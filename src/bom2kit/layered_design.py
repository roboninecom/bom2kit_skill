"""Geometry-derived closed inner cartons stacked in a generated outer carton."""
from collections import Counter
from copy import deepcopy
import math
from time import perf_counter

from .models import normalize, number, vector
from .strip_packing import pack_strip
from .validation import validate


def remaining_height_bands(units, increment, fallback, limit=8):
    """Favor heights shared by a large volume of the remaining packing units."""
    weights = {}
    for unit in units:
        volume = math.prod(unit["dimensions"])
        heights = {math.ceil(s[2]/increment)*increment for _,s in unit["orientations"]}
        for height in heights:
            weights[height] = weights.get(height,0) + volume
    ranked = sorted(weights,key=lambda h:(-weights[h],h))[:limit]
    return sorted(set(fallback).union(ranked))


def validate_layered(problem, layout):
    """Check source coverage, each inner cavity, and supported outer carton stack."""
    try:
        data = normalize(problem)
        expected = {u["unit_id"]: u for u in data["units"]}
        poses = layout["placements"]
        if Counter(p["unit_id"] for p in poses) != Counter(expected.keys()):
            raise ValueError("Layered unit coverage mismatch")
        layers = layout["layers"]
        if not layers or len({l["id"] for l in layers}) != len(layers):
            raise ValueError("Unique nonempty layer identities required")
        declared_wall = number(problem["inner_wall_mm"], "inner_wall_mm", True)
        outer_items, outer_poses, inner_certificates = [], [], []
        known_layers = {l["id"] for l in layers}
        if any(p.get("layer_id") not in known_layers for p in poses):
            raise ValueError("Unknown layer membership")
        items = {i["id"]: i for i in problem["items"]}
        for layer in layers:
            inner = vector(layer["inner_mm"], "layer inner", True)
            position = vector(layer["position_mm"], "layer position")
            if layer["wall_mm"] != declared_wall:
                raise ValueError("Layer wall differs from manufacturing policy")
            dimensions = [v + 2*declared_wall for v in inner]
            outer_items.append({"id": layer["id"], "quantity": 1, "dimensions_mm": dimensions, "allowed_rotations": "fixed"})
            outer_poses.append({"item_id": layer["id"], "unit_id": layer["id"]+"#1",
                                "position_mm": list(position), "dimensions_mm": dimensions, "rotation": [0,1,2]})
            members = [p for p in poses if p["layer_id"] == layer["id"]]
            if not members:
                raise ValueError("Empty inner carton")
            counts = Counter(p["item_id"] for p in members)
            inner_items = [{**items[iid], "quantity": count} for iid,count in counts.items()]
            local_counts, local_poses = Counter(), []
            for p in members:
                if expected[p["unit_id"]]["item_id"] != p["item_id"]:
                    raise ValueError("Unit identity changed between layers")
                local_counts[p["item_id"]] += 1
                local_poses.append({**p, "unit_id": p["item_id"]+"#"+str(local_counts[p["item_id"]]),
                                    "position_mm": [p["position_mm"][k]-position[k]-declared_wall for k in range(3)]})
            certificate = validate({"units": "mm", "container": {"inner_mm": list(inner)},
                                    "items": inner_items, "gap_mm": problem.get("gap_mm",0)}, {"placements": local_poses})
            inner_certificates.append(certificate)
        outer = validate({"units": "mm", "container": problem["container"], "items": outer_items}, {"placements": outer_poses})
        return {"valid": outer["valid"] and all(c["valid"] for c in inner_certificates),
                "scope": "Closed inner carton cavities and supported outer stack",
                "outer": outer, "inner": inner_certificates,
                "limitations": ["Carton strength and irregular-part stability need separate qualification."]}
    except (KeyError, ValueError, TypeError) as error:
        return {"valid": False, "errors": [str(error)]}


