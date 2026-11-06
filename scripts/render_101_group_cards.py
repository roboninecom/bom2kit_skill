"""Render source-bound SO101 assembly cards from checked hierarchical paths."""
import base64
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from mpl_toolkits.mplot3d import proj3d
from matplotlib.ticker import MaxNLocator
from bom2kit.report import fingerprint

root = Path('packaging-results/so-arm-101/regrouped-without-camera')
problem = json.loads((root / 'problem.json').read_text())
layout = json.loads((root / 'layout.json').read_text())
bindings = json.loads((root / 'packing-recipe-bindings.json').read_text())
motion = json.loads((root / 'motion-grouped-validation.json').read_text())
assert fingerprint(problem) == bindings['input_sha256']
assert fingerprint(layout) == bindings['layout_sha256']
items = {item['id']: item for item in problem['items']}
triangles = {}
for pose in layout['placements']:
    ref = items[pose['item_id']]['mesh']
    raw = Path(ref['path']).read_bytes()
    assert sha256(raw).hexdigest() == ref['sha256']
    data = json.loads(raw)
    transform = np.array(pose['transform'])
    vertices = np.array(data['vertices_mm']) @ transform[:3, :3].T + transform[:3, 3]
    triangles[pose['unit_id']] = vertices[np.array(data['triangles'])]
colors = plt.get_cmap('tab10')
size = np.array(problem['container']['inner_mm'])

def top_view(axis, active, numbers=None):
    faces, depths, shades = [], [], []
    for uid, geometry in triangles.items():
        faces.append(geometry[:, :, :2])
        depths.append(geometry[:, :, 2].mean(axis=1))
        color = colors(active.index(uid) % 10) if uid in active else (0.88, 0.90, 0.92, 1)
        shades.extend([color] * len(geometry))
    order = np.argsort(np.concatenate(depths), kind='stable')
    axis.add_collection(PolyCollection(np.concatenate(faces)[order], facecolors=np.array(shades)[order], edgecolors='none'))
    axis.set(xlim=(0, size[0]), ylim=(0, size[1]), xlabel='X (mm)', ylabel='Y (mm)', aspect='equal')
    if numbers:
        for number, members in numbers:
            geometry = np.concatenate([triangles[uid] for uid in members])
            center = (geometry.reshape(-1, 3).min(axis=0) + geometry.reshape(-1, 3).max(axis=0)) / 2
            axis.text(center[0], center[1], str(number), ha='center', va='center', fontsize=10, fontweight='bold',
                      bbox={'boxstyle':'circle,pad=.25', 'fc':'white', 'ec':'#18364b', 'lw':1})

images = []
cards = []
for index, (name, group) in enumerate(bindings['groups'].items(), 1):
    order = group['sequence']
    fig = plt.figure(figsize=(12, 5.2), facecolor='white')
    axis = fig.add_subplot(1, 2, 1, projection='3d')
    all_vertices = np.concatenate([triangles[uid].reshape(-1, 3) for uid in order])
    low, high = all_vertices.min(axis=0), all_vertices.max(axis=0)
    label_centers = []
    for ordinal, uid in enumerate(order, 1):
        geometry = triangles[uid]
        axis.add_collection3d(Poly3DCollection(geometry, facecolor=colors((ordinal - 1) % 10), edgecolor='none'))
        center = (geometry.reshape(-1, 3).min(axis=0) + geometry.reshape(-1, 3).max(axis=0)) / 2
        label_centers.append((ordinal, center))
    axis.set(xlim=(low[0]-2, high[0]+2), ylim=(low[1]-2, high[1]+2), zlim=(low[2]-2, high[2]+2), xlabel='X', ylabel='Y', zlabel='Z')
    axis.set_box_aspect(high-low+4)
    axis.set_proj_type('ortho')
    axis.view_init(25, -55)
    for coordinate_axis in (axis.xaxis, axis.yaxis, axis.zaxis):
        coordinate_axis.set_major_locator(MaxNLocator(3))
    for ordinal, center in label_centers:
        x, y, _ = proj3d.proj_transform(*center, axis.get_proj())
        axis.annotate(str(ordinal), (x, y), ha='center', va='center', fontsize=11,
                      weight='bold', zorder=100,
                      bbox={'boxstyle':'circle,pad=.2', 'fc':'white', 'ec':'#18364b'})
    direction = '+X' if np.allclose(group['insertion_direction_carton'], [1,0,0]) else '-Z'
    axis.set_title(f'Group {index}: assemble {direction} in numbered order')
    context = fig.add_subplot(1, 2, 2)
    top_view(context, order)
    context.set_title('Final position in the lower carton')
    fig.subplots_adjust(left=.04, right=.97, bottom=.10, top=.9, wspace=.2)
    path = root / f'group-card-{index}.png'
    fig.savefig(path, dpi=140)
    plt.close(fig)
    images.append(path)
    rows = ''.join(f'<li><b style="color:rgb{tuple(int(c*255) for c in colors(j%10)[:3])}">{escape(uid)}</b></li>' for j, uid in enumerate(order))
    encoded = base64.b64encode(path.read_bytes()).decode()
    cards.append(f'<section><h2>Prepare group {index}</h2><p>Move each part towards <b>{direction}</b>; keep the final relative poses shown below. Internal paths checked.</p><img src="data:image/png;base64,{encoded}" alt="Actual group {index} meshes and their carton location"><ol>{rows}</ol></section>')

