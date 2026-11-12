"""Evidence-aware semantic cards and organization measurements.

Name-derived labels guide search only. They never authorize a contact, remove
protection, establish material strength or change a source packing state.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import re
import math

from .packing_states import declared_state
from .report import fingerprint


def _fact(value, source, status="declared"):
    return {"value": value, "status": status, "source": source}


def describe_parts(library, policy, options=None, annotations=None):
    annotations = annotations or {}
    ids = {i["id"] for i in library["items"]}
    if set(annotations)-ids:
        raise ValueError("Part annotations name unknown source SKUs")
    cards = {}
    for item in library["items"]:
        iid = item["id"]
        evidence = item.get("source_evidence", {})
        names = [str(item.get(k, "")) for k in ("name", "source_name", "source_stem")]
        names.append(str(evidence.get("source_item", "")))
        label = next((s for s in names if s), iid)
        # The identifier is a useful last-resort textual label, never a lookup
        # into a benchmark-specific grouping or coordinate table.
        text = " ".join([*names, iid]).lower().replace("_", " ")
        state = declared_state(item)
        family = policy["families"][iid]
        printed = state["kind"] == "source_part"
        kind, assembly = "unclassified", "unknown"
        if printed:
            if "aruco" in text:
                kind, assembly = "fiducial_parts", "fiducial_object"
            elif "cube" in text or "cylinder" in text or "cone" in text:
                kind, assembly = "learning_objects", "learning_objects"
            elif "nameplate" in text:
                kind, assembly = "nameplates", "identification"
            else:
                for token, category in (("holder", "holders"), ("plate", "plates"),
                                        ("washer", "washers"), ("ring", "rings"),
                                        ("clamp", "clamps"), ("rack", "racks"),
                                        ("gear", "gears"), ("nail", "pins"),
                                        ("frame", "frames"), ("handle", "handles"),
                                        ("trigger", "levers"), ("spacer", "spacers"),
                                        ("cap", "covers"), ("snap", "clips"),
                                        ("wrist", "joint_parts"),
                                        ("arm", "arm_parts"), ("base", "base_parts")):
                    if token in text:
                        kind = category
                        break
                if "follower" in text:
                    assembly = "follower_arm"
                elif "leader" in text:
                    assembly = "leader_arm"
                elif "gripper" in text or "rack" in text or "nail" in text:
                    assembly = "gripper"
                elif any(t in text for t in ("base", "bottom", "upper arm", "wrist")):
                    assembly = "arm_structure"
                elif "board" in text or "cable snap" in text:
                    assembly = "electronics_mounting"
                elif "camera" in text:
                    assembly = "camera_mounting"
                elif "handle" in text or "trigger" in text:
                    assembly = "manual_control"
        else:
            rules = [(r"clamp", "clamps"), (r"bearing", "bearings"),
                     (r"\brod\b", "rods"), (r"power supply", "power_supplies"),
                     (r"camera", "cameras"), (r"cable|cord", "cables"),
                     (r"adapter", "adapters"), (r"extras", "accessory_packets"),
                     (r"hex.key|driver", "tools"), (r"screw|nut|socket head|countersunk|set screw", "fasteners"),
                     (r"o.ring", "seals"), (r"sts\d|servo", "servos")]
            kind = next((value for pattern, value in rules if re.search(pattern, text)), "unclassified")
        card = {
            "id": iid, "label": label, "quantity": _fact(item["quantity"], "source BOM"),
            "family": _fact(family, "transport compatibility policy"),
            "part_type": _fact(kind, label, "name_inference" if kind != "unclassified" else "unknown"),
            "assembly": _fact(assembly, label, "name_inference" if assembly != "unknown" else "unknown"),
            "material": _fact(None, "not established by geometry", "unknown"),
            "fragility": _fact(None, "not supplied", "unknown"),
            "packing_state": deepcopy(state),
            "protection": _fact({"padding_mm": policy["item_padding_mm"],
                                  "source_clearance_mm": policy["clearance_mm"]}, "unchanged transport policy"),
            "contact_permission": _fact("preserve source separation and explicit support checks", "transport policy"),
            "allowed_orientations": _fact(len(options[iid]) if options else None,
                                           "source-derived stable poses" if options else "not prepared",
                                           "computed" if options else "unknown"),
            "source_mesh": deepcopy(item["mesh"]),
        }
        if item.get('material'):
            card['material']=_fact(item['material'],'source item material declaration')
        elif 'stainless steel' in text:
            card['material']=_fact('stainless_steel',label,'name_inference')
        elif any(token in text for token in ('aluminum','aluminium')):
            card['material']=_fact('aluminium',label,'name_inference')
        if 'fragile' in item:
            card['fragility']=_fact(item['fragile'],'source item fragility declaration')
        if options:
            dimensions = sorted(options[iid][0]['dimensions_mm'])
            card['shape_profile'] = _fact({'sorted_extent_mm':dimensions,
                'thin_ratio':dimensions[0]/dimensions[2], 'elongation':dimensions[2]/dimensions[1]},
                'source stable-pose bounds; shape does not establish function or strength','computed')
            if state['kind']=='source_part':
                from .practical_geometry import load_mesh
                mesh=load_mesh(item)
                card['shape_cohort']=_fact(mesh.identifier_hash,
                    'Trimesh rigid-invariant shape descriptor; similarity proposal only, never geometry substitution','computed')
        for key, entry in annotations.get(iid, {}).items():
            if key not in ("part_type", "assembly", "material", "fragility"):
                raise ValueError("Semantic annotations cannot modify geometry or protection")
            if not isinstance(entry, dict) or not entry.get("source") or entry.get("status") not in ("declared", "measured", "assumption") or "value" not in entry:
                raise ValueError("Every annotation requires value, status and evidence source")
            card[key] = deepcopy(entry)
        cards[iid] = card
    return {"schema_version": 1, "source_library_fingerprint": fingerprint(library),
            "reference_used": False, "cards": cards}


def semantic_key(card, mode="assembly"):
    family = card["family"]["value"]
    kind = card["part_type"]["value"]
    assembly = card["assembly"]["value"]
    if mode == "sku":
        group = card["id"]
    elif mode == "shape":
        group = 'shape-'+card['shape_cohort']['value'] if 'shape_cohort' in card else kind
        if group=='unclassified':group=card['id']
    elif mode == "type":
        group = kind if kind != "unclassified" else card["id"]
    elif mode == "assembly":
        group = assembly if assembly != "unknown" else kind
        if group == "unclassified":
            group = card["id"]
    else:
        raise ValueError("Unknown semantic grouping mode")
    return family + ":" + str(group)


def semantic_groups(library, cards, mode="assembly"):
    groups = defaultdict(list)
    for item in library["items"]:
        groups[semantic_key(cards[item["id"]], mode)].append(item)
    return [{"id": key, "family": cards[items[0]["id"]]["family"]["value"],
             "items": deepcopy(items), "semantic_mode": mode} for key, items in sorted(groups.items())]


def adaptive_groups(library, cards, options, policy,base_mode='assembly'):
    """Split height-incompatible semantic groups; whole SKUs remain indivisible.

    This is a reversible concept proposal. The final beam may reunite subgroups
    or place them with other compatible groups. Gains are heuristic estimates.
    """
    from .regular_patterns import partition_by_height
    padding=policy['item_padding_mm'];groups=semantic_groups(library,cards,base_mode)
    def estimate(items):
        heights=sorted({p['dimensions_mm'][2] for i in items for p in options[i['id']]})
        scores=[]
        for h in heights:
            areas=[]
            for item in items:
                eligible=[(p['dimensions_mm'][0]+2*padding)*(p['dimensions_mm'][1]+2*padding)
                          for p in options[item['id']] if p['dimensions_mm'][2]<=h+1e-7]
                if not eligible:break
                areas.append(min(eligible)*item['quantity'])
            if len(areas)==len(items):scores.append(sum(areas)*(h+2*padding))
        return min(scores)
    revised=[]
    for group in groups:
        original=estimate(group['items']);best=(original,[group['items']],'unchanged')
        for count in range(2,min(3,len(group['items']))+1):
            for strategy in ('cost','footprint_cost'):
                chunks=partition_by_height(group['items'],options,count,strategy)
                score=sum(estimate(c) for c in chunks)
                # Require a meaningful estimated gain to justify fragmented kit groups.
                adjusted=score*(1+.08*(count-1))
                if adjusted<best[0]*.95:best=(adjusted,chunks,strategy)
        for index,chunk in enumerate(best[1],1):
            revised.append({**group,'id':group['id']+(f'/shape-{index}' if len(best[1])>1 else ''),
                            'items':chunk,'semantic_parent':group['id'],'semantic_mode':'adaptive',
                            'revision':{'method':best[2],'source_group_estimate_mm3':original,
                                        'adjusted_split_estimate_mm3':best[0],'reference_used':False}})
    return revised


def replicated_groups(library,cards,options,policy):
    """Propose two balanced repetitions of a type group, with original unit IDs.

    A later concept may reunite the repetitions. This is a carton-pattern
    hypothesis, not a bag, preassembly or permission to split packet contents.
    """
    groups=adaptive_groups(library,cards,options,policy,base_mode='type');result=[]
    for group in groups:
        if max(i['quantity'] for i in group['items'])<2 or sum(i['quantity'] for i in group['items'])<4:
            result.append(group);continue
        halves=[[],[]];weights=[0.,0.]
        for item in sorted(group['items'],key=lambda i:-min(math.prod(p['dimensions_mm']) for p in options[i['id']])):
            quantity=item['quantity'];ids=item.get('packing_unit_ids',[f"{item['id']}#{n+1}" for n in range(quantity)])
            assignments=[[],[]];volume=min(math.prod(p['dimensions_mm']) for p in options[item['id']])
            for uid in ids:
                target=min(range(2),key=lambda n:weights[n]);assignments[target].append(uid);weights[target]+=volume
            for index,units in enumerate(assignments):
                if units:halves[index].append({**deepcopy(item),'quantity':len(units),'packing_unit_ids':units})
        for index,items in enumerate(halves,1):
            if items:result.append({**group,'id':group['id']+f'/repeat-{index}','items':items,
                'semantic_parent':group.get('semantic_parent',group['id']),'semantic_mode':'replicated',
                'revision':{'method':'balanced_source_copy_repetitions','reference_used':False}})
    return result


def coalesce_items(items):
    """Reunite source copies without losing counts or duplicating unit identities."""
    merged={}
    for item in items:
        iid=item['id'];units=item.get('packing_unit_ids',[f'{iid}#{n+1}' for n in range(item['quantity'])])
        if len(units)!=item['quantity'] or len(set(units))!=len(units):raise ValueError('Invalid source copy identities')
        if iid not in merged:merged[iid]={**deepcopy(item),'packing_unit_ids':list(units)}
        else:
            previous=merged[iid]
            if previous['mesh']!=item['mesh'] or set(previous['packing_unit_ids']).intersection(units):
                raise ValueError('Cannot reunite changed or duplicate source units')
            previous['quantity']+=item['quantity'];previous['packing_unit_ids'].extend(units)
    return list(merged.values())


def motif_neighbors(first,second):
    """Prefer same-type or same-assembly motifs inside an already compatible family."""
    return (first.get('cohesion_group')==second.get('cohesion_group') or
            bool(set(first.get('nesting_affinities',())).intersection(second.get('nesting_affinities',()))))


def organization_metrics(result, cards, mode='type'):
    """Evaluate every method with the same labels and geometric separation rule.

    Connected components use protected AABB surface distance <= 10 mm. This is
    a declared organization proxy, not a physical restraint certificate.
    """
    import numpy as np
    from .practical_geometry import load_mesh
    poses = result["layout"]["placements"]
    sources = {i["id"]: load_mesh(i) for i in result["input"]["items"]}
    bounds = {}
    by_unit = {}
    for p in poses:
        mesh = sources[p["item_id"]].copy(); mesh.apply_transform(p["transform"])
        bounds[p["unit_id"]] = mesh.bounds
        by_unit[p["unit_id"]] = p["item_id"]
    locations = defaultdict(set); split_skus = defaultdict(set); records = []; fragments = 0
    for module in result["logistics"]["modules"]:
        groups = defaultdict(list)
        for uid in module["unit_ids"]:
            iid = by_unit[uid]; key = semantic_key(cards[iid],mode)
            groups[key].append(uid); locations[key].add(module["id"]); split_skus[iid].add(module["id"])
        components = {}
        for key, units in groups.items():
            unseen = set(units); count = 0
            while unseen:
                frontier = [unseen.pop()]; count += 1
                while frontier:
                    a = bounds[frontier.pop()]
                    for uid in list(unseen):
                        b = bounds[uid]
                        separation = np.maximum(0., np.maximum(a[0]-b[1], b[0]-a[1]))
                        if np.linalg.norm(separation) <= 10.+1e-7:
                            unseen.remove(uid); frontier.append(uid)
            components[key] = count; fragments += max(0, count-1)
        records.append({"carton_id": module["id"], "semantic_groups": dict(Counter(semantic_key(cards[by_unit[u]],mode) for u in module["unit_ids"])),
                        "group_connected_components": components})
    return {"semantic_groups_per_carton": records,"grouping_basis":mode,
            "mixed_group_pairs": sum(len(r["semantic_groups"])*(len(r["semantic_groups"])-1)//2 for r in records),
            "split_semantic_groups": sum(max(0, len(v)-1) for v in locations.values()),
            "split_source_skus": sum(max(0, len(v)-1) for v in split_skus.values()),
            "additional_spatial_fragments": fragments, "adjacency_distance_mm": 10.,
            "physical_restraint_verified": False}
