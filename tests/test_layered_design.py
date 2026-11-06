from copy import deepcopy
from bom2kit.models import normalize
from bom2kit.layered_design import design_layers, validate_layered


def test_supported_layers_preserve_counts_walls_and_detect_floating_cartons():
    request = {"units":"mm","items":[{"id":"box","quantity":12,"dimensions_mm":[20,20,20],"allowed_rotations":"fixed"}],
               "policy":{"wall_mm":2,"protection_mm":3,"inner_wall_mm":1.5,"gap_mm":.2}}
    units = normalize({"items":request["items"],"container":{"inner_mm":[300]*3}})["units"]
    result = design_layers(request,units,time_limit=1)
    best = result["candidate"]
    assert best and best["validation"]["valid"]
    assert len(best["layout"]["layers"]) >= 2
    assert len(best["layout"]["placements"]) == 12
    assert all(abs((d+2*l["wall_mm"])-round(d+2*l["wall_mm"])) < 1e-8
               for l in best["layout"]["layers"] for d in l["inner_mm"])
    broken = deepcopy(best["layout"])
    broken["layers"][1]["position_mm"][2] += 1
    assert not validate_layered(best["input"],broken)["valid"]
    broken = deepcopy(best["layout"])
    broken["layers"][0]["wall_mm"] = .5
    assert not validate_layered(best["input"],broken)["valid"]
    broken = deepcopy(best["layout"])
    broken["placements"].pop()
    assert not validate_layered(best["input"],broken)["valid"]


def test_adjacent_stacks_allow_different_heights_but_reject_unsupported_top():
    problem = {"units":"mm", "inner_wall_mm":1.5,
               "container":{"inner_mm":[46,23,66]},
               "items":[{"id":"part","quantity":3,"dimensions_mm":[20,20,20],"allowed_rotations":"fixed"}]}
    positions = [[0,0,0],[23,0,0],[0,0,23]]
    layers = [{"id":str(i),"inner_mm":[20,20,20],"wall_mm":1.5,"position_mm":p}
              for i,p in enumerate(positions)]
    poses = [{"item_id":"part","unit_id":f"part#{i+1}","layer_id":str(i),
              "position_mm":[x+1.5 for x in p],"dimensions_mm":[20,20,20],"rotation":[0,1,2]}
             for i,p in enumerate(positions)]
    layout = {"layers":layers,"placements":poses}
    assert validate_layered(problem,layout)["valid"]
    layout["layers"][2]["position_mm"][2] += 1
    layout["placements"][2]["position_mm"][2] += 1
    assert not validate_layered(problem,layout)["valid"]
