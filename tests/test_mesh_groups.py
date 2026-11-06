from hashlib import sha256
import json

import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("fcl")
pytest.importorskip("scipy")
pytest.importorskip("rtree")
from bom2kit.mesh_groups import discover_pairs, check_workbench_axes, rank_pair_proposals, diversify_cavity_proposals
from bom2kit.mesh_motion import check_vertical_sequence
from bom2kit.group_design import design_grouped_library
from bom2kit.nested_groups import extend_groups


def test_pair_budget_explores_different_shapes_without_losing_top_candidate():
    proposals = [(-100, 0, 0), (-99, 0, 1), (-98, 1, 1), (-70, 2, 2)]
    ranked = rank_pair_proposals(proposals, 3)
    assert ranked == [(-100, 0, 0), (-98, 1, 1), (-70, 2, 2)]
    assert rank_pair_proposals(list(reversed(proposals)), 3) == ranked
    assert len(rank_pair_proposals(proposals, 100)) == len(proposals)


def test_compound_names_do_not_hide_repeated_original_shapes():
    proposals = [(-200,0,1),(-190,2,3),(-150,4,5)]
    members = {0:{"a","b"},1:{"c"},2:{"a","b"},3:{"d"},4:{"e"},5:{"f"}}
    assert rank_pair_proposals(proposals,2,members) == [(-200,0,1),(-150,4,5)]


def test_dense_cavity_proposals_get_budget_without_displacing_first_pair():
    shapes = [{"box_volume": 1000, "volume": 300, "extents": [10,10,10]},
              {"box_volume": 512, "volume": 512, "extents": [8,8,8]},
              {"box_volume": 1000, "volume": 200, "extents": [10,10,10]}]
    proposals = [(-1400,0,2),(-1300,0,0),(-700,0,1)]
    ranked = rank_pair_proposals(proposals,2)
    assert diversify_cavity_proposals(ranked,proposals,shapes,2,.5) == [proposals[0],proposals[2]]
    assert diversify_cavity_proposals(ranked,proposals,shapes,2,2) == ranked
    assert diversify_cavity_proposals(ranked,list(reversed(proposals)),shapes,2,.5) == [proposals[0],proposals[2]]


def sources(tmp_path):
    meshes = [trimesh.creation.annulus(r_min=12, r_max=20, height=8, sections=24),
              trimesh.creation.cylinder(radius=4, height=8, sections=24)]
    items = []
    for index, mesh in enumerate(meshes):
        path = tmp_path / f"part-{index}.json"
        path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist()}))
        items.append({"id": str(index), "quantity": 1,
                      "mesh": {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}})
    return items


def test_pair_discovery_uses_no_reference_and_verifies_source_assembly(tmp_path):
    library = {"units": "mm", "all_meshes_valid_volumes": True, "items": sources(tmp_path)}
    result = discover_pairs(library, tmp_path / "groups", clearance_mm=.2, time_limit=15, pair_seconds=8)
    assert len(result["alternatives"]) == 1, result["attempts"]
    group = result["alternatives"][0]
    assert group["group_box_volume_mm3"] < group["separate_box_volume_mm3"]
    assembly = group["assembly"]
    assert check_vertical_sequence(assembly["input"], assembly["layout"])["valid"]
    assert all(item["quantity"] == 1 for item in library["items"])
    policy = {"carton": {"wall_mm": 1}, "item_padding_mm": .1, "clearance_mm": .1, "allow_all_rotations": True}
    packed = design_grouped_library(library, result, policy, tmp_path / "packed", time_limit=.3)
    assert packed["status"] == "validated_grouped_geometry"
    assert len(packed["layout"]["placements"]) == 2
    assert len(packed["groups"]) == 1
    assert packed["motion"]["valid"]
    assert {p["unit_id"] for p in packed["layout"]["placements"]} == {"0#1", "1#1"}
    # An incumbent from another source library must never steer the search.
    wrong = {**packed,"source_library_sha256":"unrelated"}
    with pytest.raises(ValueError,match="different source library"):
        design_grouped_library(library,result,policy,tmp_path/"wrong-incumbent",incumbent_result=wrong)


def test_open_workbench_frame_is_explicit(tmp_path):
    items = sources(tmp_path)
    pose = np.eye(4)
    pose[:3, 3] = [25, 25, 10]
    problem = {"units": "mm", "clearance_mm": .2, "container": {"inner_mm": [50, 50, 25]}, "items": items}
    layout = {"units": "mm", "placements": [{"item_id": i["id"], "unit_id": i["id"] + "#1", "transform": pose.tolist()} for i in items]}
    result = check_workbench_axes(problem, layout)
    assert result["certificate"]["valid"]
    assert np.linalg.det(np.array(result["source_to_workbench"])[:3, :3]) == pytest.approx(1)


@pytest.mark.parametrize("radius",[2,4])
def test_nested_groups_expand_original_units_without_reusing_unavailable_parts(tmp_path,radius):
    items = sources(tmp_path)
    mesh = trimesh.creation.cylinder(radius=radius,height=2*radius,sections=24)
    path = tmp_path/"smaller-cylinder.json"
    path.write_text(json.dumps({"units":"mm","vertices_mm":mesh.vertices.tolist(),"triangles":mesh.faces.tolist()}))
    items[1]["mesh"] = {"path":str(path),"sha256":sha256(path.read_bytes()).hexdigest()}
    items[1]["quantity"] = 2
    library = {"units":"mm","all_meshes_valid_volumes":True,"items":items}
    portfolio = discover_pairs(library,tmp_path/"pairs",clearance_mm=.2,time_limit=15,pair_seconds=5,max_pairs=1)
    nested = extend_groups(library,portfolio,tmp_path/"nested",time_limit=15,pair_seconds=5,max_pairs=1)
    assert nested["alternatives"], nested
    group = nested["alternatives"][0]
    assert sorted(group["members"]) == ["0","1","1"]
    assert {p["unit_id"] for p in group["layout"]["placements"]} == {"0#1","1#1","1#2"}
    assert check_vertical_sequence(group["assembly"]["input"],group["assembly"]["layout"])["valid"]
