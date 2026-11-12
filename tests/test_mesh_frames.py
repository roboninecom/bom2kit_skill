import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")
from bom2kit.mesh_frames import packing_bounds


def test_frame_never_worsens_source_axes_and_keeps_a_proper_rotation(monkeypatch):
    mesh = trimesh.creation.box([8,15,30])
    poor = trimesh.transformations.rotation_matrix(.03,[0,0,1])
    monkeypatch.setattr(trimesh.bounds,"oriented_bounds",lambda m:(poor,[1,1,1]))
    frame,size = packing_bounds(mesh)
    assert np.allclose(frame,np.eye(4))
    assert np.allclose(size,[8,15,30])
    assert np.linalg.det(frame[:3,:3]) == pytest.approx(1)


def test_frame_still_finds_smaller_bounds_for_rotated_source():
    mesh = trimesh.creation.box([8,15,30])
    mesh.apply_transform(trimesh.transformations.rotation_matrix(.3,[0,0,1]))
    frame,size = packing_bounds(mesh)
    assert np.prod(size) == pytest.approx(8*15*30)
    assert np.prod(size) < np.prod(mesh.extents)
    assert np.allclose(size,np.ptp(trimesh.transform_points(mesh.vertices,frame),axis=0))


def test_cached_bounds_are_isolated_from_callers_and_changed_geometry():
    mesh=trimesh.creation.box([9,17,31])
    frame,size=packing_bounds(mesh)
    frame[:3,3]=999;size[:]=999
    fresh_frame,fresh_size=packing_bounds(mesh)
    assert np.allclose(fresh_frame,np.eye(4)) and np.allclose(fresh_size,[9,17,31])
    mesh.apply_scale([2,1,1])
    _,changed=packing_bounds(mesh)
    assert np.allclose(changed,[18,17,31])
