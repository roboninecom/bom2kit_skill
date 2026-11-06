"""Render source triangles at validated rigid poses, without visual fitting."""

import base64
from hashlib import sha256
from html import escape
import json
from pathlib import Path

from .mesh_validation import validate_mesh_layout
from .report import fingerprint


def render_mesh_report(problem, layout, output_dir):
    """Write a static geometric review; never label it an insertion instruction."""
    checked = validate_mesh_layout(problem, layout)
    if not checked['valid']:
        raise ValueError('Cannot render an accepted mesh review: ' + '; '.join(checked['errors']))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import numpy as np
    import trimesh

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    items = {item['id']: item for item in problem['items']}
    geometries = {}
    for iid, item in items.items():
        ref = item['mesh']
        path = Path(ref['path'])
        if path.suffix.lower() == '.3mf':
            from .mesh_geometry import load_instance_mesh
            geometries[iid] = load_instance_mesh(path, ref['instance_id'], ref.get('frame', 'object'))
        else:
            geometries[iid] = json.loads(path.read_text(encoding='utf-8-sig'))
    dimensions = np.asarray(problem['container']['inner_mm'], dtype=float)
    if dimensions.ndim == 0:
        dimensions = np.repeat(dimensions, 3)
    fig = plt.figure(figsize=(12, 8), facecolor='white')
    views = [('Isometric', 28, -55), ('Top', 90, -90), ('Front', 0, -90), ('Side', 0, 0)]
    colors = plt.get_cmap('tab20')
    for index, (title, elevation, azimuth) in enumerate(views, 1):
        ax = fig.add_subplot(2, 2, index, projection='3d' if index == 1 else None)
        projected, depths, face_colors = [], [], []
        plane = {2: (0, 1, 2, 1), 3: (0, 2, 1, -1), 4: (1, 2, 0, 1)}.get(index)
        if index == 1:
            ax.set_proj_type('ortho')
        for pi, placement in enumerate(layout['placements']):
            geometry = geometries[placement['item_id']]
            mesh = trimesh.Trimesh(vertices=geometry['vertices_mm'], faces=geometry['triangles'], process=False)
            mesh.apply_transform(np.asarray(placement['transform'], dtype=float))
            if index == 1:
                collection = Poly3DCollection(mesh.triangles, facecolor=colors(pi % 20),
                                              edgecolor='none', linewidth=0, rasterized=True)
                ax.add_collection3d(collection)
                middle = mesh.bounds.mean(axis=0)
                ax.text(*middle, str(pi + 1), fontsize=6, color='#101820')
            else:
                a, b, depth, sign = plane
                projected.append(mesh.triangles[:, :, [a, b]])
                depths.append(mesh.triangles[:, :, depth].mean(axis=1) * sign)
                face_colors.extend([colors(pi % 20)] * len(mesh.faces))
        if index == 1:
            ax.set(xlim=(0, dimensions[0]), ylim=(0, dimensions[1]), zlim=(0, dimensions[2]))
            ax.set_box_aspect(dimensions.copy())
            ax.view_init(elevation, azimuth)
            ax.set_xlabel('X (mm)', fontsize=8)
            ax.set_ylabel('Y (mm)', fontsize=8)
            ax.set_zlabel('Z (mm)', fontsize=8)
        else:
            a, b, _, _ = plane
            order = np.argsort(np.concatenate(depths), kind='stable')
            ax.add_collection(PolyCollection(np.concatenate(projected)[order],
                                            facecolors=np.asarray(face_colors)[order], edgecolors='none'))
            ax.set(xlim=(0, dimensions[a]), ylim=(0, dimensions[b]))
            ax.set_aspect('equal')
            ax.set_xlabel('XYZ'[a] + ' (mm)', fontsize=8)
            ax.set_ylabel('XYZ'[b] + ' (mm)', fontsize=8)
        ax.set_title(title, fontsize=11)
        ax.tick_params(labelsize=7)
    fig.suptitle(f"Static mesh placement: {checked['placed_units']} / {checked['expected_units']} units", fontsize=15)
    fig.subplots_adjust(top=.91, bottom=.06, left=.03, right=.97, hspace=.12, wspace=.08)
    picture = output / 'mesh-views.png'
    fig.savefig(picture, dpi=140)
    plt.close(fig)
    rows = ''.join(f'<tr><td>{i + 1}</td><td>{escape(p["unit_id"])}</td></tr>'
                   for i, p in enumerate(layout['placements']))
    warnings = checked['limitations'] + problem.get('limitations', [])
    image = base64.b64encode(picture.read_bytes()).decode('ascii')
    text = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Mesh packing review</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:32px auto;padding:0 24px;color:#18364b}}img{{width:100%}}td,th{{padding:6px 14px;text-align:left;border-bottom:1px solid #ddd}}.warning{{background:#fff3da;padding:14px}}</style>
<h1>Static mesh packing review</h1><p>{checked['placed_units']} / {checked['expected_units']} units validated.
Declared container: {' x '.join(f'{v:g}' for v in dimensions)} mm.
Pair clearance: {problem.get('clearance_mm', 0):g} mm.</p>
<p class="warning">These views show the checked final poses. They do not establish packing order,
support, box wall allowances, or complete-kit acceptance.</p>
<img src="data:image/png;base64,{image}" alt="Four orthographic views of the actual placed source triangles">
<h2>Unit key</h2><table><tr><th>Number</th><th>Unit</th></tr>{rows}</table>
<h2>Scope</h2><ul>{''.join('<li>' + escape(str(w)) + '</li>' for w in warnings)}</ul>
<p>Input SHA-256: {fingerprint(problem)}<br>Layout SHA-256: {fingerprint(layout)}</p></html>'''
    target = output / 'mesh-review.html'
    target.write_text(text, encoding='utf-8')
    (output / 'mesh-validation.json').write_text(json.dumps(checked, indent=2), encoding='utf-8')
    (output / 'mesh-render.json').write_text(json.dumps({
        'input_sha256': fingerprint(problem), 'layout_sha256': fingerprint(layout),
        'image_sha256': sha256(picture.read_bytes()).hexdigest(),
    }, indent=2), encoding='utf-8')
    return target
