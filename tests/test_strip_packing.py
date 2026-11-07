from bom2kit.models import normalize
from bom2kit.strip_packing import pack_strip
from bom2kit.validation import validate
import pytest


@pytest.mark.parametrize("placement_score",["bottom_left","short_side","area","height_fill"])
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


def test_volume_order_preserves_tall_items_when_floor_area_is_scarce():
    problem = {"container":{"inner_mm":[10,10,10]},"items":[
        {"id":"thin","dimensions_mm":[10,10,1],"allowed_rotations":"fixed"},
        {"id":"dense","dimensions_mm":[9,9,10],"allowed_rotations":"fixed"}]}
    units = normalize(problem)["units"]
    area = pack_strip(units,10,10,depth=10,allow_partial=True)
    volume = pack_strip(units,10,10,depth=10,allow_partial=True,item_order="volume")
    assert area["placements"][0]["item_id"] == "thin"
    assert volume["placements"][0]["item_id"] == "dense"
    with pytest.raises(ValueError,match="item order"):
        pack_strip(units,10,10,item_order="unknown")


def test_height_fill_uses_allowed_vertical_span_without_changing_dimensions():
    problem = {"container":{"inner_mm":[10,10,4]},"items":[
        {"id":"block","dimensions_mm":[4,3,2],"allowed_rotations":[[0,1,2],[1,2,0],[2,1,0]]}]}
    units = normalize(problem)["units"]
    result = pack_strip(units,10,4,depth=10,placement_score="height_fill")
    assert result["placements"][0]["dimensions_mm"][2] == 4
    assert validate(problem,result)["valid"]


@pytest.mark.parametrize("order",["input","compact","best_fit"])
def test_repair_keeps_existing_unit_and_packs_every_remaining_unit(order):
    problem = {"container":{"inner_mm":[21,10,10]},"gap_mm":.2,"items":[
        {"id":"cube","quantity":2,"dimensions_mm":[10,10,10],"allowed_rotations":"fixed"}]}
    units = normalize(problem)["units"]
    initial = [{"item_id":"cube","unit_id":"cube#1","position_mm":[0,0,0],
                "dimensions_mm":[10,10,10],"rotation":[0,1,2]}]
    result = pack_strip(units,21,10,.2,depth=10,item_order=order,initial_placements=initial)
    assert validate(problem,result)["valid"]
    assert result["placements"][0] == initial[0]
    assert result["placements"][1]["position_mm"][0] >= 10.2
    with pytest.raises(ValueError,match="membership"):
        pack_strip(units,21,10,.2,depth=10,initial_placements=initial*2)


def test_floor_area_bound_retains_smaller_permitted_upright_footprints():
    problem = {"container":{"inner_mm":[11,10,10]},"gap_mm":.2,"items":[
        {"id":"plate","quantity":2,"dimensions_mm":[10,10,1],"allowed_rotations":[[0,1,2],[2,0,1]]}]}
    result = pack_strip(normalize(problem)["units"],11,10,.2,depth=10,placement_score="height_fill")
    assert validate(problem,result)["valid"]
    assert len(result["placements"]) == 2