fig, axis = plt.subplots(figsize=(9, 8), facecolor='white')
numbered = [(index, step['unit_ids']) for index, step in enumerate(motion['packing_sequence'], 1)]
top_view(axis, list(triangles), numbered)
axis.set_title('Lower carton: numbered insertion order, all moves -Z')
fig.tight_layout()
overview = root / 'packing-sequence-overview.png'
fig.savefig(overview, dpi=160)
plt.close(fig)
images.append(overview)
sequence = ''.join(f'<li>{escape(step["group_id"]).replace("preassembled_cluster_", "Prepared group ")}</li>' for step in motion['packing_sequence'])
encoded = base64.b64encode(overview.read_bytes()).decode()
box7 = Path('packaging-results/so-arm-101/box7-with-camera-fasteners')
box7_motion = json.loads((box7 / 'motion-validation.json').read_text())
box7_picture = base64.b64encode((box7 / 'mesh-views.png').read_bytes()).decode()
box7_sequence = ''.join(f'<li>{escape(step["group_id"])}</li>' for step in box7_motion['packing_sequence'])
html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>SO101 packing cards</title>
<style>body{{font:16px system-ui;color:#18364b;max-width:1150px;margin:30px auto;padding:0 24px;line-height:1.5}}img{{width:100%;height:auto}}section{{border-top:2px solid #dce5eb;padding:20px 0;break-inside:avoid}}h1,h2{{line-height:1.2}}ol{{columns:2;column-gap:50px}}li{{break-inside:avoid;padding:3px}}.note{{background:#edf4f8;padding:14px}}@media print{{section{{page-break-inside:avoid}}}}</style>
<h1>SO-ARM-101: packing cards</h1><p>29 lower-carton units + 19 BOX7 units. Actual source meshes; source-bound static and continuous path checks.</p>
<p class="note">Frame: X and Y are the carton floor axes; +Z is up. Prepare five groups outside the carton in their final orientation. +X insertion approaches from the negative-X side; -Z insertion approaches from above. Then lower prepared groups and individual items into the carton.</p>
{''.join(cards)}
<section><h2>Insert into the lower carton</h2><p>265 x 243 x 72.2 mm cavity. Follow these 17 steps; every move is -Z.</p><img src="data:image/png;base64,{encoded}" alt="Numbered top view of all actual packed units"><ol>{sequence}</ol></section>
<section><h2>Pack BOX7, camera and tools</h2><p>193 x 75 x 61 mm cavity. All 19 insertion steps are -Z.</p><img src="data:image/png;base64,{box7_picture}" alt="Actual BOX7 figures with the camera packet"><ol>{box7_sequence}</ol></section>
<section><h2>Scope</h2><p>Camera 70 x 70 x 36 mm, two adapters 48 x 39 x 17 mm, cables 80 x 45 x 12 mm, and fasteners/tools 110 x 70 x 18 mm retain declared purchased-part assumptions. Pair clearance is 0.1 mm. Support, hand access, bag behavior and physical trials are not certified.</p><p>Bindings: packing-recipe-bindings.json. Input SHA-256: {fingerprint(problem)}. Layout SHA-256: {fingerprint(layout)}.</p></section></html>'''
(root / 'packing-cards.html').write_text(html, encoding='utf8')
(root / 'packing-cards-render.json').write_text(json.dumps({'input_sha256':fingerprint(problem), 'layout_sha256':fingerprint(layout), 'images':{p.name:sha256(p.read_bytes()).hexdigest() for p in images}}, indent=2), encoding='utf8')
print(root / 'packing-cards.html', flush=True)
