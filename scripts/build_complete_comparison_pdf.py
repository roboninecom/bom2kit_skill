"""Freshly assess complete kits and render a concise, source-bound comparison.

Default: require both corrected complete kits. --draft-101: explicitly limited
101-only draft; never an accepted result for the two-kit user objective.
"""
import argparse
from collections import Counter
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from bom2kit.assessment import assess_mesh_kit
from bom2kit.report import fingerprint
from bom2kit.validation import validate


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def checked_motion_index(case):
    path = case['folder'] / 'independent-motion-readiness.json'
    index = read(path)
    if not index.get('complete_internal_motion_ready'):
        raise ValueError('Complete internal motion evidence is not ready')
    for name, value in [('input', case['problem']), ('layout', case['layout'])]:
        if index.get(name + '_sha256') != fingerprint(value):
            raise ValueError('Motion evidence index is not bound to the final ' + name)
    for entry in index['evidence'].values():
        source = ROOT / entry['path']
        if sha256(source.read_bytes()).hexdigest() != entry['sha256'] or not read(source).get('valid'):
            raise ValueError('Motion certificate is stale or invalid: ' + str(source))
    return index


def load_case(key):
    folder = ROOT / 'packaging-results' / key / 'complete-kit'
    problem, layout, bom = [read(folder / f'{name}.json') for name in ('input', 'layout', 'bom')]
    if problem.get('custom_frame_length_mm') != 106:
        raise ValueError(f'{key}: missing user-confirmed custom 106 mm clamp metadata')
    clamps = [item for item in problem['items']
              if any(sku in item.get('contents', {}) for sku in ('C_clamp_3inch', 'clamp_3_inch'))
              or ('custom' in item['id'].lower() and '106' in item['id'] and 'clamp' in item['id'].lower())]
    if not clamps or sum(item.get('quantity', 1) for item in clamps) != 4:
        raise ValueError(f'{key}: exactly four current custom clamps required')
    import numpy as np
    for item in clamps:
        if '106' not in str(item.get('dimension_basis', item.get('geometry_evidence', ''))):
            raise ValueError(f'{key}: clamp evidence does not identify the corrected frame')
        source = read(Path(item['mesh']['path']))
        if np.ptp(np.asarray(source['vertices_mm']), axis=0).max() < 106 - 1e-6:
            raise ValueError(f'{key}: smaller superseded clamp geometry detected')
    started = perf_counter()
    assessment = assess_mesh_kit(bom, problem, layout)
    seconds = perf_counter() - started
    if not assessment['computational_acceptance']:
        raise ValueError(f'{key}: fresh complete-kit assessment rejected; no final PDF written')
    outer_problem, outer_layout = [read(folder / f'outer-{name}.json') for name in ('input', 'layout')]
    outer_check = validate(outer_problem, outer_layout)
    if not outer_check['valid']:
        raise ValueError(f'{key}: outer support/insertion certificate rejected: {outer_check["errors"]}')
    # Validate any reused report image against the current data, even though new
    # source-triangle plots below do not depend on that image.
    if (folder / 'mesh-render.json').exists():
        binding = read(folder / 'mesh-render.json')
        if (binding['input_sha256'] != fingerprint(problem) or binding['layout_sha256'] != fingerprint(layout)
                or binding['image_sha256'] != sha256((folder / 'mesh-views.png').read_bytes()).hexdigest()):
            raise ValueError(f'{key}: stale mesh rendering; regenerate mesh-report')
    return {'key': key, 'folder': folder, 'problem': problem, 'layout': layout,
            'bom': bom, 'assessment': assessment, 'assessment_seconds': seconds,
            'outer_problem': outer_problem, 'outer_layout': outer_layout}


