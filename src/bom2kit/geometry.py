"""Read-only CAD measurement. Geometry measurements are not packing proof."""

from hashlib import sha256
from pathlib import Path
import time


def inspect_step(path):
    """Return STEP geometry measurements using optional CadQuery/OpenCascade.

    No quantity, material density, packed state, or production revision is inferred.
    STEP import handles source units; CadQuery measurements are in millimetres.
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"CAD file does not exist: {path}")
    if path.suffix.lower() == ".3mf":
        from .mesh_geometry import inspect_3mf
        return inspect_3mf(path)
    if path.suffix.lower() not in (".step", ".stp"):
        raise ValueError("Expected STEP (.step/.stp) or 3MF geometry")
    started = time.perf_counter()
    import cadquery as cq

    imported = time.perf_counter()
    shape = cq.importers.importStep(str(path)).val()
    bbox = shape.BoundingBox()
    solids = shape.Solids()
    return {
        "source": str(path), "sha256": sha256(path.read_bytes()).hexdigest(),
        "units": "mm", "format": "STEP", "valid_shape": shape.isValid(),
        "bounding_box_mm": [bbox.xlen, bbox.ylen, bbox.zlen],
        "bounds_min_mm": [bbox.xmin, bbox.ymin, bbox.zmin],
        "cad_solid_volume_mm3": shape.Volume(), "solid_count": len(solids),
        "scope": "Source geometry in its original pose; not a packing arrangement or verified BOM",
        "production_status": "unverified",
        "timing": {"library_import_seconds": imported - started,
                   "measurement_seconds": time.perf_counter() - imported},
    }
