"""Independent checks for conservative vertical insertion certificates."""

from hashlib import sha256
import json
from unittest.mock import patch

import pytest

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("fcl")

from bom2kit.mesh_motion import check_vertical_sequence
from bom2kit.mesh_validation import validate_mesh_layout
from bom2kit.report import fingerprint


def fixture(tmp_path):
    mesh = trimesh.creation.box([2, 2, 2])
    path = tmp_path / "cube.json"
    path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist()}))
    problem = {"units": "mm", "container": {"inner_mm": [10,10,10]}, "clearance_mm": .1,
               "items": [{"id": "A", "quantity": 2, "mesh": {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}}]}
    layout = {"units": "mm", "placements": [
        {"item_id": "A", "unit_id": f"A#{i + 1}", "transform": [[1,0,0,2],[0,1,0,2],[0,0,1,z],[0,0,0,1]]}
        for i,z in enumerate((2,6))]}
    return problem, layout


def test_stack_removes_top_first_and_packs_bottom_first(tmp_path):
    problem, layout = fixture(tmp_path)
    result = check_vertical_sequence(problem, layout)
    assert result["valid"]
    assert [s["unit_ids"] for s in result["removal_sequence"]] == [["A#2"], ["A#1"]]
    assert [s["unit_ids"] for s in result["packing_sequence"]] == [["A#1"], ["A#2"]]
    assert all(s["direction"] == "-Z" for s in result["packing_sequence"])
    assert not result["production_validated"]
    assert result["input_sha256"] == fingerprint(problem)
    assert result["layout_sha256"] == fingerprint(layout)


def test_side_by_side_xy_pruning_is_translation_invariant(tmp_path):
    problem, layout = fixture(tmp_path)
    layout["placements"][1]["transform"][0][3] = 6
    result = check_vertical_sequence(problem, layout)
    assert result["valid"]
    assert result["distance_queries"] == 0


def test_invalid_static_layout_cannot_get_motion_certificate(tmp_path):
    problem, layout = fixture(tmp_path)
    layout["placements"][1]["transform"][2][3] = 2
    result = check_vertical_sequence(problem, layout)
    assert not result["valid"]
    assert result["reason"] == "Static layout is invalid"


def test_group_names_and_members_are_unambiguous(tmp_path):
    problem, layout = fixture(tmp_path)
    for groups in ([], {"A#1": ["A#1", "A#2"]}, {"group": ["missing"]},
                   {"group": ["A#1", "A#1"]}, {"first": ["A#1"], "second": ["A#1"]}):
        with pytest.raises(ValueError):
            check_vertical_sequence(problem, layout, groups=groups)
    result = check_vertical_sequence(problem, layout, groups={"prepared_pair": ["A#1", "A#2"]})
    assert result["valid"]
    assert len(result["packing_sequence"]) == 1
    assert result["groups_sha256"] == fingerprint({"prepared_pair": ["A#1", "A#2"]})


def test_source_change_after_static_validation_is_rejected(tmp_path):
    problem, layout = fixture(tmp_path)
    checked = validate_mesh_layout(problem, layout)

    def change_source(*args, **kwargs):
        path = tmp_path / "cube.json"
        path.write_text(path.read_text() + " ")
        return checked

    with patch("bom2kit.mesh_motion.validate_mesh_layout", side_effect=change_source):
        with pytest.raises(ValueError, match="changed"):
            check_vertical_sequence(problem, layout)


def test_motion_budget_is_finite_typed_and_source_bound(tmp_path):
    problem, layout = fixture(tmp_path)
    for budget in (True, "1", float("nan"), float("inf"), 0):
        with pytest.raises(ValueError):
            check_vertical_sequence(problem, layout, time_limit=budget)
    before = check_vertical_sequence(problem, layout)
    layout["placements"][1]["transform"][0][3] = 6
    after = check_vertical_sequence(problem, layout)
    assert before["layout_sha256"] != after["layout_sha256"]


def test_continuous_distance_steps_handle_overlapping_aabbs(tmp_path):
    pytest.importorskip("rtree")
    shapes = {"tube": trimesh.creation.annulus(r_min=2, r_max=3, height=6),
              "cube": trimesh.creation.box([1,1,1])}
    items, placements = [], []
    for name, mesh in shapes.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist()}))
        items.append({"id": name, "mesh": {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}})
        placements.append({"item_id": name, "unit_id": name + "#1",
                           "transform": [[1,0,0,5],[0,1,0,5],[0,0,1,4],[0,0,0,1]]})
    result = check_vertical_sequence({"units": "mm", "container": {"inner_mm": [10,10,10]},
                                      "clearance_mm": .1, "items": items},
                                     {"units": "mm", "placements": placements})
    assert result["valid"]
    assert result["distance_queries"] > 0
    assert result["removal_sequence"][0]["unit_ids"] == ["tube#1"]
