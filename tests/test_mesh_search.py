from hashlib import sha256
import json

import pytest

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("fcl")
pytest.importorskip("scipy")
pytest.importorskip("rtree")

from bom2kit.mesh_search import solve_mesh_kit


def test_beam_search_complete_certificate_and_checkpoint(tmp_path, monkeypatch):
    mesh = trimesh.creation.box([2, 2, 2])
    source = tmp_path / "mesh.json"
    source.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(),
                                  "triangles": mesh.faces.tolist()}), encoding="utf8")
    problem = {"units": "mm", "container": {"inner_mm": [8, 3, 3]}, "clearance_mm": .5,
               "items": [{"id": "cube", "quantity": 3,
                          "mesh": {"path": str(source), "sha256": sha256(source.read_bytes()).hexdigest()}}]}
    result = solve_mesh_kit(problem, time_limit=15, beam_width=4, pitch_mm=1,
                            checkpoint_dir=tmp_path / "result")
    assert result["status"] == "validated_static_layout", result
    assert result["validation"]["valid"]
    assert len(result["placements"]) == 3
    assert (tmp_path / "result" / "layout.json").is_file()
    assert not result["search"]["optimality_proven"]
    def forbidden_voxelization(*args, **kwargs):
        raise AssertionError("Complete recipe replay must not prepare voxel geometry")
    monkeypatch.setattr(trimesh.Trimesh, "voxelized", forbidden_voxelization)
    replay = solve_mesh_kit(problem, time_limit=15, beam_width=2, pitch_mm=1,
                            seed_placements=result["placements"])
    assert replay["mode"] == "validated_seed_replay"
    assert replay["validation"]["valid"]
    bad_seed = json.loads(json.dumps(result["placements"]))
    bad_seed[0]["transform"][0][3] = -100
    with pytest.raises(ValueError, match="Invalid seed"):
        solve_mesh_kit(problem, time_limit=15, pitch_mm=1, seed_placements=bad_seed)


def test_proxy_overlap_budget_cannot_accept_solid_collisions(tmp_path):
    mesh = trimesh.creation.box([2, 2, 2])
    source = tmp_path / "mesh.json"
    source.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(),
                                  "triangles": mesh.faces.tolist()}), encoding="utf8")
    problem = {"units": "mm", "container": {"inner_mm": [3, 3, 3]},
               "items": [{"id": "cube", "quantity": 2,
                          "mesh": {"path": str(source), "sha256": sha256(source.read_bytes()).hexdigest()}}]}
    result = solve_mesh_kit(problem, time_limit=15, beam_width=4, pitch_mm=1,
                            voxel_overlap_cells=100, lookahead=True)
    assert not result["validation"]["valid"]
    assert len(result["placements"]) == 1
    assert result["search"]["voxel_overlap_cells"] == 100
    with pytest.raises(ValueError, match="voxel_overlap_cells"):
        solve_mesh_kit(problem, voxel_overlap_cells=True)


def test_partial_recipe_skips_orientations_for_fully_seeded_type(tmp_path, monkeypatch):
    mesh = trimesh.creation.box([2, 2, 2])
    source = tmp_path / "mesh.json"
    source.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(),
                                  "triangles": mesh.faces.tolist()}), encoding="utf8")
    reference = {"path": str(source), "sha256": sha256(source.read_bytes()).hexdigest()}
    problem = {"units": "mm", "container": {"inner_mm": [8, 3, 3]}, "clearance_mm": .5,
               "items": [{"id": name, "quantity": 1, "mesh": reference} for name in ["seeded", "new"]]}
    seed = [{"item_id": "seeded", "unit_id": "seeded#1",
             "transform": [[1, 0, 0, 1], [0, 1, 0, 1], [0, 0, 1, 1], [0, 0, 0, 1]]}]
    voxelize = trimesh.Trimesh.voxelized
    calls = []

    def counted(mesh, *args, **kwargs):
        calls.append(1)
        return voxelize(mesh, *args, **kwargs)

    monkeypatch.setattr(trimesh.Trimesh, "voxelized", counted)
    result = solve_mesh_kit(problem, seed_placements=seed, pitch_mm=1, time_limit=15)
    assert result["validation"]["valid"]
    assert len(calls) == 2  # One unseeded-type grid and one transformed seed grid.


def test_partial_recipe_occupancy_cache_binds_transform(tmp_path, monkeypatch):
    mesh = trimesh.creation.box([2, 2, 2])
    source = tmp_path / "mesh.json"
    source.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(),
                                  "triangles": mesh.faces.tolist()}))
    reference = {"path": str(source), "sha256": sha256(source.read_bytes()).hexdigest()}
    problem = {"units": "mm", "container": {"inner_mm": [9, 3, 3]}, "clearance_mm": .5,
               "items": [{"id": name, "quantity": 1, "mesh": reference} for name in ["seeded", "new"]]}
    seed = [{"item_id": "seeded", "unit_id": "seeded#1",
             "transform": [[1, 0, 0, 1], [0, 1, 0, 1], [0, 0, 1, 1], [0, 0, 0, 1]]}]
    cache = tmp_path / "cache"
    first = solve_mesh_kit(problem, seed_placements=seed, pitch_mm=1, cache_dir=cache)
    assert first["validation"]["valid"]
    original = trimesh.Trimesh.voxelized
    calls = []

    def counted(mesh, *args, **kwargs):
        calls.append(1)
        return original(mesh, *args, **kwargs)

    monkeypatch.setattr(trimesh.Trimesh, "voxelized", counted)
    replay = solve_mesh_kit(problem, seed_placements=seed, pitch_mm=1, cache_dir=cache)
    assert replay["validation"]["valid"]
    assert not calls
    moved = json.loads(json.dumps(seed))
    moved[0]["transform"][0][3] = 4
    changed = solve_mesh_kit(problem, seed_placements=moved, pitch_mm=1, cache_dir=cache)
    assert changed["validation"]["valid"]
    assert len(calls) == 1  # Changed world pose cannot reuse old seed occupancy.
    for cached in cache.glob("seed-*.npz"):
        cached.write_bytes(b"truncated-cache")
    recovered = solve_mesh_kit(problem, seed_placements=seed, pitch_mm=1, cache_dir=cache)
    assert recovered["validation"]["valid"]
    assert len(calls) == 2  # Corrupt optional occupancy is rebuilt, not trusted.
