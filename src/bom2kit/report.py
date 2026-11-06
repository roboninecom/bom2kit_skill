"""Standalone, evidence-scoped packing instructions from a validated certificate."""

import base64
from hashlib import sha256
from html import escape
import json
import math
from pathlib import Path

from .models import normalize, vector
from .validation import validate

COLORS = ['#6da7ce', '#87bfa4', '#e6b46a', '#b09bc9', '#db9692', '#8bbec0', '#b8be78']


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def comparison(problem, layout):
    """Report only the comparisons justified by supplied evidence and actual checks."""
    checks = validate(problem, layout)
    data = normalize(problem)
    volume = math.prod(data['external']) / 1e6
    ref = problem.get('reference', {})
    if not isinstance(ref, dict):
        raise ValueError('reference must be an object')
    reference_mm = ref.get('external_mm')
    reference_volume = math.prod(vector(reference_mm, 'reference.external_mm', True)) / 1e6 if reference_mm is not None else None
    no_worse = checks['valid'] and reference_volume is not None and volume <= reference_volume + 1e-9
    return {
        'scope': 'Nominal closed-box arrangement; internal SKU geometry is not validated by the box solver',
        'geometry_valid': checks['valid'], 'external_volume_l': volume,
        'reference_external_volume_l': reference_volume,
        'volume_change_percent': 100 * (volume / reference_volume - 1) if reference_volume else None,
        'no_worse_nominal_carton_volume': no_worse,
        'full_kit_acceptance': False,
        'full_kit_acceptance_reason': 'Part-level fit, dimensional tolerances, packaging strength and physical execution require separate evidence',
        'input_sha256': fingerprint(problem), 'layout_sha256': fingerprint(layout),
    }


def _color(item, index):
    return COLORS[index % len(COLORS)]


def layer_svg(problem, layout, z, width=500, height=340):
    data = normalize(problem)
    px, py, _ = data['protection']
    xsize, ysize = [data['inner'][i] - 2 * data['protection'][i] for i in (0, 1)]
    scale = min((width - 54) / xsize, (height - 54) / ysize)
    ox, oy = 26, 20
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Layer at z={z:g} mm">',
           f'<rect x="{ox}" y="{oy}" width="{xsize*scale}" height="{ysize*scale}" fill="#f5f7fa" stroke="#18364b" stroke-width="2"/>']
    id_colors = {item['id']: i for i, item in enumerate(problem['items'])}
    for p in layout.get('placements', []):
        if abs(p['position_mm'][2] - z) > 1e-7:
            continue
        x, y, _ = p['position_mm']; a, b, c = p['dimensions_mm']
        sx, sy = ox + (x-px)*scale, oy + (y-py)*scale
        color = _color(p['item_id'], id_colors.get(p['item_id'], 0))
        title = escape(f"{p['unit_id']}: {a:g} x {b:g} x {c:g} mm at {x:g}, {y:g}, {z:g}")
        out.append(f'<g><title>{title}</title><rect x="{sx}" y="{sy}" width="{a*scale}" height="{b*scale}" fill="{color}" stroke="#fff" stroke-width="2"/>')
        out.append(f'<text x="{sx+a*scale/2}" y="{sy+b*scale/2}" text-anchor="middle" font-size="15" font-weight="bold">{escape(p["item_id"])}</text></g>')
    out.append(f'<text x="{ox}" y="{oy+ysize*scale+23}" font-size="12">Cavity {xsize:g} x {ysize:g} mm | Z = {z:g} mm</text></svg>')
    return ''.join(out)


