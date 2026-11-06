"""Audited source mesh preparation; never fill holes or scale geometry to fit."""
from hashlib import sha256
from pathlib import Path


def remove_empty_faces(mesh):
    """Remove exactly zero-area faces, without a geometric tolerance or welding."""
    result = mesh.copy()
    before = len(result.faces)
    result.update_faces(result.area_faces > 0)
    result.remove_unreferenced_vertices()
    return result, before - len(result.faces)


def load_print_mesh(stl_path, step_path=None, tolerance_mm=.05):
    import numpy as np
    import trimesh
    from .models import number

    tolerance_mm = number(tolerance_mm, "tolerance_mm", True)
    mesh = trimesh.load_mesh(stl_path, process=True)
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
        raise ValueError(f"Expected one triangle mesh: {stl_path}")
    mesh, removed = remove_empty_faces(mesh)
    audit = {"method": "STL_vertex_deduplication_and_zero_area_removal",
             "zero_area_faces_removed": removed, "hole_filling": False,
             "scaled": False, "source_stl_sha256": sha256(Path(stl_path).read_bytes()).hexdigest()}
    if mesh.is_volume or step_path is None:
        return mesh, audit
    import cadquery as cq

    source = Path(step_path).resolve()
    shape = cq.importers.importStep(str(source)).val()
    if not shape.isValid() or not shape.Solids() or shape.Volume() <= 0:
        raise ValueError(f"STEP source must contain valid positive solids: {source}")
    original_volume = shape.Volume()
    # Capture source bounds before meshing shared OCCT faces. Meshing may change
    # the cached triangulation used by a later BoundingBox() call.
    box = shape.BoundingBox()
    source_bounds = np.array([[box.xmin, box.ymin, box.zmin], [box.xmax, box.ymax, box.zmax]])
    cleaned = shape.clean()
    if not cleaned.isValid() or abs(cleaned.Volume() / original_volume - 1) > 1e-5:
        raise ValueError("STEP face unification changed source volume beyond preparation tolerance")
    vertices, faces = cleaned.tessellate(tolerance_mm, .1)
    candidate = trimesh.Trimesh([vertex.toTuple() for vertex in vertices], faces, process=True)
    candidate, discarded = remove_empty_faces(candidate)
    if not candidate.is_volume:
        raise ValueError("STEP triangulation is not watertight; automatic hole filling is forbidden")
    bounds_error = float(np.abs(candidate.bounds - source_bounds).max())
    volume_error = abs(float(candidate.volume) / original_volume - 1)
    if bounds_error > tolerance_mm * 2 or volume_error > .001:
        raise ValueError(f"STEP tessellation exceeds screening thresholds: bounds={bounds_error} mm, relative volume={volume_error}")
    audit.update({"method": "STEP_retessellation", "step_source": str(source),
                  "step_sha256": sha256(source.read_bytes()).hexdigest(),
                  "linear_tessellation_tolerance_mm": tolerance_mm,
                  "angular_tolerance_radians": .1,
                  "step_volume_mm3": original_volume,
                  "mesh_volume_relative_error": volume_error,
                  "source_bounds_max_error_mm": bounds_error,
                  "retessellation_zero_area_faces_removed": discarded,
                  "surface_distance_certified": False,
                  "limitation": "Bounds and volume screen tessellation; they do not prove a Hausdorff error bound. Preserve meshing allowance in clearance policy."})
    return candidate, audit
