from copy import deepcopy
import json

import pytest

from bom2kit.carton_design import design_carton
from bom2kit.cli import main
from bom2kit.validation import validate


def job():
    return {"units": "mm", "items": [
        {"id": "part", "quantity": 4, "dimensions_mm": [10, 10, 10], "allowed_rotations": "fixed"}],
        "policy": {"wall_mm": 1.5, "protection_mm": 2, "reserved_top_mm": 1,
                   "gap_mm": .5, "dimension_increment_mm": 5}}


def test_generated_carton_has_complete_coverage_and_preserves_shell():
    result = design_carton(job(), time_limit=.5)
    candidate = result["candidate"]
    assert result["status"] == "validated_envelope_design"
    assert validate(candidate["input"], candidate["layout"])["valid"]
    assert len(candidate["layout"]["placements"]) == 4
    assert all(x % 5 == 0 for x in candidate["external_mm"])
    assert candidate["input"]["container"]["wall_mm"] == [1.5] * 3
    assert candidate["input"]["container"]["protection_mm"] == [2] * 3
    assert candidate["input"]["container"]["reserved_top_mm"] == 1
    assert result["search"]["reference_used"] is False


@pytest.mark.parametrize("field", ["reference", "container", "placements", "seed_layout"])
def test_no_reference_or_recipe_input_allowed(field):
    request = job()
    request[field] = {}
    with pytest.raises(ValueError, match="forbidden"):
        design_carton(request)


def test_forbidden_item_pose_and_policy_target():
    request = job()
    request["items"][0]["orientation_hint"] = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    with pytest.raises(ValueError, match="Envelope items"):
        design_carton(request)
    request = job()
    request["policy"]["reference_volume"] = 20
    with pytest.raises(ValueError, match="policy"):
        design_carton(request)


def test_maximum_rejects_all_candidates_without_false_infeasibility_claim():
    request = job()
    request["policy"]["max_external_mm"] = [5, 5, 5]
    result = design_carton(request, time_limit=.1)
    assert result["candidate"] is None
    assert result["status"] == "no_verified_candidate"


def test_new_quantity_is_designed_without_old_output(tmp_path):
    request = job()
    path = tmp_path / "job.json"
    output = tmp_path / "output"
    path.write_text(json.dumps(request))
    assert main(["design-envelopes", str(path), "--output", str(output), "--time-limit", ".2"]) == 0
    changed = deepcopy(request)
    changed["items"][0]["quantity"] = 5
    path.write_text(json.dumps(changed))
    assert main(["design-envelopes", str(path), "--output", str(output), "--time-limit", ".2"]) == 0
    assert len(json.loads((output / "layout.json").read_text())["placements"]) == 5
    changed["policy"]["max_external_mm"] = [1, 1, 1]
    path.write_text(json.dumps(changed))
    assert main(["design-envelopes", str(path), "--output", str(output), "--time-limit", ".1"]) == 1
    assert json.loads((output / "validation.json").read_text())["valid"] is False
