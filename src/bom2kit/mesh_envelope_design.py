"""Independent conservative mesh baseline using automatically oriented boxes.

Singleton groups provide a valid starting point for later cluster optimization.
This stage may waste concave voids; it never claims to be a nesting optimizer.
"""
from hashlib import sha256
from itertools import permutations
import json
from pathlib import Path
from time import perf_counter

from .carton_design import design_carton
from .models import number


def design_mesh_envelopes(library, policy, time_limit=5):
    import numpy as np
    import trimesh
    from .mesh_validation import validate_mesh_layout
    from .mesh_motion import check_vertical_sequence

    started = perf_counter()
    if library.get("units") != "mm" or not library.get("all_meshes_valid_volumes"):
        raise ValueError("A verified mm part library is required")
    if set(policy) != {"carton", "item_padding_mm", "clearance_mm", "allow_all_rotations"}:
        raise ValueError("Explicit carton, item padding, clearance and rotation policy required")
    if policy["allow_all_rotations"] is not True:
        raise ValueError("This baseline currently requires explicitly unrestricted part rotations")
    padding = number(policy["item_padding_mm"], "item_padding_mm", True)
    clearance = number(policy["clearance_mm"], "clearance_mm", True)
    if 2 * padding < clearance:
        raise ValueError("Padding must preserve the requested inter-part clearance")
    frames, envelopes, items = {}, [], []
    for item in library["items"]:
        ref = item["mesh"]
        raw = Path(ref["path"]).read_bytes()
        if sha256(raw).hexdigest() != ref["sha256"]:
            raise ValueError("Geometry source hash mismatch")
        source = json.loads(raw)
        if source.get("units") != "mm":
            raise ValueError("Mesh source must use mm")
        mesh = trimesh.Trimesh(source["vertices_mm"], source["triangles"], process=False)
        if not mesh.is_volume or np.any(mesh.area_faces <= 0):
            raise ValueError("Invalid mesh source")
        frame, _ = trimesh.bounds.oriented_bounds(mesh)
        points = trimesh.transform_points(mesh.vertices, frame)
        frame[:3, 3] -= points.min(axis=0)
        size = np.ptp(points, axis=0)
        frames[item["id"]] = (frame, size)
        envelopes.append({"id": item["id"], "quantity": item["quantity"],
                          "dimensions_mm": (size + 2 * padding).tolist(),
                          "allowed_rotations": [list(p) for p in permutations(range(3))]})
        items.append({key: value for key, value in item.items() if key in
                      {"id", "quantity", "mesh", "contents", "contents_revisions", "revision", "dimension_basis", "packing_state"}})
    preparation = perf_counter() - started
    design = design_carton({"units": "mm", "items": envelopes, "policy": policy["carton"]}, time_limit=time_limit)
    candidate = design["candidate"]
    if not candidate:
        return {"status": "no_verified_candidate", "envelope_design": design}
    poses = []
    for placement in candidate["layout"]["placements"]:
        frame, size = frames[placement["item_id"]]
        rotation = np.eye(3)[placement["rotation"]]
        if np.linalg.det(rotation) < 0:
            rotation[0] *= -1
        # Signed axis permutations preserve handedness. Translate negative axes
        # back into the positive local box; never reflect or resize a part.
        low = np.minimum(rotation, 0) @ size
        transform = np.eye(4)
        transform[:3, :3] = rotation
        transform[:3, 3] = np.asarray(placement["position_mm"]) + padding - low
        poses.append({"item_id": placement["item_id"], "unit_id": placement["unit_id"],
                      "transform": (transform @ frame).tolist()})
    problem = {"units": "mm", "container": candidate["input"]["container"],
               "clearance_mm": clearance, "items": items}
    layout = {"units": "mm", "placements": poses}
    validation_started = perf_counter()
    certificate = validate_mesh_layout(problem, layout)
    motion = check_vertical_sequence(problem, layout) if certificate["valid"] else None
    return {"status": "validated_mesh_envelope_baseline" if certificate["valid"] and motion and motion["valid"] else "validation_failed",
            "input": problem, "layout": layout, "validation": certificate, "motion": motion,
            "envelope_design": design, "scope": library.get("scope", "Declared library only"),
            "timing": {"geometry_preparation_seconds": preparation,
                       "carton_design_seconds": design["search"]["total_seconds"],
                       "mesh_validation_and_motion_seconds": perf_counter() - validation_started,
                       "total_seconds": perf_counter() - started},
            "limitations": ["Singleton envelope baseline; automatic cluster nesting is not implemented here.",
                            "Padding is a geometric allowance, not a manufactured protective sleeve.",
                            "No independent shipping BOM reconciliation or transport qualification is implied."]}
