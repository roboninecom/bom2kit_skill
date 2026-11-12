"""Source-bound stable floor poses and complete planar projections."""
from hashlib import sha256
import json
from pathlib import Path


def load_mesh(item):
    import trimesh
    raw = Path(item["mesh"]["path"]).read_bytes()
    if sha256(raw).hexdigest() != item["mesh"]["sha256"]:
        raise ValueError("Source mesh hash mismatch")
    data = json.loads(raw)
    if data.get("units") != "mm":
        raise ValueError("Source mesh must use millimetres")
    mesh = trimesh.Trimesh(data["vertices_mm"], data["triangles"], process=False)
    if not mesh.is_volume:
        raise ValueError("Positive watertight source mesh required")
    return mesh


def contact_certificate(mesh, *, plane_z=0., tolerance_mm=.02, minimum_margin_mm=.05):
    """Quasistatic horizontal-plane support under a uniform-density assumption.

    Contact vertices, not an object's bounding rectangle, define the support
    polygon. This does not establish bearing strength, friction or restraint.
    """
    import numpy as np
    from shapely.geometry import MultiPoint, Point
    low = float(mesh.bounds[0, 2])
    points = mesh.vertices[np.abs(mesh.vertices[:, 2] - plane_z) <= tolerance_mm]
    polygon = MultiPoint(points[:, :2]).convex_hull if len(points) else None
    center = np.asarray(mesh.center_mass)
    point = Point(center[:2])
    margin = (polygon.boundary.distance(point) if polygon.covers(point) else -polygon.distance(point)) if polygon is not None and polygon.area > 1e-10 else -1.
    return {"valid": abs(low-plane_z) <= tolerance_mm and margin >= minimum_margin_mm,
            "floor_error_mm": low-plane_z, "support_area_mm2": polygon.area if polygon is not None else 0.,
            "center_margin_mm": margin, "center_of_mass_mm": center.tolist(),
            "mass_model": "uniform source solid density; purchased envelopes are geometric proxies",
            "tolerance_mm": tolerance_mm, "minimum_margin_mm": minimum_margin_mm,
            "physical_qualification": False}


def projected_polygon(mesh, padding_mm=0.):
    """Union every triangle projection; do not treat through-height cavities as empty by inference."""
    import numpy as np
    from shapely import polygons, union_all
    triangles = mesh.triangles[:, :, :2]
    a, b = triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0]
    cross = np.abs(a[:, 0]*b[:, 1]-a[:, 1]*b[:, 0])
    shape = union_all(polygons(triangles[cross > 1e-12]))
    if shape.is_empty or not shape.is_valid:
        raise ValueError("Invalid complete mesh projection")
    return shape.buffer(padding_mm, join_style="round") if padding_mm else shape


def stable_pose_options(item, *, maximum=8, cache=None):
    """Derive poses from source CAD only, retaining support-checked alternatives."""
    import numpy as np
    import trimesh
    from shapely.geometry import mapping, MultiPoint
    mesh = load_mesh(item)
    key = sha256(json.dumps({"mesh": item["mesh"]["sha256"], "maximum": maximum,
                            "algorithm": "floor-poses-v2"}, sort_keys=True).encode()).hexdigest()
    path = Path(cache)/f"{key}.json" if cache else None
    if path and path.exists():
        return json.loads(path.read_text())
    transforms, probabilities = trimesh.poses.compute_stable_poses(mesh, n_samples=1, sigma=0, threshold=0)
    proposals = []
    ranked = sorted(zip(transforms, probabilities), key=lambda pair: -pair[1])
    # Highly tessellated round shapes can expose thousands of almost identical
    # resting facets. Bound geometric preparation, without certifying discarded poses.
    ranked = ranked[:max(32, maximum*4)]
    for transform, probability in ranked:
        placed = mesh.copy(); placed.apply_transform(transform)
        # Align the stable plane footprint to a minimum rectangle; then only
        # quarter-turn it during packing, preserving the actual contact face.
        rectangle = MultiPoint(placed.vertices[:, :2]).minimum_rotated_rectangle
        vertices = np.asarray(rectangle.exterior.coords)
        edge = vertices[1]-vertices[0]
        angle = -np.arctan2(edge[1], edge[0])
        yaw = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
        base = yaw @ transform
        placed = mesh.copy(); placed.apply_transform(base)
        base[:3, 3] -= placed.bounds[0]
        placed = mesh.copy(); placed.apply_transform(base)
        certificate = contact_certificate(placed)
        if not certificate["valid"]:
            continue
        size = placed.extents.tolist()
        proposals.append({"transform": base.tolist(), "dimensions_mm": size,
                          "probability": float(probability), "contact": certificate})
    proposals.sort(key=lambda p: (p["dimensions_mm"][2], -p["contact"]["center_margin_mm"]))
    selected = []
    for proposal in proposals:
        dims = proposal["dimensions_mm"]
        if any(np.allclose(sorted(dims[:2])+dims[2:], sorted(p["dimensions_mm"][:2])+p["dimensions_mm"][2:], atol=.05) for p in selected):
            continue
        selected.append(proposal)
    if len(selected) > maximum:
        # Keep height and volume/aspect alternatives rather than tiny-probability poses only.
        selected = sorted(selected, key=lambda p: (np.prod(p["dimensions_mm"]), p["dimensions_mm"][2]))[:maximum]
    if not selected:
        raise ValueError(f"No stable supported floor pose: {item['id']}")
    for proposal in selected:
        placed = mesh.copy(); placed.apply_transform(proposal["transform"])
        proposal["footprint"] = mapping(projected_polygon(placed))
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(selected), encoding="utf8")
    return selected
