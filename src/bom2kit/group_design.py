"""Compose discovered groups, pack their envelopes and verify original part poses."""
from hashlib import sha256
import json
from pathlib import Path


def design_grouped_library(library, portfolio, policy, output, time_limit=5, incumbent_volume_mm3=None,
                           incumbent_result=None):
    import numpy as np
    import trimesh
    from .mesh_envelope_design import design_mesh_envelopes
    from .mesh_validation import validate_mesh_layout
    from .mesh_motion import check_vertical_sequence

    library_hash = sha256(json.dumps(library, sort_keys=True).encode()).hexdigest()
    footprint_hints = []
    if incumbent_result is not None:
        if incumbent_result.get("source_library_sha256") != library_hash:
            raise ValueError("Incumbent belongs to a different source library")
        if incumbent_result.get("status") not in ("validated_grouped_geometry","validated_mesh_envelope_baseline"):
            raise ValueError("Only a verified in-run incumbent may supply footprints")
        old = incumbent_result.get("envelope_candidate",incumbent_result)["envelope_design"]["candidate"]
        if old["layout"].get("layers"):
            from .layered_design import validate_layered
            if not validate_layered(old["input"],old["layout"])["valid"]:
                raise ValueError("Invalid incumbent carton hierarchy")
            footprint_hints = list(dict.fromkeys(tuple(layer["inner_mm"][:2]) for layer in old["layout"]["layers"]))
    if portfolio["source_library_sha256"] != library_hash:
        raise ValueError("Pair portfolio belongs to a different source library")
    if portfolio["clearance_mm"] < max(policy["clearance_mm"], 2 * policy["item_padding_mm"]):
        raise ValueError("Discovered pairs do not preserve the configured padding/clearance")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    sources = {i["id"]: i for i in library["items"]}
    remaining = {i["id"]: i["quantity"] for i in library["items"]}
    assigned = {iid: 0 for iid in sources}
    grouped, expansion, certificates = [], {}, []
    alternatives = sorted(portfolio["alternatives"], key=lambda a: a["group_box_volume_mm3"] - a["separate_box_volume_mm3"])
    for alternative in alternatives:
        needed = {iid: alternative["members"].count(iid) for iid in alternative["members"]}
        copies = min(remaining[iid] // count for iid, count in needed.items())
        if not copies:
            continue
        expected = {iid: {"id": iid, "quantity": count, "mesh": sources[iid]["mesh"]} for iid, count in needed.items()}
        for manifest in (alternative["input"], alternative["assembly"]["input"]):
            if {i["id"]: i for i in manifest["items"]} != expected:
                raise ValueError("Group certificate source/quantity mismatch")
        if not check_vertical_sequence(alternative["assembly"]["input"], alternative["assembly"]["layout"])["valid"]:
            raise ValueError("Invalid internal assembly recipe")
        # Revalidate the source-frame geometry independently, too. A certificate
        # for the workbench frame cannot certify a separately modified layout.
        if not validate_mesh_layout(alternative["input"], alternative["layout"])["valid"]:
            raise ValueError("Invalid original-source group layout")
        # Verify workbench poses are one common rigid transformation of exactly
        # the source poses before trusting its internal-motion certificate.
        frame = np.asarray(alternative["assembly"]["source_to_workbench"])
        workbench = {p["unit_id"]: p for p in alternative["assembly"]["layout"]["placements"]}
        if set(workbench) != {p["unit_id"] for p in alternative["layout"]["placements"]}:
            raise ValueError("Assembly membership mismatch")
        for pose in alternative["layout"]["placements"]:
            if not np.allclose(frame @ np.asarray(pose["transform"]), workbench[pose["unit_id"]]["transform"], atol=1e-8, rtol=0):
                raise ValueError("Assembly pose mismatch")
        pieces = []
        for pose in alternative["layout"]["placements"]:
            ref = sources[pose["item_id"]]["mesh"]
            data = json.loads(Path(ref["path"]).read_text())
            mesh = trimesh.Trimesh(data["vertices_mm"], data["triangles"], process=False)
            mesh.apply_transform(pose["transform"])
            pieces.append(mesh)
        combined = trimesh.util.concatenate(pieces)
        group_id = "group-" + str(len(certificates) + 1)
        if group_id in sources:
            raise ValueError("Generated group identity conflicts with a source item")
        path = output / (group_id + ".json")
        path.write_text(json.dumps({"units": "mm", "vertices_mm": combined.vertices.tolist(), "triangles": combined.faces.tolist()}))
        grouped.append({"id": group_id, "quantity": copies, "mesh": {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}})
        for copy in range(copies):
            members = []
            for pose in alternative["layout"]["placements"]:
                iid = pose["item_id"]
                assigned[iid] += 1
                remaining[iid] -= 1
                members.append({**pose, "unit_id": iid + "#" + str(assigned[iid])})
            expansion[group_id + "#" + str(copy + 1)] = members
        certificates.append({"group_id": group_id, "alternative": alternative})
    for iid, quantity in remaining.items():
        if not quantity:
            continue
        grouped.append({**sources[iid], "quantity": quantity})
        for copy in range(quantity):
            assigned[iid] += 1
            expansion[iid + "#" + str(copy + 1)] = [{"item_id": iid, "unit_id": iid + "#" + str(assigned[iid]), "transform": np.eye(4).tolist()}]
    grouped_library = {"units": "mm", "all_meshes_valid_volumes": True,
                       "scope": library.get("scope"), "items": grouped}
    candidate = design_mesh_envelopes(grouped_library, policy, time_limit=time_limit,
                                     incumbent_volume_mm3=incumbent_volume_mm3,footprint_hints=footprint_hints)
    if candidate["status"] == "not_improved":
        result = {"status":"not_improved","envelope_candidate":candidate,"source_library_sha256":library_hash}
        (output/"result.json").write_text(json.dumps(result,allow_nan=False))
        return result
    if candidate["status"] != "validated_mesh_envelope_baseline":
        return {"status": "group_envelope_failure", "candidate": candidate}
    placements, groups = [], {}
    for pose in candidate["layout"]["placements"]:
        group_members = expansion[pose["unit_id"]]
        groups["assembly-" + pose["unit_id"]] = [p["unit_id"] for p in group_members]
        for member in group_members:
            placements.append({**member, "transform": (np.asarray(pose["transform"]) @ np.asarray(member["transform"])).tolist()})
    problem = {**candidate["input"], "items": [{key: value for key,value in i.items() if key in
               {"id", "quantity", "mesh", "contents", "contents_revisions", "revision", "dimension_basis", "packing_state"}}
               for i in library["items"]]}
    layout = {"units": "mm", "placements": placements}
    validation = validate_mesh_layout(problem, layout)
    motion = check_vertical_sequence(problem, layout, groups=groups) if validation["valid"] else None
    result = {"status": "validated_grouped_geometry" if validation["valid"] and motion and motion["valid"] else "validation_failed",
              "input": problem, "layout": layout, "validation": validation, "motion": motion,
              "groups": groups, "group_certificates": certificates, "envelope_candidate": candidate,
              "scope": library.get("scope"), "source_library_sha256": library_hash,
              "limitations": ["Greedy group selection; complete grouping optimum not proven.", "Packaging materials and source shipping BOM coverage are not certified by this geometry stage."]}
    (output / "result.json").write_text(json.dumps(result, allow_nan=False))
    return result
