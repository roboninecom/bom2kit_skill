from bom2kit.layer_sequences import search_sequences
from bom2kit.layered_design import validate_layered
from bom2kit.models import normalize
import pytest


@pytest.mark.parametrize("mode",["bottom_left","portfolio"])
def test_sequence_search_avoids_a_dense_layer_that_leaves_a_tall_remainder(mode):
    items = [{"id":"large","quantity":1,"dimensions_mm":[12,12,12],"allowed_rotations":"fixed"},
             {"id":"medium","quantity":3,"dimensions_mm":[10,10,5],"allowed_rotations":"fixed"},
             {"id":"small","quantity":4,"dimensions_mm":[8,8,10],"allowed_rotations":"fixed"}]
    units = normalize({"items":items,"container":{"inner_mm":[100]*3}})["units"]
    result = search_sequences(units,20,20,1,0,1,[5,10,12],time_limit=1,incumbent_height=33,placement_score=mode)
    assert result["height_mm"] == 26
    layers,poses,z = [],[],0
    for index,packed in enumerate(result["layers"]):
        lid = str(index)
        height = packed["usable_mm"][2]
        layers.append({"id":lid,"inner_mm":[20,20,height],"position_mm":[0,0,z],"wall_mm":1})
        poses.extend({**p,"layer_id":lid,"position_mm":[p["position_mm"][0]+1,p["position_mm"][1]+1,z+1]}
                     for p in packed["placements"])
        z += height+2
    problem = {"items":items,"inner_wall_mm":1,"container":{"inner_mm":[22,22,z]}}
    assert validate_layered(problem,{"layers":layers,"placements":poses})["valid"]


def test_incomplete_prefix_never_becomes_a_successful_stack():
    items = [{"id":"too_wide","dimensions_mm":[30,30,1],"allowed_rotations":"fixed"}]
    units = normalize({"items":items,"container":{"inner_mm":[100]*3}})["units"]
    result = search_sequences(units,20,20,1,0,1,[1],time_limit=.1)
    assert result["layers"] is None
    assert result["height_mm"] is None
