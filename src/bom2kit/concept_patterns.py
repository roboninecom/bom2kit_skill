"""Compose contiguous semantic zones from executable source-unit motifs.

A zone is a search envelope, not a purchased box or a rigid handling group.
Its members remain individual original CAD parts with independent replay.
"""
from collections import Counter
from copy import deepcopy
import math
from time import perf_counter

from .regular_patterns import floor_patterns
from .strip_packing import pack_strip
from .part_properties import coalesce_items


def manual_pattern_screen(pattern,minimum_sheet_side_mm=10.):
    """Declared manual-cutting assumption, not a material-strength standard."""
    rejected=[{'lower_unit_id':s['lower_unit_id'],'upper_unit_id':s['upper_unit_id'],
               'dimensions_mm':s['dimensions_mm']} for s in pattern.get('protective_separators',[])
              if min(s['dimensions_mm'][:2])<minimum_sheet_side_mm-1e-7]
    return {'valid':not rejected,'minimum_contact_sheet_side_mm':minimum_sheet_side_mm,
            'basis':'Declared manual handling/cutting assumption; supplier capability unmeasured',
            'rejected_contact_sheets':rejected,'physical_qualification':False}


def diverse_patterns(patterns, limit=10):
    unique = {}
    for p in sorted(patterns, key=lambda p: (math.prod(p["external_mm"]), len(p.get("protective_separators", [])))):
        unique.setdefault((tuple(p["external_mm"]), p["method"]), p)
    ordered = list(unique.values())
    if not ordered:
        return []
    keep = []
    for score in (lambda p: math.prod(p["external_mm"]), lambda p: p["external_mm"][2],
                  lambda p: math.prod(p["external_mm"][:2]), lambda p: p["external_mm"][0],
                  lambda p: len(p.get("protective_separators", []))):
        choice = min(ordered, key=score)
        if choice not in keep:
            keep.append(choice)
    for p in ordered:
        if len(keep) >= limit:
            break
        if p not in keep:
            keep.append(p)
    return keep


