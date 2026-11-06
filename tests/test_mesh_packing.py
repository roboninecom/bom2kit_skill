from hashlib import sha256
import json
from pathlib import Path

import pytest

pytest.importorskip("fcl")
trimesh = pytest.importorskip("trimesh")
pytest.importorskip("scipy")

from bom2kit.mesh_packing import solve_mesh_pair


def test_pair_search_emits_independent_mesh_certificate(tmp_path):
    meshes = [trimesh.creation.annulus(r_min=3, r_max=5, height=2, sections=24),
              trimesh.creation.cylinder(radius=1, height=2, sections=24)]
    items = []
    for index, mesh in enumerate(meshes):
        path = tmp_path / f"part-{index}.json"
        path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(),
                                    "triangles": mesh.faces.tolist()}), encoding="utf8")
        items.append({"id": str(index), "quantity": 1,
                      "mesh": {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}})
    problem = {"units": "mm", "container": {"inner_mm": [12, 12, 5]}, "clearance_mm": .1, "items": items}
    cache = {}
    result = solve_mesh_pair(problem, time_limit=5, pitch_mm=.5,voxel_cache=cache)
    assert result["status"] == "validated_static_layout", result
    assert result["validation"]["valid"]
    assert result["envelope_volume_l"] < result["separate_envelope_volume_l"]
    assert not result["search"]["optimality_proven"]
    timing = result["search"]
    assert timing["preparation_seconds"] > 0
    assert timing["search_seconds"] > 0
    assert timing["verification_seconds"] > 0
    assert timing["rotations_checked"] == 24
    assert timing["orientation_proposals"] > 0
    assert timing["proposal_seconds"] <= timing["search_seconds"]
    assert sum(timing[k] for k in ("preparation_seconds", "search_seconds", "verification_seconds")) == pytest.approx(
        timing["total_elapsed_seconds_including_validation"], abs=.01)
    reused = solve_mesh_pair(problem,time_limit=5,pitch_mm=.5,voxel_cache=cache)
    assert reused["search"]["voxel_cache_hits"] == 2
    assert reused["validation"]["valid"]
    assert reused["envelope_volume_l"] == pytest.approx(result["envelope_volume_l"])
    Path(items[0]["mesh"]["path"]).write_text("changed source")
    with pytest.raises(ValueError,match="hash"):
        solve_mesh_pair(problem,time_limit=5,pitch_mm=.5,voxel_cache=cache)