def render_geometry(case, destination):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    items = {item['id']: item for item in case['problem']['items']}
    triangles, groups = {}, {}
    for pose in case['layout']['placements']:
        item = items[pose['item_id']]
        raw = Path(item['mesh']['path']).read_bytes()
        if sha256(raw).hexdigest() != item['mesh']['sha256']:
            raise ValueError('Source changed after assessment')
        source = json.loads(raw)
        transform = np.asarray(pose['transform'])
        vertices = np.asarray(source['vertices_mm']) @ transform[:3, :3].T + transform[:3, 3]
        triangles[pose['unit_id']] = vertices[np.asarray(source['triangles'])]
        groups[pose['unit_id']] = item.get('packing_group', 'UNASSIGNED')
    if 'UNASSIGNED' in groups.values():
        raise ValueError('Complete report requires explicit packing_group on every item')
    group_names = list(dict.fromkeys(groups.values()))
    colors = plt.get_cmap('tab10')
    color = {name: colors(index % 10) for index, name in enumerate(group_names)}
    dims = case['problem']['container']['inner_mm']
    fig = plt.figure(figsize=(8, 6), facecolor='white')
    axis = fig.add_subplot(111, projection='3d')
    for uid, geometry in triangles.items():
        axis.add_collection3d(Poly3DCollection(geometry, facecolor=color[groups[uid]], edgecolor='none'))
    axis.set(xlim=(0, dims[0]), ylim=(0, dims[1]), zlim=(0, dims[2]), xlabel='X (mm)', ylabel='Y (mm)', zlabel='Z (mm)')
    axis.set_box_aspect(dims)
    axis.set_proj_type('ortho')
    axis.view_init(30, -55)
    fig.tight_layout()
    iso = destination / f'{case["key"]}-actual-isometric.png'
    fig.savefig(iso, dpi=150)
    plt.close(fig)
    group_z = {pose['item_id']: pose['position_mm'][2] for pose in case['outer_layout']['placements']}
    levels = sorted(set(round(value, 4) for value in group_z.values()))
    if len(levels) != 2 or any(group not in group_z for group in group_names):
        raise ValueError('Expected two explicit carton layers with matching group IDs')
    layer_files = []
    for level_index, level in enumerate(levels):
        fig, axis = plt.subplots(figsize=(8, 6), facecolor='white')
        polygons, depths, shades = [], [], []
        included = []
        for uid, geometry in triangles.items():
            if abs(group_z[groups[uid]] - level) > 1e-4:
                continue
            included.append(uid)
            polygons.append(geometry[:, :, :2])
            depths.append(geometry[:, :, 2].mean(axis=1))
            shades.extend([color[groups[uid]]] * len(geometry))
        order = np.argsort(np.concatenate(depths), kind='stable')
        axis.add_collection(PolyCollection(np.concatenate(polygons)[order], facecolors=np.asarray(shades)[order], edgecolors='none'))
        for name in group_names:
            active = [uid for uid in included if groups[uid] == name]
            if not active:
                continue
            vertices = np.concatenate([triangles[uid].reshape(-1, 3) for uid in active])
            center = (vertices.min(axis=0) + vertices.max(axis=0)) / 2
            short = 'MERGED' if name.startswith('MERGED') else name
            axis.text(center[0], center[1], short, ha='center', va='center', weight='bold', fontsize=10,
                      bbox={'fc':'white', 'ec':'#17384c', 'alpha':.92, 'pad':3})
        axis.set(xlim=(0, dims[0]), ylim=(0, dims[1]), xlabel='X (mm)', ylabel='Y (mm)', aspect='equal')
        axis.set_title(('Lower' if level_index == 0 else 'Upper') + ' layer - actual source triangles')
        fig.tight_layout()
        path = destination / f'{case["key"]}-layer-{level_index + 1}.png'
        fig.savefig(path, dpi=160)
        plt.close(fig)
        layer_files.append(path)
    return iso, layer_files, Counter(groups.values())


