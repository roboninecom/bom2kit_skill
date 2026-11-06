"""Render complete SO102 numbered placement cards after fresh kit assessment."""
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
from matplotlib.ticker import MaxNLocator
from build_complete_comparison_pdf import load_case, render_geometry, checked_motion_index, ROOT
from bom2kit.report import fingerprint

case = load_case('so-arm-102')
motion = checked_motion_index(case)
root = case['folder']
problem, layout = case['problem'], case['layout']
items = {item['id']: item for item in problem['items']}
geometry, groups = {}, {}
for pose in layout['placements']:
    item = items[pose['item_id']]
    raw = Path(item['mesh']['path']).read_bytes()
    assert sha256(raw).hexdigest() == item['mesh']['sha256']
    data = json.loads(raw)
    transform = np.array(pose['transform'])
    vertices = np.array(data['vertices_mm']) @ transform[:3, :3].T + transform[:3, 3]
    geometry[pose['unit_id']] = vertices[np.array(data['triangles'])]
    groups.setdefault(item['packing_group'], []).append(pose['unit_id'])
colors = plt.get_cmap('tab20')
cards, images = [], []
for card_index, outer_pose in enumerate(case['outer_layout']['placements'], 1):
    name = outer_pose['item_id']
    uids = groups[name]
    vertices = np.concatenate([geometry[uid].reshape(-1, 3) for uid in uids])
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    fig = plt.figure(figsize=(13, 6), facecolor='white')
    iso = fig.add_subplot(1, 2, 1, projection='3d')
    top = fig.add_subplot(1, 2, 2)
    polygons, depths, shades, centers = [], [], [], []
    rows = []
    for index, uid in enumerate(uids, 1):
        mesh = geometry[uid]
        color = colors((index-1) % 20)
        iso.add_collection3d(Poly3DCollection(mesh, facecolor=color, edgecolor='none'))
        polygons.append(mesh[:, :, :2])
        depths.append(mesh[:, :, 2].mean(axis=1))
        shades.extend([color] * len(mesh))
        bounds = np.array([mesh.reshape(-1, 3).min(axis=0), mesh.reshape(-1, 3).max(axis=0)])
        centers.append((index, bounds.mean(axis=0)))
        rows.append(f'<tr><td>{index}</td><td>{escape(uid)}</td><td>' + ', '.join(f'{v:.2f}' for v in bounds[0]) + '</td></tr>')
    iso.set(xlim=(low[0]-2, high[0]+2), ylim=(low[1]-2, high[1]+2), zlim=(low[2]-2, high[2]+2), xlabel='X', ylabel='Y', zlabel='Z')
    iso.set_box_aspect(high-low+4)
    iso.set_proj_type('ortho')
    iso.view_init(27, -55)
    for axis in (iso.xaxis, iso.yaxis, iso.zaxis):
        axis.set_major_locator(MaxNLocator(3))
    iso.set_title('Actual final geometry')
    order = np.argsort(np.concatenate(depths), kind='stable')
    top.add_collection(PolyCollection(np.concatenate(polygons)[order], facecolors=np.array(shades)[order], edgecolors='none'))
    split = sorted(centers, key=lambda pair: pair[1][0])
    left_numbers = {number for number, _ in split[:(len(split)+1)//2]}
    for side in (-1, 1):
        chosen = [(i, c) for i, c in centers if (i in left_numbers) == (side < 0)]
        chosen.sort(key=lambda pair: pair[1][1])
        label_x = .035 if side < 0 else .965
        for (number, center), label_y in zip(chosen, np.linspace(.06, .94, len(chosen))):
            top.annotate(str(number), xy=center[:2], xytext=(label_x, label_y),
                         textcoords='axes fraction',
                         fontsize=8.5, ha='center', va='center',
                         bbox={'boxstyle':'circle,pad=.2','fc':'white','ec':'#18364b'},
                         arrowprops={'arrowstyle':'-','color':'#667785','lw':.7})
    top.set(xlim=(low[0]-23, high[0]+23), ylim=(low[1]-8, high[1]+8), xlabel='X (mm)', ylabel='Y (mm)', aspect='equal')
    top.set_adjustable('datalim')
    top.set_title('Numbered final positions - IDs, not assembly order')
    fig.suptitle(f'{name}: {len(uids)} geometric units', fontsize=15)
    fig.subplots_adjust(left=.04, right=.98, bottom=.12, top=.87, wspace=.2)
    path = root / f'group-card-{card_index}.png'
    fig.savefig(path, dpi=150)
    plt.close(fig)
    images.append(path)
    encoded = base64.b64encode(path.read_bytes()).decode()
    corner = ', '.join(f'{v:g}' for v in outer_pose['position_mm'])
    envelope = ' x '.join(f'{v:g}' for v in outer_pose['dimensions_mm'])
    cards.append(f'<section><h2>{card_index}. {escape(name)}</h2><p>Outer group corner XYZ: {corner} mm; envelope {envelope} mm. Insert this prepared group downward (-Z), in the listed group order.</p><img src="data:image/png;base64,{encoded}" alt="Actual {escape(name)} meshes with numbered part positions"><table><thead><tr><th>ID</th><th>Unit</th><th>Minimum XYZ, mm (carton frame)</th></tr></thead><tbody>{"".join(rows)}</tbody></table></section>')
iso, layers, _ = render_geometry(case, root)
layer_html = ''.join('<img src="data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode() + '" alt="Actual complete carton layer">' for path in layers)
manifest = base64.b64encode(json.dumps({'input':problem,'layout':layout},indent=2).encode()).decode()
assumptions = ''.join('<li>' + escape(value) + '</li>' for value in problem.get('assumptions', []))
motion_steps = ''.join('<li>' + escape(value) + '</li>' for value in motion['instructions'])
motion_links = ''.join('<li><a href="../../../' + escape(entry['path']) + '">' + escape(name.replace('_', ' ')) + '</a></li>' for name, entry in motion['evidence'].items())
html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>SO102 packing cards</title>
<style>body{{font:16px system-ui;color:#18364b;max-width:1200px;margin:28px auto;padding:0 24px;line-height:1.45}}img{{width:100%;height:auto}}.layers{{display:grid;grid-template-columns:1fr 1fr}}section{{padding:22px 0;border-top:2px solid #dce5eb}}table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{padding:5px 10px;border-bottom:1px solid #ddd;text-align:left}}.note{{background:#eef4f8;padding:14px}}h1,h2{{line-height:1.2}}</style>
<h1>SO-ARM-102: numbered packing cards</h1><p><b>93/93 geometric units; complete declared canonical BOM; 20.06336 L.</b> Fresh assessment: {case['assessment_seconds']:.2f} seconds.</p>
<p class="note">All drawings use actual source triangles and the final carton coordinate frame: X/Y on the floor, +Z up. Callout numbers identify exact unit poses; they are not an internal assembly sequence. Group insertion and internal assembly have separate passing motion certificates. Prepare the groups in their documented local frames, then insert the five groups below in order. Hands, tools and support during assembly are not modeled.</p>
<section><h2>Checked assembly instructions</h2><ol>{motion_steps}</ol><p>Exact ordered unit lists and source coordinate frames:</p><ul>{motion_links}</ul></section>
<div class="layers">{layer_html}</div>
<p><a download="so102-exact-packing-poses.json" href="data:application/json;base64,{manifest}">Download exact source-bound poses and contents</a></p>
{''.join(cards)}
<section><h2>Explicit assumptions and checks</h2><ul>{assumptions}</ul><p>The clamps have user-confirmed custom106mm frames; the retained assembled proxy is140x40x52mm. Purchased folded envelopes remain estimates. No geometry is scaled. Support within irregular groups, hands/tool access and transport performance are not certified.</p><p>Source-bound assessment: assessment.json. Input SHA-256:{fingerprint(problem)}; layout SHA-256:{fingerprint(layout)}.</p></section></html>'''
(root / 'packing-cards.html').write_text(html, encoding='utf8')
(root / 'packing-cards-render.json').write_text(json.dumps({'input_sha256':fingerprint(problem),'layout_sha256':fingerprint(layout),
    'image_sha256':{path.name:sha256(path.read_bytes()).hexdigest() for path in images+layers+[iso]}},indent=2),encoding='utf8')
print(root / 'packing-cards.html',flush=True)
