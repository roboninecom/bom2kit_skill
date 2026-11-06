from bom2kit.layer_repair import repair_layer_stack
from bom2kit.models import normalize


def test_repair_changes_orientations_without_losing_membership():
    units = normalize({"container":{"inner_mm":[40,40,30]},"items":[
        {"id":"part","quantity":2,"dimensions_mm":[10,10,30],
         "allowed_rotations":[[0,1,2],[2,1,0]]}]})["units"]
    candidate = {"layout":{"layers":[{"id":"layer","inner_mm":[40,40,30],"position_mm":[0,0,0]}],
                           "placements":[{"unit_id":u["unit_id"],"layer_id":"layer"} for u in units]}}
    repairs = repair_layer_stack(units,candidate,.2,1.5,1,time_limit=1)
    assert repairs
    assert min(p["height_mm"] for p in repairs) == 13
    assert all({p["unit_id"] for layer in r["layers"] for p in layer["placements"]} == {"part#1","part#2"}
               for r in repairs)
    candidate["layout"]["placements"].pop()
    assert repair_layer_stack(units,candidate,.2,1.5,1,time_limit=1) == []