def render_reference_cartons(key, destination):
    """Reconstruct only documented carton envelopes, never Alan's part poses."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    source = ROOT / 'packaging-results/benchmarks' / key / 'input.json'
    problem = read(source)
    layout = problem['reference_layout']
    if not validate(problem, layout)['valid']:
        raise ValueError('Reference carton reconstruction does not validate')
    levels = sorted({p['position_mm'][2] for p in layout['placements']})
    if len(levels) != 2 or len(layout['placements']) != 7:
        raise ValueError('Expected seven reference cartons in two layers')
    margin = problem['container']['protection_mm']
    cavity = [v - 2 * margin for v in problem['container']['inner_mm']]
    fig, axes = plt.subplots(2, 1, figsize=(5, 7), facecolor='white')
    colors = plt.get_cmap('tab10')
    for layer, (axis, level) in enumerate(zip(axes, levels)):
        for index, pose in enumerate(layout['placements']):
            if pose['position_mm'][2] != level:
                continue
            x, y = [v - margin for v in pose['position_mm'][:2]]
            a, b, c = pose['dimensions_mm']
            axis.add_patch(Rectangle((x, y), a, b, facecolor=colors(index), edgecolor='white', linewidth=2))
            axis.text(x+a/2, y+b/2, f'{pose["item_id"]}\n{a:g} x {b:g}\nx {c:g} mm',
                      ha='center', va='center', fontsize=9, weight='bold',
                      bbox={'facecolor':'white', 'alpha':.8, 'edgecolor':'none','pad':2})
        axis.set(xlim=(0,cavity[0]), ylim=(0,cavity[1]), aspect='equal', xlabel='X (mm)', ylabel='Y (mm)')
        axis.set_title(('Lower' if layer == 0 else 'Upper') + ' reference layer', fontsize=12)
    fig.tight_layout()
    path = destination / f'{key}-alan-cartons-reconstructed.png'
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return path, {'source':str(source.relative_to(ROOT)), 'source_sha256':sha256(source.read_bytes()).hexdigest(),
                  'scope':'Seven outer carton envelopes reconstructed from documented dimensions; original part poses unavailable'}


def build(draft_101=False, output=None):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    keys = ['so-arm-101'] if draft_101 else ['so-arm-101', 'so-arm-102']
    # All acceptance gates run before creating any apparent final deliverable.
    cases = [load_case(key) for key in keys]
    for case in cases:
        if case['key'].endswith('102'):
            case['motion'] = checked_motion_index(case)
    destination = Path(output) if output else ROOT / 'packaging-results/complete-comparison'
    destination.mkdir(parents=True, exist_ok=True)
    pictures = [render_geometry(case, destination) for case in cases]
    target = destination / ('101-comparison-draft.pdf' if draft_101 else 'complete-packing-comparison.pdf')
    temporary = target.with_suffix('.pending.pdf')
    pdf = canvas.Canvas(str(temporary), pagesize=A4)
    pdf.setTitle('SO-ARM packing: complete declared BOM comparison' + (' - 101 draft only' if draft_101 else ''))
    width, height = A4
    style = ParagraphStyle('body', fontName='Helvetica', fontSize=9.3, leading=13, textColor=HexColor('#18364b'))

    def paragraph(text, x, y, w=523, size=9.3):
        local = ParagraphStyle('local', parent=style, fontSize=size, leading=size*1.4)
        obj = Paragraph(text, local)
        _, h = obj.wrap(w, 1000)
        obj.drawOn(pdf, x, y-h)
        return y-h

    def title(text, subtitle):
        pdf.setFillColor(HexColor('#18364b'))
        pdf.setFont('Helvetica-Bold', 20)
        pdf.drawString(36, height-45, text)
        paragraph(subtitle, 36, height-62, size=9)

    def image(path, x, y, w, h):
        pdf.drawImage(str(path), x, y, width=w, height=h, preserveAspectRatio=True, anchor='c', mask='auto')

    def footer(number):
        pdf.setFont('Helvetica', 8)
        pdf.setFillColor(HexColor('#617483'))
        pdf.drawString(36, 22, 'Computational packing under explicit assumptions; no physical shipping trial.')
        pdf.drawRightString(width-36, 22, str(number))

    provenance = []
    for index, (case, picture) in enumerate(zip(cases, pictures)):
        assessment = case['assessment']
        model = case['key'].upper().replace('SO-ARM-', 'SO-ARM')
        iso, layers, counts = picture
        draft = '101-ONLY DRAFT: SO-ARM102 is not assessed in this document.' if draft_101 else 'Both complete declared kits freshly assessed before PDF generation.'
        title(f'{model} | Alan and computed packing', draft)
        volume = assessment['external_volume_l']
        reference = assessment['reference_external_volume_l']
        units = assessment['geometry']['expected_units']
        text = (f'<b>Alan:</b> {reference:.5f} L &nbsp;&nbsp; <b>Computed:</b> {volume:.5f} L &nbsp;&nbsp; '
                f'<b>Change:</b> {assessment["volume_change_percent"]:+.2f}%<br/>'
                f'<b>{units}/{units} logical packing units; declared BOM coverage passes; rigid geometry passes.</b><br/>'
                f'Fresh geometry/BOM/volume recheck: {case["assessment_seconds"]:.2f} seconds. Recipe validation, not search time.')
        paragraph(text, 36, height-95)
        alan = ROOT / 'packaging-results/research-previews' / ('layout-1.png' if case['key'].endswith('101') else '102-kitting-5.png')
        if not alan.exists():
            raise ValueError(f'Missing Alan source screenshot: {alan}')
        reference_binding = None
        if case['key'].endswith('102'):
            alan, reference_binding = render_reference_cartons(case['key'], destination)
        paragraph('<b>Alan: reconstructed seven cartons</b>' if reference_binding else '<b>Alan source document</b>', 36, 645, w=250)
        paragraph('<b>Computed: actual placed geometry</b>', 309, 645, w=250)
        image(alan, 36, 270, 250, 355)
        image(iso, 302, 360, 257, 260)
        paragraph('Same external carton target. Grouping and internal cartons may change while every declared item remains represented.', 309, 346, w=250)
        if case['key'].endswith('101'):
            paragraph('Source: Alan SO101 box-in-box instruction, page 1. R3 contents retained: 43 printed pieces. The 69 logical units count one USB packet represented by two physical subbags.', 36, 249)
        else:
            paragraph('Alan reference: two carton layers reconstructed from documented BOX1-7 dimensions and benchmark reference_layout. Original full-kit part poses are unavailable; these are carton envelopes, not Alan CAD. Computed: current pinned CAD and independent BOM.', 36, 249)
        paragraph('<b>Comparison boundary.</b> The reported 50 L result was not supplied as a reproducible layout and is not used as a measured baseline. This comparison uses Alan\'s documented carton and the complete declared contents.', 36, 194)
        paragraph('<b>Corrected clamps:</b> custom 106 mm frames. The superseded 80 mm catalogue model is rejected. The retained historical assembled proxy is 140 x 40 x 52 mm; other unmeasured details remain estimates.', 36, 130)
        footer(index*2+1)
        pdf.showPage()
        title(f'{model} | Layer plan and packing order', 'Source triangles at validated rigid poses. White labels identify the packing groups.')
        image(layers[0], 28, 414, 270, 285)
        image(layers[1], 298, 414, 270, 285)
        y = paragraph('<b>Group contents and sequence</b>', 36, 409)
        for position, pose in enumerate(case['outer_layout']['placements'], 1):
            name = pose['item_id']
            shown = 'Merged printed/electronics group' if name.startswith('MERGED') else name
            y = paragraph(f'{position}. <b>{escape(shown)}</b>: {counts[name]} represented geometric units; external group envelope '
                          + ' x '.join(f'{d:g}' for d in pose['dimensions_mm']) + ' mm.', 36, y-5)
        y = paragraph('The outer group arrangement passes full base support and top insertion checks. Internal assembly paths are separate evidence: static mesh acceptance alone does not establish them.', 36, y-13)
        if case['key'].endswith('101'):
            y = paragraph('101 operating cards: <b>so-arm-101/regrouped-without-camera/packing-cards.html</b>. Five printed clusters use their checked internal -Z or +X paths. Custom clamps assemble 4, 3, 2, 1 along the documented negative-Y direction, then lower together into BOX6. BOX7 contains all 17 figures, camera and tools.', 36, y-10)
        else:
            motion = case['motion']
            y = paragraph('102 motion checks pass for group insertion and internal assembly. Preassemble the lower seven-part cluster along -Y and wrist/clamp pair along -X; custom clamps use their checked -Y sequence. BOX7 uses 31 individual downward insertions. See <b>so-arm-102/complete-kit/packing-cards.html</b> and its linked motion certificates for exact unit orders and coordinate frames.', 36, y-10)
        material_note = ('Cardboard groups use 1.5 mm walls.' if case['key'].endswith('101') else
                         'Upper groups use 0.05 mm film instead of inner cartons. Ten upper servos use 1 mm EPE; two lower servos use 2 mm EPE. Cushioning equivalence is unverified.')
        y = paragraph('<b>Assumptions:</b> purchased packets, folded leads and protective sleeves use declared estimated envelopes; rigid CAD is unscaled. '
                      + material_note + ' External foam is 15 mm; shipping-wall offset is 7 mm. Booklet allowance comes from the current manifest. '
                      'Support within irregular groups, hands/tool access and transport performance are not certified.', 36, y-10, size=8.8)
        if y < 42:
            raise ValueError('PDF text overflows page; revise layout before delivery')
        footer(index*2+2)
        pdf.showPage()
        provenance.append({'kit':case['key'], 'assessment':assessment, 'assessment_seconds':case['assessment_seconds'],
                           'motion_evidence_index':motion if case['key'].endswith('102') else None,
                           'reference_reconstruction':reference_binding,
                           'alan_image':str(alan.relative_to(ROOT)), 'alan_image_sha256':sha256(alan.read_bytes()).hexdigest(),
                           'rendered_images':{p.name:sha256(p.read_bytes()).hexdigest() for p in [iso,*layers]}})
    pdf.save()
    temporary.replace(target)
    (destination / ('101-draft-evidence.json' if draft_101 else 'complete-comparison-evidence.json')).write_text(
        json.dumps({'scope':'101-only draft' if draft_101 else 'both complete declared kits', 'cases':provenance,
                    'pdf_sha256':sha256(target.read_bytes()).hexdigest()}, indent=2), encoding='utf8')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--draft-101', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        print(build(args.draft_101, args.output))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'Refusing comparison: {error}\n')
