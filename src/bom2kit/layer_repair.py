"""Local repacking of an internally generated layer assignment on the size lattice."""
import math
import random
from time import perf_counter

from .strip_packing import pack_strip


def repair_floor(members, poses, width, depth, height, gap, rng, deadline):
    """Retain valid generated poses and relocate boundary blockers plus neighbors."""
    keepable = [p for p in poses if p["position_mm"][0]+p["dimensions_mm"][0] <= width+1e-8
                and p["position_mm"][1]+p["dimensions_mm"][1] <= depth+1e-8
                and p["dimensions_mm"][2] <= height+1e-8]
    for attempt in range(80):
        if perf_counter() >= deadline:
            break
        count = 0 if attempt == 0 else min(len(keepable),1+attempt%5)
        removed = set(rng.sample(range(len(keepable)),count))
        initial = [p for i,p in enumerate(keepable) if i not in removed]
        mode = ("height_fill","bottom_left","short_side","area")[attempt%4]
        packed = pack_strip(members,width,height,gap,depth=depth,initial_placements=initial,
                            placement_score=mode,item_order="compact" if attempt%2 else "area")
        if packed is not None:
            return packed
    return None


def repair_layer_stack(units, candidate, gap, thickness, increment, time_limit=2):
    """Propose complete one-column stacks; callers independently validate them.

    Preserve layer membership and valid internally generated poses where useful.
    Relocated units use permitted orientations. Multi-column layouts stay unchanged.
    """
    started = perf_counter()
    rng = random.Random(0)
    layers = candidate["layout"].get("layers",[])
    if not layers or len({tuple(layer["inner_mm"][:2]) for layer in layers}) != 1:
        return []
    if len({tuple(layer["position_mm"][:2]) for layer in layers}) != 1:
        return []
    by_id = {unit["unit_id"]:unit for unit in units}
    memberships = []
    seen = []
    for layer in layers:
        ids = [p["unit_id"] for p in candidate["layout"]["placements"] if p["layer_id"] == layer["id"]]
        if not ids or any(uid not in by_id for uid in ids):
            return []
        memberships.append([by_id[uid] for uid in ids])
        seen.extend(ids)
    if len(seen) != len(by_id) or set(seen) != set(by_id):
        return []
    base_width,base_depth = layers[0]["inner_mm"][:2]
    proposals = []
    offsets = [(0,0),(-1,-1),(-2,-2),(-1,0),(0,-1),(-2,0),(0,-2),
               (1,-1),(-1,1),(1,0),(0,1),(1,1),(2,-2),(-2,2)]
    for dx,dy in offsets:
        if perf_counter()-started >= time_limit:
            break
        width,depth = base_width+dx*increment,base_depth+dy*increment
        if min(width,depth) <= 0:
            continue
        stack = []
        for layer,members in zip(layers,memberships):
            # Volume is a necessary bound only, not a fit certificate.
            lower = sum(math.prod(unit["dimensions"]) for unit in members)/(width*depth)
            ceiling = layer["inner_mm"][2]+2*increment
            heights = sorted({size[2] for unit in members for _,size in unit["orientations"]
                              if lower-1e-8 <= size[2] <= ceiling+1e-8})
            local = [{**p,"position_mm":[p["position_mm"][k]-layer["position_mm"][k]-thickness for k in range(3)]}
                     for p in candidate["layout"]["placements"] if p["layer_id"] == layer["id"] and "position_mm" in p]
            best = repair_floor(members,local,width,depth,layer["inner_mm"][2],gap,rng,started+time_limit) if local else None
            for height in heights:
                if best is not None and height >= best["usable_mm"][2]-1e-8:
                    break
                variants = [("bottom_left","area"),("height_fill","area"),("short_side","area"),
                            ("height_fill","compact"),("short_side","compact"),
                            ("short_side","best_fit"),("area","best_fit")]
                variants += [("height_fill","input"),("short_side","input")]*4
                for mode,order in variants:
                    if perf_counter()-started >= time_limit:
                        break
                    ordered = list(members)
                    if order == "input":
                        # Seeded order perturbation changes search, never geometry.
                        ordered.sort(key=lambda u:-math.prod(u["dimensions"])*rng.uniform(.5,1.5))
                    packed = pack_strip(ordered,width,height,gap,depth=depth,placement_score=mode,item_order=order)
                    if packed is not None:
                        if best is None or packed["usable_mm"][2] < best["usable_mm"][2]:
                            best = packed
                if (best is not None and best["usable_mm"][2] <= height+1e-8) or perf_counter()-started >= time_limit:
                    break
            if best is None:
                break
            stack.append(best)
        if len(stack) == len(layers):
            proposals.append({"width_mm":width,"depth_mm":depth,"layers":stack,
                              "height_mm":sum(math.ceil((p["usable_mm"][2]+2*thickness)/increment)*increment for p in stack)})
    return proposals