def design_layers(request, units, time_limit=5):
    """Search footprints and height bands without a reference or supplied poses."""
    started = perf_counter()
    time_limit = number(time_limit,"time_limit",True)
    policy = request["policy"]
    thickness = number(policy["inner_wall_mm"],"inner_wall_mm",True)
    wall = vector(policy.get("wall_mm",0),"wall")
    margin = vector(policy.get("protection_mm",0),"protection")
    reserve = number(policy.get("reserved_top_mm",0),"reserve")
    gap = number(policy.get("gap_mm",0),"gap")
    increment = number(policy.get("dimension_increment_mm",1),"increment",True)
    maximum = vector(policy["max_external_mm"],"maximum",True) if "max_external_mm" in policy else None
    volume = sum(math.prod(u["dimensions"]) for u in units)
    side = volume ** (1/3)
    footprints = list(dict.fromkeys(math.ceil((side*f+2*thickness)/increment)*increment-2*thickness
                                   for f in (1.2,1,1.4,.8,1.6)))
    heights = sorted({s[2] for u in units for _,s in u["orientations"]})
    if len(heights) > 10:
        heights = [heights[round(i*(len(heights)-1)/9)] for i in range(10)]
    best, attempts = None, []
    # Compete full-width trays with narrower independently supported columns.
    # Column dimensions derive from geometry, never a target reference carton.
    configurations = [(w,d,anchor,columns) for w in footprints for d in footprints
                      for columns in (1,2) for anchor in (True,False)]
    for footprint_width, depth, anchor_required, columns in configurations:
        if perf_counter()-started >= time_limit:
            break
        width = math.ceil((footprint_width/columns+2*thickness)/increment)*increment-2*thickness
        remaining, poses, layers = list(units), [], []
        column_tops = [margin[2]] * columns
        while remaining and perf_counter()-started < time_limit:
            options = []
            anchor = max(remaining, key=lambda u:math.prod(u["dimensions"]))["unit_id"] if anchor_required else None
            for height in remaining_height_bands(remaining, increment, heights):
                if perf_counter()-started >= time_limit:
                    break
                packed = pack_strip(remaining,width, height,gap,depth=depth,allow_partial=True,priority_unit=anchor)
                if not packed["placements"]:
                    continue
                if anchor and not any(p["unit_id"] == anchor for p in packed["placements"]):
                    continue
                used = sum(math.prod(p["dimensions_mm"]) for p in packed["placements"])
                score = used / ((width+2*thickness)*(depth+2*thickness)*(packed["usable_mm"][2]+2*thickness))
                options.append((score,len(packed["placements"]),packed))
            if not options:
                break
            _,_,packed = max(options,key=lambda option: option[:2])
            lid = "layer-"+str(len(layers)+1)
            column = min(range(columns),key=lambda c:column_tops[c])
            layer_height = math.ceil((packed["usable_mm"][2]+2*thickness)/increment)*increment-2*thickness
            layer = {"id": lid, "inner_mm": [width,depth,layer_height], "wall_mm": thickness,
                     "position_mm": [margin[0]+column*(width+2*thickness),margin[1],column_tops[column]]}
            layers.append(layer)
            for pose in packed["placements"]:
                poses.append({**pose,"layer_id":lid,"position_mm": [pose["position_mm"][k]+layer["position_mm"][k]+thickness for k in range(3)]})
            placed = {p["unit_id"] for p in packed["placements"]}
            remaining = [u for u in remaining if u["unit_id"] not in placed]
            column_tops[column] += layer_height+2*thickness
        if remaining:
            continue
        cavity = [columns*(width+2*thickness), depth+2*thickness, max(column_tops)-margin[2]]
        external = [math.ceil((cavity[k]+2*(wall[k]+margin[k])+(reserve if k==2 else 0))/increment)*increment for k in range(3)]
        if maximum and any(a>b for a,b in zip(external,maximum)):
            continue
        total = math.prod(external)
        if best and total >= best["volume_mm3"]:
            continue
        problem = {"units": "mm", "items": deepcopy(request["items"]), "gap_mm":gap,
                   "inner_wall_mm": thickness,
                   "container": {"inner_mm": [external[k]-2*wall[k] for k in range(3)],
                                 "wall_mm":list(wall),"protection_mm":list(margin),"reserved_top_mm":reserve}}
        layout = {"placements": poses,"layers":layers,"status":"feasible"}
        certificate = validate_layered(problem,layout)
        attempts.append({"external_mm":external,"valid":certificate["valid"],"layer_count":len(layers)})
        if certificate["valid"]:
            packaging = [{"id":layer["id"],"quantity":1,"type":"closed_rectangular_inner_carton",
                          "inner_mm":layer["inner_mm"],"external_mm":[d+2*thickness for d in layer["inner_mm"]],
                          "wall_mm":thickness,"manufacturing_status":"Dimension specification; production dieline and strength qualification pending"}
                         for layer in layers]
            best = {"input":problem,"layout":layout,"validation":certificate,"volume_mm3":total,"external_mm":external,
                    "packaging_bom":packaging}
    return {"candidate":best,"attempts":attempts,"elapsed_seconds":perf_counter()-started}
