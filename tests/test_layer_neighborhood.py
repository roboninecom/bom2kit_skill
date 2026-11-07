from copy import deepcopy
import pytest
from bom2kit.layer_neighborhood import improve_layer_membership
from bom2kit.layered_design import validate_layered


def split_stack():
    items = [{"id":"part","quantity":2,"dimensions_mm":[10,10,10],"allowed_rotations":"fixed"}]
    layers = [{"id":str(i),"inner_mm":[22,22,10],"wall_mm":1.5,"position_mm":[3,3,3+13*i]} for i in range(2)]
    poses = [{"item_id":"part","unit_id":f"part#{i+1}","layer_id":str(i),"position_mm":[4.5,4.5,4.5+13*i],
              "dimensions_mm":[10,10,10],"rotation":[0,1,2]} for i in range(2)]
    return {"input":{"units":"mm","items":items,"gap_mm":.2,"inner_wall_mm":1.5,
                     "container":{"inner_mm":[31,31,33],"wall_mm":[2,2,2],"protection_mm":[3,3,3],"reserved_top_mm":1}},
            "layout":{"placements":poses,"layers":layers},"external_mm":[35,35,37],"volume_mm3":35*35*37}


def test_membership_search_merges_layers_without_changing_protection_or_contents():
    original = split_stack()
    before = deepcopy(original)
    result = improve_layer_membership(original,time_limit=2,max_iterations=30)
    candidate = result["candidate"]
    assert original == before
    assert len(candidate["layout"]["layers"]) == 1
    assert candidate["external_mm"] == [35,35,24]
    assert candidate["input"]["items"] == original["input"]["items"]
    assert candidate["input"]["container"]["protection_mm"] == [3,3,3]
    assert candidate["input"]["container"]["reserved_top_mm"] == 1
    assert validate_layered(candidate["input"],candidate["layout"])["valid"]


def test_membership_search_rejects_missing_unit_and_wall_changes():
    candidate = split_stack()
    candidate["layout"]["placements"].pop()
    with pytest.raises(ValueError,match="valid generated"):
        improve_layer_membership(candidate,time_limit=.1)
    candidate = split_stack()
    candidate["layout"]["layers"][0]["wall_mm"] = 1
    with pytest.raises(ValueError,match="valid generated"):
        improve_layer_membership(candidate,time_limit=.1)
