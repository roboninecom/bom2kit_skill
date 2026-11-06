from hashlib import sha256
import json

import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("fcl")
pytest.importorskip("scipy")
pytest.importorskip("rtree")
from bom2kit.mesh_groups import discover_pairs, check_workbench_axes
from bom2kit.mesh_motion import check_vertical_sequence
from bom2kit.group_design import design_grouped_library


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


def test_open_workbench_frame_is_explicit(tmp_path):
    items = sources(tmp_path)
    pose = np.eye(4)
    pose[:3, 3] = [25, 25, 10]
    problem = {"units": "mm", "clearance_mm": .2, "container": {"inner_mm": [50, 50, 25]}, "items": items}
    layout = {"units": "mm", "placements": [{"item_id": i["id"], "unit_id": i["id"] + "#1", "transform": pose.tolist()} for i in items]}
    result = check_workbench_axes(problem, layout)
    assert result["certificate"]["valid"]
    assert np.linalg.det(np.array(result["source_to_workbench"])[:3, :3]) == pytest.approx(1)
