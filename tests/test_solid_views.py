"""Catch missing viewports and unintended edits to certified mesh geometry."""
import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("vtk")
from PIL import Image

from bom2kit.solid_views import render_solid_views


def test_solid_views_keep_geometry_and_render_both_panels(tmp_path):
    mesh = trimesh.creation.annulus(r_min=8, r_max=15, height=10)
    mesh.apply_translation([25, 25, 6])
    vertices, faces = mesh.vertices.copy(), mesh.faces.copy()
    output = tmp_path / "views.png"
    render_solid_views([(mesh, 1)], output, title="Original annulus",
                       cavity=[60, 60, 25])
    np.testing.assert_array_equal(mesh.vertices, vertices)
    np.testing.assert_array_equal(mesh.faces, faces)
    pixels = np.asarray(Image.open(output).convert("RGB"))
    assert pixels.shape == (1000, 1800, 3)
    for panel in (pixels[:, :900], pixels[:, 900:]):
        # Each viewport needs a white page and substantial non-text geometry.
        assert (panel.mean(axis=2) > 245).mean() > .25
        middle = panel[180:850, 80:820]
        assert (middle.max(axis=2)-middle.min(axis=2) > 15).mean() > .10


def test_empty_solid_view_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="original mesh"):
        render_solid_views([], tmp_path / "empty.png", title="Empty")
    assert not (tmp_path / "empty.png").exists()
