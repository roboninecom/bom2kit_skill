from bom2kit.models import normalize
from bom2kit.strip_packing import pack_strip
from bom2kit.validation import validate
import pytest


@pytest.mark.parametrize("placement_score",["bottom_left","short_side","area"])
def test_strip_reuses_free_rectangles_and_keeps_lateral_clearance(placement_score):
    problem = {"units": "mm", "container": {"inner_mm": [8,30,2]}, "gap_mm": .2,
               "items": [{"id": "long", "quantity": 3, "dimensions_mm": [4,2,1]},
                         {"id": "square", "quantity": 2, "dimensions_mm": [2,2,1]}]}
    strip = pack_strip(normalize(problem)["units"], 8, 1, .2,placement_score=placement_score)
    problem["container"]["inner_mm"] = strip["usable_mm"]
    assert validate(problem, strip)["valid"]
    assert strip["usable_mm"][1] < 10


def test_strip_rejects_unavailable_orientations():
    problem = {"container": {"inner_mm": [10,10,10]}, "items": [
        {"id": "upright", "dimensions_mm": [2,2,8], "allowed_rotations": "fixed"}]}
    assert pack_strip(normalize(problem)["units"], 10, 3) is None
