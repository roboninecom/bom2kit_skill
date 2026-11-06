import json
from hashlib import sha256

import pytest

trimesh = pytest.importorskip('trimesh')
pytest.importorskip('fcl')
pytest.importorskip('matplotlib')

from bom2kit.mesh_report import render_mesh_report
from bom2kit.report import fingerprint


def test_mesh_view_keeps_millimetres_and_binds_image_to_certificate(tmp_path):
    mesh = trimesh.creation.box([2, 2, 2])
    source = tmp_path / 'part.json'
    source.write_text(json.dumps({'units': 'mm', 'vertices_mm': mesh.vertices.tolist(),
                                 'triangles': mesh.faces.tolist()}))
    problem = {'units': 'mm', 'container': {'inner_mm': [10, 20, 30]}, 'items': [
        {'id': 'cube', 'quantity': 1, 'mesh': {'path': str(source), 'sha256': sha256(source.read_bytes()).hexdigest()}}]}
    layout = {'units': 'mm', 'placements': [{'item_id': 'cube', 'unit_id': 'cube#1',
        'transform': [[1, 0, 0, 2], [0, 1, 0, 2], [0, 0, 1, 2], [0, 0, 0, 1]]}]}
    output = tmp_path / 'report'
    html = render_mesh_report(problem, layout, output).read_text()
    assert '10 x 20 x 30 mm' in html  # matplotlib must not normalize shared dimension data
    evidence = json.loads((output / 'mesh-render.json').read_text())
    assert evidence['input_sha256'] == fingerprint(problem)
    assert evidence['layout_sha256'] == fingerprint(layout)
    assert evidence['image_sha256'] == sha256((output / 'mesh-views.png').read_bytes()).hexdigest()
    layout['placements'] = []
    with pytest.raises(ValueError, match='Cannot render'):
        render_mesh_report(problem, layout, tmp_path / 'invalid')
    assert not (tmp_path / 'invalid').exists()
