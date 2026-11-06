"""Independent static validation of explicit, fingerprinted triangle placements.

Optional dependencies: numpy, trimesh, python-fcl, rtree. No voxel approximation
or automatic repair is used. Floating-point mesh checks are not a CAD proof or
an insertion, stability, protection, or transport qualification.
"""

from hashlib import sha256
import json
import math
from pathlib import Path


def validate_mesh_layout(problem, layout):
    """Check a supplied mesh layout against its explicit manifest.

    Mesh refs: {path, sha256}; JSON files require units='mm', vertices_mm and
    triangles. A .3mf ref additionally needs instance_id, optionally frame.
    Placements: {item_id, unit_id: 'ID#1', transform: 4x4 column-vector matrix}.
    Every transform must be a proper rigid transform; scaling/reflection fails.
    """
    import numpy as np
    import trimesh
    from .models import vector

    errors, placed, expected, sources = [], {}, {}, {}
    limitations = [
        "Static triangulated geometry only; no insertion-path or support validation.",
        "No protection performance, assembly identity, or physical trial validation.",
        "Floating-point FCL and ray parity checks; self-intersecting source surfaces are not certified.",
        "Surface contact is conservatively rejected; a positive clearance is recommended.",
    ]

    def result():
        return {"valid": not errors, "errors": errors,
                "scope": "static_triangle_mesh_layout",
                "checks": ["source_sha256", "units", "quantities", "identity", "proper_rigid_transform",
                           "watertight_consistent_positive_mesh", "vertex_containment",
                           "triangle_surface_collision", "enclosed_solid_collision", "pair_clearance"],
                "expected_units": len(expected), "placed_units": len(placed),
                "sources": sources, "limitations": limitations,
                "production_validated": False}

    if not isinstance(problem, dict) or not isinstance(layout, dict):
        errors.append("Problem and layout must be JSON objects")
        return result()
    if problem.get("units") != "mm" or layout.get("units") != "mm":
        errors.append("Problem and layout must explicitly use mm")
        return result()
    try:
        inner = np.array(vector(problem["container"]["inner_mm"], "inner_mm", True))
        margin = np.array(vector(problem["container"].get("protection_mm", 0), "protection_mm"))
        clearance = problem.get("clearance_mm", 0)
        reserved_top = problem["container"].get("reserved_top_mm", 0)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (clearance, reserved_top)):
            raise ValueError("Clearance and reserved top must be numbers")
        if not math.isfinite(reserved_top) or reserved_top < 0:
            raise ValueError("Invalid reserved top")
        inner[2] -= reserved_top
        if not math.isfinite(clearance) or clearance < 0 or np.any(2 * margin >= inner):
            raise ValueError("Invalid clearance or protection")
        if not isinstance(problem["items"], list) or not all(isinstance(item, dict) for item in problem["items"]):
            raise ValueError("items must be a list of objects")
        if not isinstance(layout.get("placements"), list) or not all(isinstance(p, dict) for p in layout["placements"]):
            raise ValueError("placements must be a list of objects")
        ids = set()
        for item in problem["items"]:
            iid, quantity = item["id"], item.get("quantity", 1)
            if not isinstance(iid, str) or not iid or iid in ids:
                raise ValueError("Item IDs must be nonempty and unique")
            ids.add(iid)
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
                raise ValueError("Quantities must be positive integers")
            for index in range(quantity):
                expected[f"{iid}#{index + 1}"] = item
        if not expected:
            raise ValueError("Mesh BOM is empty")
    except (ValueError, KeyError, TypeError) as error:
        errors.append(f"Invalid problem: {error}")
        return result()

    loaded = {}
    for iid in ids:
        item = next(i for i in problem["items"] if i["id"] == iid)
        try:
            ref = item["mesh"]
            path = Path(ref["path"])
            actual_hash = sha256(path.read_bytes()).hexdigest()
            if actual_hash != ref["sha256"]:
                raise ValueError("Source SHA256 mismatch")
            sources[iid] = {"path": str(path.resolve()), "sha256": actual_hash}
            if path.suffix.lower() == ".3mf":
                from .mesh_geometry import load_instance_mesh

                geometry = load_instance_mesh(path, ref["instance_id"], ref.get("frame", "object"))
                if geometry["instance"]["classification"] == "excluded_nonpart":
                    raise ValueError("Explicit nonpart/support mesh cannot represent a BOM item")
            else:
                geometry = json.loads(path.read_text(encoding="utf-8-sig"))
                if geometry.get("units") != "mm":
                    raise ValueError("Mesh JSON must explicitly use mm")
            vertices = np.asarray(geometry["vertices_mm"], dtype=float)
            raw_faces = np.asarray(geometry["triangles"])
            faces = raw_faces.astype(np.int64)
            if (vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices)
                    or not np.isfinite(vertices).all() or faces.ndim != 2 or faces.shape[1] != 3
                    or not len(faces) or not np.array_equal(raw_faces, faces)
                    or faces.min() < 0 or faces.max() >= len(vertices)):
                raise ValueError("Invalid vertices or triangle indices")
            mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
            if not mesh.is_volume or np.any(mesh.area_faces <= 0):
                raise ValueError("Mesh must be watertight, consistently wound, positive-volume, without degenerate faces")
            loaded[iid] = mesh
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
            errors.append(f"Invalid source {iid}: {error}")

    seen = set()
    for placement in layout.get("placements", []):
        try:
            uid = placement["unit_id"]
            if uid not in expected or uid in seen:
                raise ValueError(f"Unknown or duplicate unit: {uid}")
            seen.add(uid)
            iid = expected[uid]["id"]
            if placement["item_id"] != iid:
                raise ValueError(f"Wrong item identity: {uid}")
            matrix = np.array(placement["transform"], dtype=float)
            if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
                raise ValueError(f"Invalid transform: {uid}")
            rotation = matrix[:3, :3]
            if (not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-9, rtol=0)
                    or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-9, rtol=0)
                    or not np.isclose(np.linalg.det(rotation), 1, atol=1e-9, rtol=0)):
                raise ValueError(f"Transform must be proper rigid rotation/translation: {uid}")
            if iid not in loaded:
                continue
            mesh = loaded[iid].copy()
            mesh.apply_transform(matrix)
            if np.any(mesh.vertices < margin - 1e-8) or np.any(mesh.vertices > inner - margin + 1e-8):
                errors.append(f"Outside protected cavity: {uid}")
            placed[uid] = mesh
        except (ValueError, KeyError, TypeError) as error:
            errors.append(f"Invalid placement: {error}")
    for uid in sorted(expected.keys() - seen):
        errors.append(f"Missing unit: {uid}")

    # FCL checks the complete triangle surfaces. With disjoint closed surfaces,
    # one point per connected surface component suffices to detect enclosure.
    # Use all connected components, not only the mesh's first vertex.
    representatives = {}
    managers = {}
    try:
        for uid, mesh in placed.items():
            manager = trimesh.collision.CollisionManager()
            manager.add_object(uid, mesh)
            managers[uid] = manager
            components = trimesh.graph.connected_components(mesh.edges_unique, nodes=np.arange(len(mesh.vertices)))
            representatives[uid] = mesh.vertices[[int(component[0]) for component in components]]
        entries = list(placed.items())
        for index, (a_id, a) in enumerate(entries):
            for b_id, b in entries[index + 1:]:
                if managers[a_id].in_collision_single(b):
                    errors.append(f"Surface collision/contact or convex overlap: {a_id}, {b_id}")
                    continue
                # This catches nested solids missed by surface-intersection tests,
                # while ray parity correctly permits a part in a genuine cavity.
                if a.contains(representatives[b_id]).any() or b.contains(representatives[a_id]).any():
                    errors.append(f"Enclosed solid collision: {a_id}, {b_id}")
                    continue
                distance = managers[a_id].min_distance_single(b)
                if distance + 1e-8 < clearance:
                    errors.append(f"Pair clearance violated: {a_id}, {b_id}")
    except (ImportError, ValueError, RuntimeError) as error:
        errors.append(f"Mesh collision checks unavailable or failed: {error}")
    return result()
