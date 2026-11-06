"""Computational complete-kit comparison, separate from physical qualification."""
from hashlib import sha256
import json
import math
from .bom import reconcile_bom
from .models import vector
from .mesh_validation import validate_mesh_layout


def assess_mesh_kit(bom, problem, layout):
    """Recheck every declared unit and compare nominal external carton volumes.

    The caller supplies the authoritative BOM, including any explicit packet
    hierarchy. This function cannot verify whether that supplied BOM is complete
    relative to a different engineering document.
    """
    container = problem["container"]
    if "wall_mm" not in container:
        raise ValueError("Explicit cavity-to-exterior wall_mm is required for comparison")
    inner = vector(container["inner_mm"], "inner_mm", True)
    wall = vector(container["wall_mm"], "wall_mm")
    external = [a + 2*b for a, b in zip(inner, wall)]
    reference = vector(problem["reference"]["external_mm"], "reference.external_mm", True)
    geometry = validate_mesh_layout(problem, layout)
    coverage = reconcile_bom(bom, problem)
    volume, reference_volume = math.prod(external) / 1e6, math.prod(reference) / 1e6
    volume_pass = volume <= reference_volume + 1e-9
    fingerprints = {name + "_sha256": sha256(json.dumps(value, sort_keys=True,
                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()
                    for name, value in (("bom", bom), ("input", problem), ("layout", layout))}
    assumptions = [{"id": i["id"], "basis": i.get("dimension_basis", i.get("geometry_evidence")),
                    "packing_state": i.get("packing_state")}
                   for i in problem["items"] if "dimension_basis" in i or "geometry_evidence" in i]
    return {"scope": "Complete declared BOM under explicit computational packing assumptions",
            "computational_acceptance": geometry["valid"] and coverage["complete"] and volume_pass,
            "external_mm": external, "external_volume_l": volume,
            "reference_external_mm": reference, "reference_external_volume_l": reference_volume,
            "volume_change_percent": (volume / reference_volume - 1) * 100,
            "volume_no_worse": volume_pass, "geometry": geometry, "coverage": coverage,
            "assumed_items": assumptions, "assumptions": problem.get("assumptions", []),
            "packing_sequence_verified": False, "physical_qualification": False,
            "limitations": ["BOM completeness and reference equivalence depend on supplied evidence.",
                            "Packet counts do not independently establish their internal contents.",
                            "Static fit alone does not certify stability, handling or transport."],
            **fingerprints}
