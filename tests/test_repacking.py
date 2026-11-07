from copy import deepcopy
import pytest

from test_assembly_plan import two_cartons
from bom2kit.repacking import apply_layer_candidate


def test_repacking_transfers_original_geometry_and_rejects_changed_protection(tmp_path):
    result,bom = two_cartons(tmp_path)
    candidate = deepcopy(result["envelope_design"]["candidate"])
    # Exchange carton membership while preserving complete, valid envelopes.
    for p in candidate["layout"]["placements"]:
        if p["unit_id"] == "cube#1":
            p["layer_id"] = "carton-2"
            p["position_mm"][2] += 13
        else:
            p["layer_id"] = "carton-1"
            p["position_mm"][2] -= 13
    updated = apply_layer_candidate(result,candidate,bom)
    poses = updated["result"]["layout"]["placements"]
    assert poses[0]["transform"][2][3] == 19.5
    assert poses[1]["transform"][2][3] == 6.5
    assert updated["assembly_plan"]["status"] == "validated_geometric_assembly_plan"
    candidate["input"]["container"]["wall_mm"] = .5
    with pytest.raises(ValueError,match="policy"):
        apply_layer_candidate(result,candidate,bom)


def test_repacking_rejects_altered_source_envelopes(tmp_path):
    result,bom = two_cartons(tmp_path)
    candidate = deepcopy(result["envelope_design"]["candidate"])
    candidate["input"]["items"][0]["dimensions_mm"][0] = 9
    with pytest.raises(ValueError,match="source envelopes"):
        apply_layer_candidate(result,candidate,bom)
