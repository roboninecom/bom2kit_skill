from copy import deepcopy
from hashlib import sha256
import json

import pytest

np = pytest.importorskip("numpy")
trimesh = pytest.importorskip("trimesh")
pytest.importorskip("fcl")
pytest.importorskip("rtree")

from bom2kit.mesh_validation import validate_mesh_layout


def problem_and_layout(tmp_path, meshes):
    items, placements = [], []
    for index, mesh in enumerate(meshes):
        iid = f"part-{index}"
        path = tmp_path / f"{iid}.json"
        path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist()}), encoding="utf-8")
        items.append({"id": iid, "quantity": 1, "mesh": {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}})
        transform = np.eye(4)
        transform[:3, 3] = [10, 10, 10]
        placements.append({"item_id": iid, "unit_id": f"{iid}#1", "transform": transform.tolist()})
    return {"units": "mm", "container": {"inner_mm": [30, 30, 30]}, "items": items}, {"units": "mm", "placements": placements}


def test_true_cavity_accepted_but_enclosed_solid_rejected(tmp_path, monkeypatch):
    outer = trimesh.creation.box([10, 10, 10])
    inner = trimesh.creation.box([6, 6, 6])
    inner.invert()
    shell = trimesh.util.concatenate([outer, inner])
    small = trimesh.creation.box([2, 2, 2])
    problem, layout = problem_and_layout(tmp_path, [shell, small])
    result = validate_mesh_layout(problem, layout)
    assert result["valid"], result
    # Same pose in a solid block has no intersecting surfaces, but is invalid.
    problem, layout = problem_and_layout(tmp_path, [outer, small])
    result = validate_mesh_layout(problem, layout)
    assert not result["valid"]
    # Some FCL convex representations already detect enclosure. Verify that the
    # independent parity safeguard also detects it when surfaces report clear.
    monkeypatch.setattr(trimesh.collision.CollisionManager, "in_collision_other", lambda *args, **kwargs: False)
    result = validate_mesh_layout(problem, layout)
    assert any("Enclosed solid collision" in error for error in result["errors"])


def test_surface_overlap_rejected(tmp_path):
    problem, layout = problem_and_layout(tmp_path, [trimesh.creation.box([4, 4, 4])] * 2)
    layout["placements"][1]["transform"][0][3] += 3
    result = validate_mesh_layout(problem, layout)
    assert not result["valid"]
    assert any("Surface collision" in e for e in result["errors"])


def test_aabb_shortcut_preserves_diagonal_clearance(tmp_path):
    problem, layout = problem_and_layout(tmp_path, [trimesh.creation.box([2, 2, 2])] * 2)
    layout["placements"][1]["transform"][0][3] += 4
    layout["placements"][1]["transform"][1][3] += 4
    problem["clearance_mm"] = 2.5
    result = validate_mesh_layout(problem, layout)
    assert result["valid"]
    assert result["pair_checks"]["aabb_separated_pairs"] == 1
    problem["clearance_mm"] = 3
    result = validate_mesh_layout(problem, layout)
    assert not result["valid"]
    assert result["pair_checks"]["narrow_phase_pairs"] == 1
    assert any("Pair clearance" in error for error in result["errors"])


def test_source_units_rigidity_quantities_and_containment(tmp_path):
    problem, layout = problem_and_layout(tmp_path, [trimesh.creation.box([4, 4, 4])])
    assert validate_mesh_layout(problem, layout)["valid"]
    changed = deepcopy(problem)
    changed["items"][0]["mesh"]["sha256"] = "wrong"
    assert not validate_mesh_layout(changed, layout)["valid"]
    changed = deepcopy(layout)
    changed["placements"][0]["transform"][0][0] = 2
    assert not validate_mesh_layout(problem, changed)["valid"]
    changed["placements"][0]["transform"][0][0] = -1
    assert not validate_mesh_layout(problem, changed)["valid"]
    changed = deepcopy(layout)
    changed["placements"][0]["transform"][0][3] = 0
    assert not validate_mesh_layout(problem, changed)["valid"]
    changed = deepcopy(layout)
    changed["placements"].append(deepcopy(changed["placements"][0]))
    assert not validate_mesh_layout(problem, changed)["valid"]
    assert not validate_mesh_layout(problem, {"units": "mm", "placements": []})["valid"]
    assert not validate_mesh_layout(problem, {**layout, "units": "inch"})["valid"]


def test_disconnected_component_enclosure_and_clearance(tmp_path):
    large = trimesh.creation.box([6, 6, 6])
    inside = trimesh.creation.box([1, 1, 1])
    outside = inside.copy()
    outside.apply_translation([8, 0, 0])
    # First component is outside. The second must still be checked for enclosure.
    composite = trimesh.util.concatenate([outside, inside])
    problem, layout = problem_and_layout(tmp_path, [large, composite])
    assert not validate_mesh_layout(problem, layout)["valid"]
    problem, layout = problem_and_layout(tmp_path, [inside, outside])
    problem["clearance_mm"] = 8
    assert not validate_mesh_layout(problem, layout)["valid"]


def test_open_mesh_rejected(tmp_path):
    mesh = trimesh.creation.box([4, 4, 4])
    mesh.update_faces(np.arange(len(mesh.faces) - 1))
    problem, layout = problem_and_layout(tmp_path, [mesh])
    assert not validate_mesh_layout(problem, layout)["valid"]


def test_reserved_space_and_malformed_collections_rejected(tmp_path):
    problem, layout = problem_and_layout(tmp_path, [trimesh.creation.box([4, 4, 4])])
    problem["container"]["reserved_top_mm"] = 20
    assert not validate_mesh_layout(problem, layout)["valid"]
    problem["container"]["reserved_top_mm"] = 0
    problem["clearance_mm"] = True
    assert not validate_mesh_layout(problem, layout)["valid"]
    problem["clearance_mm"] = 0
    assert not validate_mesh_layout(problem, {"units": "mm", "placements": None})["valid"]
    assert not validate_mesh_layout({**problem, "items": [None]}, layout)["valid"]