def iso_svg(problem, layout, width=700, height=470):
    points = []
    polygons = []
    id_colors = {item['id']: i for i, item in enumerate(problem['items'])}
    for p in sorted(layout.get('placements', []), key=lambda r: sum(r['position_mm'])):
        x,y,z = p['position_mm']; a,b,c = p['dimensions_mm']
        vertices = [(x,y,z), (x+a,y,z), (x+a,y+b,z), (x,y+b,z),
                    (x,y,z+c), (x+a,y,z+c), (x+a,y+b,z+c), (x,y+b,z+c)]
        projected = [(vx-vy, .43*(vx+vy)-vz) for vx,vy,vz in vertices]
        points.extend(projected)
        polygons.append((p, projected, _color(p['item_id'], id_colors.get(p['item_id'],0))))
    if not points:
        return '<p>No complete layout is available.</p>'
    xmin,xmax=min(p[0] for p in points),max(p[0] for p in points)
    ymin,ymax=min(p[1] for p in points),max(p[1] for p in points)
    scale=min((width-50)/max(xmax-xmin,1),(height-50)/max(ymax-ymin,1))
    def xy(p): return (25+(p[0]-xmin)*scale,25+(p[1]-ymin)*scale)
    out=[f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Computed isometric packing">']
    for p,vertices,color in polygons:
        for inds,opacity in [([0,1,5,4],.7),([1,2,6,5],.85),([4,5,6,7],1)]:
            coords=' '.join(f'{xy(vertices[i])[0]:.2f},{xy(vertices[i])[1]:.2f}' for i in inds)
            out.append(f'<polygon points="{coords}" fill="{color}" fill-opacity="{opacity}" stroke="#34495e" stroke-width="1"/>')
        center=xy(tuple(sum(vertices[i][k] for i in (4,5,6,7))/4 for k in (0,1)))
        out.append(f'<text x="{center[0]}" y="{center[1]}" text-anchor="middle" font-size="14" font-weight="bold">{escape(p["item_id"])}</text>')
    out.append('</svg>')
    return ''.join(out)


def render_report(problem, layout, validation, output_dir):
    """Write self-contained HTML and comparison JSON, revalidating the certificate."""
    del validation  # caller cannot override verification
    checked = validate(problem, layout)
    summary = comparison(problem, layout)
    output_dir = Path(output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    title = str(problem.get('name', 'Packing layout'))
    state = 'NOMINAL CARTON FIT VERIFIED' if checked['valid'] else 'INVALID LAYOUT - DO NOT PACK'
    data = normalize(problem)
    ref = problem.get('reference', {})
    ref_volume = summary['reference_external_volume_l']
    reference_text = f'{ref_volume:.5f} L' if ref_volume else 'Not supplied'
    safe_layout = layout if checked['valid'] else {'placements': []}
    stats = layout.get('stats', {}) if isinstance(layout, dict) else {}
    elapsed = stats.get('elapsed_seconds', 0) if isinstance(stats, dict) else 0
    elapsed_text = f'{elapsed:.3f}' if isinstance(elapsed, (int, float)) and math.isfinite(elapsed) and elapsed >= 0 else 'unavailable'
    sections = [f'<h1>{escape(title)}</h1><p class="badge">{state}</p>',
                '<p class="warning">Closed-box geometry only. This report does not certify the contents inside each box or transport performance.</p>',
                f'<div class="metrics"><div>Alan reference<strong>{reference_text}</strong></div><div>Computed carton<strong>{summary["external_volume_l"]:.5f} L</strong></div><div>Units placed<strong>{checked["placed_units"]} / {checked["expected_units"]}</strong></div></div>',
                f'<p>Outer dimensions: {" x ".join(f"{v:g}" for v in data["external"])} mm. Reported search time: {elapsed_text} s. Positions are measured from the inner carton origin, before foam margins.</p>',
                '<h2>Computed arrangement</h2>',iso_svg(problem,safe_layout)]
    reference_layout = problem.get('reference_layout')
    if reference_layout and not validate(problem, reference_layout)['valid']:
        sections.append('<p class="warning">Reference reconstruction is not valid in this selected container; its diagram is omitted. The numeric reference volume remains the supplied source dimension product.</p>')
        reference_layout = None
    layers = sorted({p['position_mm'][2] for p in safe_layout.get('placements',[])})
    for z in layers:
        sections.append(f'<h2>Layer starting at {z:g} mm</h2><div class="views">')
        if reference_layout:
            sections.append('<div><h3>Alan reference reconstruction</h3>'+layer_svg(problem,reference_layout,z)+'</div>')
        sections.append('<div><h3>Independent computed layout</h3>'+layer_svg(problem,layout,z)+'</div></div>')
    sections.append('<h2>Packing sequence</h2><p>Use closed, prepared packing units. Match the oriented dimensions below; do not infer the lid face from the original dimension order.</p><table><tr><th>Step</th><th>Unit</th><th>Position X / Y / Z</th><th>Oriented size X / Y / Z</th></tr>')
    for n,p in enumerate(safe_layout.get('placements',[]),1):
        pos=' / '.join(f'{v:g}' for v in p['position_mm']); size=' / '.join(f'{v:g}' for v in p['dimensions_mm'])
        sections.append(f'<tr><td>{n}</td><td>{escape(p["unit_id"])}</td><td>{pos}</td><td>{size}</td></tr>')
    sections.append('</table><h2>Box contents</h2><p>Declared manifest only; the rectangular solver does not verify internal part fit.</p><table><tr><th>Box</th><th>Declared contents</th></tr>')
    for item in problem['items']:
        contents=item.get('contents',{})
        desc=', '.join(f'{key}: {qty}' for key,qty in contents.items()) if contents else 'Not supplied / unresolved'
        sections.append(f'<tr><td>{escape(item["id"])}</td><td>{escape(desc)}</td></tr>')
    sections.append('</table><h2>Validation</h2><ul>')
    for check in checked['checks']: sections.append(f'<li>{escape(check.replace("_"," "))}</li>')
    for error in checked['errors']: sections.append(f'<li class="warning">{escape(error)}</li>')
    sections.append('</ul><h2>Assumptions and unresolved evidence</h2><ul>')
    for note in problem.get('limitations',[]): sections.append(f'<li>{escape(str(note))}</li>')
    sections.append(f'<li>{escape(summary["full_kit_acceptance_reason"])}</li></ul>')
    sections.append('<h2>Sources and reproducibility</h2><ul>')
    for source in problem.get('sources',[]): sections.append(f'<li>{escape(str(source))}</li>')
    sections.append(f'</ul><p class="hash">Input SHA-256: {summary["input_sha256"]}<br>Layout SHA-256: {summary["layout_sha256"]}</p>')
    css='body{font:16px/1.5 system-ui,sans-serif;color:#19364a;background:#fff;max-width:1080px;margin:40px auto;padding:0 24px}h1{font-size:32px}h2{margin-top:32px}svg{width:100%;max-height:450px}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #dce5ec;text-align:left;padding:8px}th{background:#edf3f7}.badge{background:#edf3f7;padding:12px;font-weight:bold}.warning{background:#fff2d9;padding:12px}.views,.metrics{display:flex;gap:24px}.views>div,.metrics>div{flex:1}.metrics{background:#edf3f7;padding:20px}.metrics strong{display:block;font-size:28px}.hash{font-size:11px;overflow-wrap:anywhere}@media print{body{margin:0;font-size:11px}.views{break-inside:avoid}h2{break-after:avoid}}'
    html=f'<!doctype html><html lang="en"><meta charset="utf-8"><title>{escape(title)}</title><style>{css}</style><body>'+''.join(sections)+'</body></html>'
    target=output_dir/'instruction.html';target.write_text(html,encoding='utf-8')
    (output_dir/'comparison.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return target
