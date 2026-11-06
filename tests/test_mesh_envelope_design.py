from hashlib import sha256
import json

import pytest

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("fcl")
pytest.importorskip("rtree")
from bom2kit.mesh_envelope_design import design_mesh_envelopes


def test_oblique_source_frame_becomes_valid_rigid_packing(tmp_path):
    mesh = trimesh.creation.box([7, 11, 17])
    mesh.apply_transform(trimesh.transformations.rotation_matrix(.37, [1, 2, 3]))
    mesh.apply_translation([60, -90, 40])
    source = tmp_path / "mesh.json"
    source.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist()}))
    library = {"units": "mm", "all_meshes_valid_volumes": True, "items": [
        {"id": "oblique", "quantity": 3, "contents": {"screw": 37},
         "mesh": {"path": str(source), "sha256": sha256(source.read_bytes()).hexdigest()}}]}
    policy = {"carton": {"wall_mm": 1.5, "protection_mm": 2}, "item_padding_mm": 1,
              "clearance_mm": .1, "allow_all_rotations": True}
    result = design_mesh_envelopes(library, policy, time_limit=.3)
    assert result["status"] == "validated_mesh_envelope_baseline"
    assert result["validation"]["valid"]
    assert result["motion"]["valid"]
    assert len(result["layout"]["placements"]) == 3
    assert result["envelope_design"]["search"]["reference_used"] is False
    from bom2kit.bom import reconcile_bom
    assert reconcile_bom({"components": [{"id": "screw", "quantity": 111}]}, result["input"])["complete"]
