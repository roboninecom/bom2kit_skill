"""Replay geometry and bind an executable geometric assembly plan to one result."""
from collections import Counter
import json
from pathlib import Path
from time import perf_counter

from .bom import reconcile_bom
from .layered_design import validate_layered
from .mesh_motion import check_vertical_sequence
from .mesh_validation import validate_mesh_layout
from .models import normalize
from .report import fingerprint


def build_assembly_plan(result, expected_bom):
    """Validate original poses, group templates, copy mappings and carton order.

    This certifies geometric sequences, not hand access, load bearing or transit.
    Only generated closed-carton hierarchies are supported here.
    """
    import numpy as np
    import trimesh

    started = perf_counter()
    if result.get("status") not in ("validated_grouped_geometry", "validated_mesh_envelope_baseline"):
        raise ValueError("A verified complete design is required")
    carton = result.get("envelope_candidate", result)["envelope_design"]["candidate"]
    coverage = reconcile_bom(expected_bom, result["input"])
    hierarchy = validate_layered(carton["input"], carton["layout"])
    if not coverage["complete"] or not hierarchy["valid"]:
        raise ValueError("Complete BOM and validated closed-carton hierarchy required")
    practical_access = None
    source_modes={'planar','source_floor','source_contact'}
    needs_practical=(carton['input'].get('planar_footprints') or carton['input'].get('source_clearance_slots')
                     or any(l.get('placement_check') in source_modes for l in carton['layout']['layers']))
    if needs_practical and 'practical' not in result:
        raise ValueError('Planar footprints require original-source projection and practical checks')
    if "practical" in result:
        from .practical_validation import check_floor_support, check_hand_access
        support = check_floor_support(result)
        parameters = result["practical"].get("hand_access", {}).get("parameters", {})
        practical_access = check_hand_access(result, **parameters)
        if not support["valid"] or not practical_access["valid"]:
            raise ValueError("Practical floor support and fingertip access must independently pass")
    if result["input"]["container"] != carton["input"]["container"]:
        raise ValueError("Mesh and carton containers differ")
    external = normalize(carton["input"])["external"]
    if not np.allclose(external,carton["external_mm"],atol=1e-8,rtol=0):
        raise ValueError("Reported exterior differs from the container and wall dimensions")
    groups = result.get("groups", {})
    motion = check_vertical_sequence(result["input"], result["layout"], groups=groups)
    if not motion["valid"]:
        raise ValueError("Original-part insertion sequence failed")
    poses = {p["unit_id"]: p for p in result["layout"]["placements"]}
    sources = {item["id"]: item["mesh"] for item in result["input"]["items"]}
    templates, explained = [], set()
    for entry in result.get("group_certificates", []):
        alternative = entry["alternative"]
        assembly = alternative["assembly"]
        local = alternative["layout"]["placements"]
        local_ids = [p["unit_id"] for p in local]
        if len(set(local_ids)) != len(local_ids):
            raise ValueError("Duplicate template units")
        for manifest in (alternative["input"], assembly["input"]):
            if any(sources.get(item["id"]) != item["mesh"] for item in manifest["items"]):
                raise ValueError("Template source differs from final source")
        if not validate_mesh_layout(alternative["input"], alternative["layout"])["valid"]:
            raise ValueError("Original group geometry failed")
        frame = np.asarray(assembly["source_to_workbench"])
        workbench = {p["unit_id"]: p for p in assembly["layout"]["placements"]}
        if set(workbench) != set(local_ids) or any(
            not np.allclose(frame @ np.asarray(p["transform"]), workbench[p["unit_id"]]["transform"], atol=1e-8, rtol=0)
            for p in local
        ):
            raise ValueError("Workbench template is not one common rigid transform")
        certificate = check_vertical_sequence(assembly["input"], assembly["layout"])
        if not certificate["valid"]:
            raise ValueError("Internal group assembly failed")
        copies = []
        for gid, members in groups.items():
            if not gid.startswith("assembly-" + entry["group_id"] + "#"):
                continue
            if len(members) != len(local):
                raise ValueError("Group copy membership differs from template")
            transform = np.asarray(poses[members[0]]["transform"]) @ np.linalg.inv(local[0]["transform"])
            for uid, original in zip(members, local):
                final = poses[uid]
                if final["item_id"] != original["item_id"] or not np.allclose(
                    transform @ np.asarray(original["transform"]), final["transform"], atol=1e-8, rtol=0
                ):
                    raise ValueError("Final group copy is not the certified rigid template")
            copies.append({"group_id": gid, "unit_mapping": dict(zip(local_ids, members)),
                           "workbench_to_final": (transform @ np.linalg.inv(frame)).tolist()})
            explained.add(gid)
        if not copies:
            raise ValueError("Unused group template in selected result")
        templates.append({"id": entry["group_id"], "copies": copies,
                          "workbench_input": assembly["input"], "workbench_layout": assembly["layout"],
                          "packing_sequence": certificate["packing_sequence"], "certificate": certificate})
    if any(len(members) > 1 and gid not in explained for gid, members in groups.items()):
        raise ValueError("Multi-part group lacks a certified internal assembly template")

    vertices = {iid: np.asarray(json.loads(Path(ref["path"]).read_text())["vertices_mm"])
                for iid, ref in sources.items()}
    bounds = {uid: trimesh.transform_points(vertices[p["item_id"]], p["transform"])
              for uid, p in poses.items()}
    cartons, seen = [], []
    for layer in carton["layout"]["layers"]:
        low = np.asarray(layer["position_mm"]) + layer["wall_mm"]
        high = low + layer["inner_mm"]
        members = []
        for slot in carton["layout"]["placements"]:
            if slot["layer_id"] == layer["id"]:
                members.extend(groups.get("assembly-" + slot["unit_id"], [slot["unit_id"]]))
        for uid in members:
            if np.any(bounds[uid].min(axis=0) < low-1e-6) or np.any(bounds[uid].max(axis=0) > high+1e-6):
                raise ValueError("Original part is outside its assigned inner carton")
        member_set = set(members)
        sequence = [step for step in motion["packing_sequence"] if member_set.intersection(step["unit_ids"])]
        if practical_access is not None:
            checked = next(c for c in practical_access["cartons"] if c["carton_id"] == layer["id"])
            sequence = [{"group_id": s["unit_id"], "unit_ids": [s["unit_id"]], "direction": "-Z",
                         "finger_axis": s["axis"]} for s in checked["packing_sequence"]]
        if Counter(uid for step in sequence for uid in step["unit_ids"]) != Counter(members):
            raise ValueError("Insertion sequence crosses carton membership")
        sheets=[s for s in result.get('practical',{}).get('protective_separators',[]) if s['carton_id']==layer['id']]
        operator_steps=[];placed=set()
        for step in sequence:
            for sheet in sheets:
                if sheet['upper_unit_id'] in step['unit_ids']:
                    if sheet['lower_unit_id'] not in placed:raise ValueError('Contact sheet precedes its supporting part')
                    operator_steps.append({'action':'place_protective_contact_sheet','packaging_id':sheet['id'],
                                           'origin_mm':sheet['origin_mm'],'dimensions_mm':sheet['dimensions_mm'],
                                           'manual_sheet_handling_verified':False})
            operator_steps.append({'action':'place_source_unit',**step});placed.update(step['unit_ids'])
        cartons.append({**layer, "unit_ids": members, "packing_sequence": sequence,
                        "operator_steps":operator_steps,
                        "instruction": ("Fit the specified floor liner. Place each original unit separately in the checked fingertip-access order; fit every listed protective sheet before the upper part. Close the carton."
                                        if practical_access is not None else "Preassemble listed groups, orient to final poses, lower through the open top, then close the carton.")})
        seen.extend(members)
    if Counter(seen) != Counter(poses.keys()):
        raise ValueError("Cartons must cover every original unit exactly once")
    return {"status": "validated_geometric_assembly_plan", "result_fingerprint": fingerprint(result),
            "expected_bom_fingerprint": fingerprint(expected_bom), "bom": coverage,
            "templates": templates, "cartons_in_outer_insertion_order": cartons,
            "outer_external_mm": carton["external_mm"], "hierarchy": hierarchy,
            "original_insertion": motion, "elapsed_seconds": perf_counter()-started,
            "production_validated": False,
            "limitations": ["Hand access, part stability, carton strength and transport performance remain unqualified.",
                            "Static clearance is checked; the motion certificate establishes collision freedom only.",
                            "Source dimensions and protection assumptions remain those of the selected input."]}
