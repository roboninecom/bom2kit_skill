from copy import deepcopy
from hashlib import sha256
import json

import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("fcl")
from bom2kit.assembly_plan import build_assembly_plan


def two_cartons(tmp_path):
    mesh = trimesh.creation.box([8,8,8])
    path = tmp_path/"cube.json"
    path.write_text(json.dumps({"units":"mm","vertices_mm":mesh.vertices.tolist(),"triangles":mesh.faces.tolist()}))
    ref = {"path":str(path),"sha256":sha256(path.read_bytes()).hexdigest()}
    container = {"inner_mm":[13,13,26],"wall_mm":1}
    problem = {"units":"mm","container":container,"clearance_mm":.2,
               "items":[{"id":"cube","quantity":2,"mesh":ref}]}
    layers, slots, poses = [], [], []
    for index,z in enumerate((0,13),1):
        uid,lid = f"cube#{index}",f"carton-{index}"
        layers.append({"id":lid,"position_mm":[0,0,z],"inner_mm":[10,10,10],"wall_mm":1.5})
        slots.append({"unit_id":uid,"item_id":"cube","layer_id":lid,"position_mm":[1.5,1.5,z+1.5],
                      "dimensions_mm":[10,10,10],"rotation":[0,1,2]})
        transform = np.eye(4)
        transform[:3,3] = [6.5,6.5,z+6.5]
        poses.append({"unit_id":uid,"item_id":"cube","transform":transform.tolist()})
    carton = {"input":{"units":"mm","container":container,"inner_wall_mm":1.5,
                        "items":[{"id":"cube","quantity":2,"dimensions_mm":[10,10,10]}]},
              "layout":{"layers":layers,"placements":slots},"external_mm":[15,15,28]}
    result = {"status":"validated_mesh_envelope_baseline","input":problem,"layout":{"units":"mm","placements":poses},
              "envelope_design":{"candidate":carton}}
    return result,{"components":[{"id":"cube","quantity":2}]}


def test_plan_binds_complete_cartons_and_rejects_unexplained_group(tmp_path):
    result,bom = two_cartons(tmp_path)
    plan = build_assembly_plan(result,bom)
    assert plan["status"] == "validated_geometric_assembly_plan"
    assert not plan["production_validated"]
    assert [c["unit_ids"] for c in plan["cartons_in_outer_insertion_order"]] == [["cube#1"],["cube#2"]]
    broken = deepcopy(result)
    broken["groups"] = {"combined":["cube#1","cube#2"]}
    with pytest.raises(ValueError,match="template"):
        build_assembly_plan(broken,bom)
    with pytest.raises(ValueError,match="BOM"):
        build_assembly_plan(result,{"components":[{"id":"cube","quantity":3}]})
    broken = deepcopy(result)
    broken["envelope_design"]["candidate"]["external_mm"][0] -= 1
    with pytest.raises(ValueError,match="exterior"):
        build_assembly_plan(broken,bom)
    # Valid outer geometry is insufficient if the part-to-carton association changes.
    broken = deepcopy(result)
    broken["layout"]["placements"][0]["transform"][2][3] = 19.5
    broken["layout"]["placements"][1]["transform"][2][3] = 6.5
    with pytest.raises(ValueError,match="assigned inner carton"):
        build_assembly_plan(broken,bom)