def repeated_rows(item, options, padding, wall, *, gap=.2, access_lane=6.4):
    """Identical SKU copies in explicit equal-orientation rows; no preassembly."""
    import numpy as np
    patterns = []
    quantity = item["quantity"]
    ids = item.get("packing_unit_ids", [f"{item['id']}#{k+1}" for k in range(quantity)])
    columns = sorted({1, quantity, max(1, math.ceil(math.sqrt(quantity))), max(1, quantity//2)})
    for index, option in enumerate(options[item["id"]]):
        dims = [v+2*padding for v in option["dimensions_mm"]]
        for n in columns:
            poses = []
            for copy, uid in enumerate(ids):
                origin = np.array([(copy % n)*(dims[0]+gap), (copy//n)*(dims[1]+max(gap, access_lane)), 0.])
                transform = np.asarray(option["transform"]).copy(); transform[:3, 3] += origin+padding
                poses.append({"item_id": item["id"], "unit_id": uid, "transform": transform.tolist(),
                              "stable_option": index, "envelope_position_mm": origin.tolist(),
                              "envelope_dimensions_mm": dims.copy()})
            size = [max(p["envelope_position_mm"][k]+p["envelope_dimensions_mm"][k] for p in poses)+2*wall for k in range(3)]
            patterns.append({"external_mm": size, "placements": poses, "method": "repeated_sku_rows",
                             "preassemblies": 0, "protective_separators": [],
                             "stable_sku_orientations": {item["id"]: index},
                             "motif_operations": [{"action": "place_individual_repeated_row", "item_id": item["id"],
                                                    "quantity": quantity, "columns": n,
                                                    "unit_ids": ids, "materials": [],
                                                    "instruction": "Place each copy separately in the same orientation; verify final insertion order."}]})
    return diverse_patterns(patterns, 12)


def transform_pattern(pattern, position, rotation, body_size, wall):
    """Translate/yaw a motif while preserving source and contact-sheet geometry."""
    import numpy as np
    yaw = np.eye(4)
    if rotation[0] == 1:
        yaw[:2, :2] = [[0, -1], [1, 0]]; yaw[0, 3] = body_size[1]
    yaw[:3, 3] += position
    def box_pose(origin, size):
        o = list(origin); s = list(size)
        if rotation[0] == 1:
            o = [body_size[1]-origin[1]-size[1], origin[0], origin[2]]; s = [size[1], size[0], size[2]]
        return [a+b for a, b in zip(o, position)], s
    poses = []
    for p in pattern["placements"]:
        transformed = deepcopy(p)
        transformed["transform"] = (yaw@np.asarray(p["transform"])).tolist()
        transformed["envelope_position_mm"], transformed["envelope_dimensions_mm"] = box_pose(p["envelope_position_mm"], p["envelope_dimensions_mm"])
        # Contour footprints require their own transformed polygon binding.
        if "footprint" in p:
            raise ValueError("Contour motifs need an explicit footprint transform")
        poses.append(transformed)
    sheets = []
    for sheet in pattern.get("protective_separators", []):
        s = deepcopy(sheet); s["origin_mm"], s["dimensions_mm"] = box_pose(s["origin_mm"], s["dimensions_mm"]); sheets.append(s)
    return poses, sheets


def carton_orientation_patterns(patterns,wall):
    """Retain an intact carton's horizontal quarter-turn for outer block search."""
    result=list(patterns)
    for pattern in patterns:
        if abs(pattern['external_mm'][0]-pattern['external_mm'][1])<1e-7:
            continue
        # Projected contours need their own bound polygon transform. These
        # alternatives cover the original-source row/stack/pair patterns.
        if any('footprint' in p for p in pattern['placements']):continue
        rotated=deepcopy(pattern);body=[v-2*wall for v in pattern['external_mm']]
        rotated['placements'],rotated['protective_separators']=transform_pattern(pattern,[0.,0.,0.],(1,0,2),body,wall)
        rotated['external_mm']=[pattern['external_mm'][1],pattern['external_mm'][0],pattern['external_mm'][2]]
        for zone in rotated.get('semantic_zones',[]):
            if 'origin_mm' in zone and 'dimensions_mm' in zone:
                x,y,z=zone['origin_mm'];w,d,h=zone['dimensions_mm']
                zone['origin_mm']=[body[1]-y-d,x,z];zone['dimensions_mm']=[d,w,h]
        for pair in rotated.get('individual_floor_pairs',[]):
            if 'bounding_floor_mm' in pair:pair['bounding_floor_mm']=pair['bounding_floor_mm'][::-1]
        rotated['carton_quarter_turn']=True
        result.append(rotated)
    return result


def compose_zones(zones, wall, *, gap=.2, hand_border=7.2, access_lane=6.4,
                  increment=1., seconds=3., target_footprints=()):
    """Pack named source zones, retaining low-height and narrow alternatives."""
    started = perf_counter(); candidates = []; configurations = []
    heights = sorted({p["external_mm"][2] for z in zones for p in z["patterns"]})
    for height in heights:
        selected = []
        for z in zones:
            possible = [p for p in z["patterns"] if p["external_mm"][2] <= height+1e-7]
            if not possible:
                break
            selected.append(min(possible, key=lambda p: (math.prod(p["external_mm"][:2]), len(p.get("protective_separators", [])))))
        if len(selected) == len(zones):
            signature = tuple((tuple(p["external_mm"]), p["method"]) for p in selected)
            if not any(signature == s for s, _ in configurations):
                configurations.append((signature, selected))
    configurations.sort(key=lambda entry: sum(math.prod(v-2*wall for v in p["external_mm"][:2]) for p in entry[1])*max(p["external_mm"][2] for p in entry[1]))
    for ci, (_, selected) in enumerate(configurations):
        if candidates and ci >= 3 and perf_counter()-started > seconds:
            break
        units = []
        for index, p in enumerate(selected):
            size = [v-2*wall for v in p["external_mm"]]
            if min(size) <= 0:
                raise ValueError("Invalid zone envelope")
            units.append({"item_id": str(index), "unit_id": str(index), "dimensions": size,
                          "orientations": [((0, 1, 2), tuple(size)), ((1, 0, 2), (size[1], size[0], size[2]))]})
        area = sum(math.prod(u["dimensions"][:2]) for u in units); height = max(u["dimensions"][2] for u in units)
        widths = sorted({max(min(u["dimensions"][:2]) for u in units), *(math.sqrt(area)*f for f in (.6, .8, 1., 1.25, 1.6, 2.))})
        targets = [(w-2*(wall+hand_border), d-2*(wall+hand_border)) for w, d in target_footprints] or [(w, None) for w in widths]
        for width, depth in targets:
            for order in ("area", "input"):
                packed = pack_strip(units, width, height, max(gap, access_lane), depth=depth,
                                    placement_score="short_side", item_order=order)
                if not packed:
                    continue
                poses = []; sheets = []; records = []; operations = []
                source_contact = False; source_clearance = False
                for q in packed["placements"]:
                    index = int(q["unit_id"]); p = selected[index]; z = zones[index]
                    position = [q["position_mm"][0]+hand_border, q["position_mm"][1]+hand_border, 0.]
                    original, protective = transform_pattern(p, position, q["rotation"], units[index]["dimensions"], wall)
                    poses.extend(original); sheets.extend(protective)
                    source_contact |= p.get("source_contact_slots", False)
                    source_clearance |= p.get("source_clearance_slots", False)
                    records.append({"id": z["id"], "unit_ids": [v["unit_id"] for v in original],
                                    "origin_mm": position, "dimensions_mm": q["dimensions_mm"],
                                    "motif": p["method"], "physical_container": False})
                    operations.extend(p.get("motif_operations", []))
                used = [max(p["envelope_position_mm"][k]+p["envelope_dimensions_mm"][k] for p in poses) for k in range(3)]
                used[:2] = [v+hand_border for v in used[:2]]
                external = [math.ceil((v+2*wall)/increment-1e-9)*increment for v in used]
                if depth is not None:
                    external[:2] = [width+2*(wall+hand_border), depth+2*(wall+hand_border)]
                candidates.append({"external_mm": external, "placements": poses, "method": "semantic_zones",
                                   "preassemblies": 0, "protective_separators": sheets,
                                   "source_contact_slots": source_contact, "source_clearance_slots": source_clearance,
                                   "semantic_zones": records, "motif_operations": operations})
    return diverse_patterns(carton_orientation_patterns(candidates,wall), 16)


def group_patterns(group, options, policy, *, seconds=3., mode="rows", cache=None,minimum_sheet_side=10.):
    """Generate source-derived motifs; all outputs still require independent replay."""
    if mode == 'volumetric':
        from .volumetric_patterns import volumetric_patterns
        fallback = group_patterns(group, options, policy, seconds=seconds/2, mode='rows', cache=cache,
                                  minimum_sheet_side=minimum_sheet_side)
        patterns = volumetric_patterns(group['items'], options, policy, seconds=seconds/2, hand_border=0.)
        return {'patterns': diverse_patterns(patterns+fallback['patterns'], 20),
                'diagnostics': fallback['diagnostics']}
    if mode=='hybrid':
        generated=[group_patterns(group,options,policy,seconds=seconds/4,mode=m,cache=cache,minimum_sheet_side=minimum_sheet_side)
                   for m in ('rows','stacks','alternating','nesting')]
        return {'patterns':diverse_patterns([p for g in generated for p in g['patterns']],20),
                'diagnostics':[d for g in generated for d in g['diagnostics']]}
    wall = policy["carton"]["inner_wall_mm"]; padding = policy["item_padding_mm"]
    gap = policy["carton"]["gap_mm"]; zones = []; diagnostics = []
    for item in group["items"]:
        key = (item["id"], item["quantity"], tuple(item.get("packing_unit_ids", [])), mode,minimum_sheet_side)
        cached = cache.get(key) if cache is not None else None
        if cached is None:
            patterns = repeated_rows(item, options, padding, wall, gap=gap)
            if mode in ("stacks", "nesting") and item['quantity']>1:
                try:
                    generated = floor_patterns([item], options, padding, wall, gap=gap, seconds=max(.1, seconds/max(1, len(group["items"]))),
                                               hand_border=0., access_lane_mm=6.4,
                                               stack_overhang_fraction=0.,minimum_sheet_side=minimum_sheet_side,
                                               stack_height_factor=3. if mode == "stacks" else 1.5,
                                               supported_nesting=mode == "nesting")
                    patterns.extend(generated["patterns"])
                except ValueError as error:
                    diagnostics.append({"item_id": item["id"], "mode": mode, "rejected": str(error)})
            cached = diverse_patterns(patterns, 12)
            if cache is not None:
                cache[key] = cached
        zones.append({"id": item["id"], "patterns": cached})
    if len(zones) == 1:
        patterns = deepcopy(zones[0]["patterns"])
    else:
        patterns = compose_zones(zones, wall, gap=gap, hand_border=0., seconds=seconds)
    if mode in ("nesting", "alternating") and len(group["items"]) > 1:
        try:
            generated = floor_patterns(group["items"], options, padding, wall, gap=gap,
                                       seconds=seconds, hand_border=0., access_lane_mm=6.4,
                                       floor_pair_budget=seconds if mode == "alternating" else 0.,
                                       stack_height_factor=1.5 if mode == "nesting" else 0.,
                                       supported_nesting=mode == "nesting",minimum_sheet_side=minimum_sheet_side)
            for p in generated["patterns"]:
                pairs = p.get("supported_pairs", []) if mode == "nesting" else p.get("individual_floor_pairs", [])
                if not pairs:
                    continue
                p["method"] = "semantic_supported_pairs" if mode == "nesting" else "semantic_alternating_floor_pairs"
                p["motif_operations"] = [{"action": "place_source_units_individually", "unit_ids": pair["unit_ids"],
                                           "instruction": "Place the first part, then insert its paired part separately in the verified order.",
                                           "materials": "Listed contact sheets" if mode == "nesting" else []} for pair in pairs]
                patterns.append(p)
        except ValueError as error:
            diagnostics.append({"group": group["id"], "mode": mode, "rejected": str(error)})
    patterns = diverse_patterns(patterns, 16)
    for p in patterns:
        p["semantic_group"] = group["id"]
    return {"patterns": patterns, "diagnostics": diagnostics}


def cohesive_carton_patterns(groups, options, policy, *, seconds=2., mode="rows", hand_border=7.2,
                             access_lane=6.4, packing_gap=None,target_footprints=(),semantic_order='portfolio',minimum_sheet_side=10.):
    """Keep meaningful neighbors without assigning rectangular private zones."""
    if mode == 'volumetric':
        from .volumetric_patterns import volumetric_patterns
        items = coalesce_items([i for g in groups for i in g['items']])
        generated = volumetric_patterns(items, options, policy, seconds=seconds/2, hand_border=hand_border,
                                        access_lane=access_lane, target_footprints=target_footprints)
        fallback = cohesive_carton_patterns(groups, options, policy, seconds=seconds/2, mode='rows',
                       hand_border=hand_border, access_lane=access_lane, packing_gap=packing_gap,
                       target_footprints=target_footprints, semantic_order=semantic_order,
                       minimum_sheet_side=minimum_sheet_side)
        return diverse_patterns(generated+fallback, 24)
    if mode=='hybrid':
        return diverse_patterns([p for m in ('rows','stacks','alternating','nesting')
            for p in cohesive_carton_patterns(groups,options,policy,seconds=seconds/4,mode=m,
                hand_border=hand_border,access_lane=access_lane,packing_gap=packing_gap,
                target_footprints=target_footprints,semantic_order=semantic_order,minimum_sheet_side=minimum_sheet_side)],24)
    if semantic_order=='portfolio':
        return diverse_patterns([p for order in ('group','area')
            for p in cohesive_carton_patterns(groups,options,policy,seconds=seconds/2,mode=mode,
                hand_border=hand_border,access_lane=access_lane,packing_gap=packing_gap,
                target_footprints=target_footprints,semantic_order=order,minimum_sheet_side=minimum_sheet_side)],24)
    ordered = sorted(groups, key=lambda g: (-max(min(max(o['dimensions_mm']) for o in options[i['id']]) for i in g['items']), g['id']))
    items = coalesce_items([i for g in ordered for i in g['items']])
    labels = {i['id']: g.get('semantic_parent',g['id']) for g in ordered for i in g['items']}
    affinities={iid:values for g in ordered for iid,values in g.get('nesting_affinities',{}).items()}
    spec = policy['carton']
    generated = floor_patterns(items, options, policy['item_padding_mm'], spec['inner_wall_mm'],
        gap=max(spec['gap_mm'],packing_gap or 0.), seconds=seconds, hand_border=hand_border, access_lane_mm=access_lane,
        target_footprints=target_footprints,
        semantic_order=semantic_order,
        semantic_labels=labels,semantic_affinities=affinities,
        stack_height_factor=2.5 if mode=='stacks' else 1.5 if mode=='nesting' else 0.,
        stack_overhang_fraction=0.,minimum_sheet_side=minimum_sheet_side,
        supported_nesting=mode=='nesting', floor_pair_budget=seconds if mode=='alternating' else 0.)
    for p in generated['patterns']:
        p['method']='cohesive_'+p['method']
        p['semantic_zones']=[{'id':g['id'],'unit_ids':[uid for i in g['items'] for uid in i.get('packing_unit_ids',[f"{i['id']}#{n+1}" for n in range(i['quantity'])])],
                              'physical_container':False,'constraint':'soft adjacency, no reserved rectangle'} for g in ordered]
        p['motif_operations']=[{'action':'place_semantic_group_individually','semantic_group':g['id'],
                                'materials':'Listed protective sheets and retained source packing states',
                                'instruction':'Place original units separately in the checked sequence; preserve same-type neighbors.'} for g in ordered]
    return carton_orientation_patterns(generated['patterns'],spec['inner_wall_mm'])
