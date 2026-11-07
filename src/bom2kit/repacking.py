"""Apply an internally generated carton improvement to unchanged original meshes."""
from copy import deepcopy
from time import perf_counter

from .assembly_plan import build_assembly_plan
from .layered_design import validate_layered
from .mesh_validation import validate_mesh_layout
from .mesh_motion import check_vertical_sequence
from .report import fingerprint


def apply_layer_candidate(result, candidate, expected_bom):
    """Transfer rigid packing units and replay original geometry and assembly.

    This is an improvement stage for the engine's own result, not a reference
    importer. Carton dimensions may change; source envelopes and policy may not.
    """
    import numpy as np

    started = perf_counter()
    old_envelope = result.get("envelope_candidate",result)
    old = old_envelope["envelope_design"]["candidate"]
    # A status string alone cannot authorize reuse of stale or altered geometry.
    build_assembly_plan(result,expected_bom)
    for key in ("units","items","gap_mm","inner_wall_mm"):
        if old["input"].get(key) != candidate["input"].get(key):
            raise ValueError("Repacking may not change source envelopes or policy")
    old_policy = {k:v for k,v in old["input"]["container"].items() if k != "inner_mm"}
    new_policy = {k:v for k,v in candidate["input"]["container"].items() if k != "inner_mm"}
    if old_policy != new_policy:
        raise ValueError("Repacking may not change protection or wall policy")
    if not validate_layered(candidate["input"],candidate["layout"])["valid"]:
        raise ValueError("Invalid replacement carton hierarchy")
    original_slots = {p["unit_id"]:p for p in old["layout"]["placements"]}
    new_slots = {p["unit_id"]:p for p in candidate["layout"]["placements"]}
    if set(original_slots) != set(new_slots):
        raise ValueError("Repacking membership mismatch")

    def frame(slot):
        rotation = np.eye(3)[slot["rotation"]]
        if np.linalg.det(rotation)<0:
            rotation[0] *= -1
        transform = np.eye(4)
        transform[:3,:3] = rotation
        transform[:3,3] = np.asarray(slot["position_mm"])+np.asarray(slot["dimensions_mm"])/2
        return transform

    deltas = {uid:frame(new_slots[uid]) @ np.linalg.inv(frame(slot)) for uid,slot in original_slots.items()}
    updated = deepcopy(result)
    envelope = updated.get("envelope_candidate",updated)
    envelope["envelope_design"] = {"status":"validated_envelope_design","candidate":deepcopy(candidate),
                                  "search":{"method":"internal_layer_membership_improvement","reference_used":False,
                                            "optimality_proven":False,"parent_result_fingerprint":fingerprint(result)}}
    envelope["input"]["container"] = deepcopy(candidate["input"]["container"])
    for pose in envelope["layout"]["placements"]:
        pose["transform"] = (deltas[pose["unit_id"]] @ np.asarray(pose["transform"])).tolist()
    envelope["validation"] = validate_mesh_layout(envelope["input"],envelope["layout"])
    envelope["motion"] = check_vertical_sequence(envelope["input"],envelope["layout"])
    if not envelope["validation"]["valid"] or not envelope["motion"]["valid"]:
        raise ValueError("Repacked envelope geometry or insertion failed")
    if "envelope_candidate" in updated:
        updated["input"]["container"] = deepcopy(candidate["input"]["container"])
        by_unit = {uid:delta for slot,delta in deltas.items() for uid in updated["groups"]["assembly-"+slot]}
        for pose in updated["layout"]["placements"]:
            pose["transform"] = (by_unit[pose["unit_id"]] @ np.asarray(pose["transform"])).tolist()
        updated["validation"] = validate_mesh_layout(updated["input"],updated["layout"])
        updated["motion"] = check_vertical_sequence(updated["input"],updated["layout"],groups=updated["groups"])
        if not updated["validation"]["valid"] or not updated["motion"]["valid"]:
            raise ValueError("Repacked original geometry or insertion failed")
    # Historical timings are provenance, not timings for the improved result.
    envelope.pop("timing",None)
    updated["repacking"] = {"parent_result_fingerprint":fingerprint(result),"method":"internal_layer_membership_improvement"}
    plan = build_assembly_plan(updated,expected_bom)
    return {"result":updated,"assembly_plan":plan,"validation_seconds":perf_counter()-started}
