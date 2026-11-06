"""CLI recipe replay must validate the new manifest, not trust a saved status."""
from hashlib import sha256
import json
import pytest

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("fcl")
pytest.importorskip("scipy")
pytest.importorskip("rtree")

from bom2kit.cli import main


def test_mesh_recipe_replay_rejects_changed_cavity(tmp_path):
    mesh = trimesh.creation.box([2, 2, 2])
    source = tmp_path / "mesh.json"
    source.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(),
                                  "triangles": mesh.faces.tolist()}))
    problem = {"units": "mm", "container": {"inner_mm": [4, 4, 4]},
               "items": [{"id": "part", "mesh": {"path": str(source),
                            "sha256": sha256(source.read_bytes()).hexdigest()}}]}
    seed = {"units": "mm", "status": "validated_static_layout", "placements": [
        {"item_id": "part", "unit_id": "part#1",
         "transform": [[1, 0, 0, 2], [0, 1, 0, 2], [0, 0, 1, 2], [0, 0, 0, 1]]}]}
    job, recipe = tmp_path / "input.json", tmp_path / "recipe.json"
    job.write_text(json.dumps(problem))
    recipe.write_text(json.dumps(seed))
    args = ["mesh-solve", str(job), "--output", str(tmp_path / "out"), "--seed-layout", str(recipe)]
    assert main(args) == 0
    assert json.loads((tmp_path / "out/validation.json").read_text())["valid"]
    problem["container"]["inner_mm"] = [2, 2, 2]
    job.write_text(json.dumps(problem))
    assert main(args) == 2
    assert not json.loads((tmp_path / "out/validation.json").read_text())["valid"]
