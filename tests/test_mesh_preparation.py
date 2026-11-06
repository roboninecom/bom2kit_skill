import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")
from bom2kit.mesh_preparation import remove_empty_faces, load_print_mesh


def test_zero_area_cleanup_preserves_surface_and_volume():
    mesh = trimesh.creation.box([4, 5, 6])
    mesh.faces = np.vstack([mesh.faces, [0, 0, 1]])
    result, count = remove_empty_faces(mesh)
    assert count == 1
    assert result.is_volume
    assert result.volume == pytest.approx(120)
    assert result.bounds == pytest.approx(mesh.bounds)


def test_missing_surface_is_not_filled(tmp_path):
    mesh = trimesh.creation.box([4, 5, 6])
    mesh.update_faces(np.arange(len(mesh.faces)) != 0)
    source = tmp_path / "open.stl"
    mesh.export(source)
    result, audit = load_print_mesh(source)
    assert not result.is_volume
    assert audit["hole_filling"] is False
    assert len(result.faces) == 11
