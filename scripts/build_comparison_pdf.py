"""Render the evidence-scoped local benchmark as a concise two-page PDF."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from bom2kit.report import comparison, COLORS
from bom2kit.validation import validate


def build(output_dir=None):
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4

    directory = Path(output_dir or ROOT / 'packaging-results' / 'benchmarks')
    destination = directory / 'packing-comparison.pdf'
    pdf = canvas.Canvas(str(destination), pagesize=A4)
    pdf.setTitle('SO-ARM101 and SO-ARM102: packing comparison')
    width, height = A4

    def text(x, y, message, size=10, bold=False, color='#18364b'):
        pdf.setFillColor(HexColor(color))
        pdf.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        pdf.drawString(x, y, message)

    def plan(problem, layout, x, y, z):
        margin = problem['container']['protection_mm']
        cavity = [v - 2 * margin for v in problem['container']['inner_mm']]
        scale = min(235 / cavity[0], 170 / cavity[1])
        pdf.setFillColor(HexColor('#edf2f6'))
        pdf.rect(x, y, cavity[0] * scale, cavity[1] * scale, fill=1, stroke=0)
        ids = {item['id']: i for i, item in enumerate(problem['items'])}
        for placement in layout['placements']:
            if abs(placement['position_mm'][2] - z) > 1e-6:
                continue
            a, b, _ = placement['dimensions_mm']
            px, py, _ = placement['position_mm']
            left = x + (px - margin) * scale
            bottom = y + (cavity[1] - (py - margin) - b) * scale
            pdf.setFillColor(HexColor(COLORS[ids[placement['item_id']] % len(COLORS)]))
            pdf.setStrokeColor(HexColor('#ffffff'))
            pdf.rect(left, bottom, a * scale, b * scale, fill=1, stroke=1)
            text(left + 5, bottom + b * scale / 2, placement['item_id'], 10, True)
        text(x, y - 15, f'Z = {z - margin:g} mm above cavity floor', 9)

    for index, key in enumerate(('so-arm-101', 'so-arm-102')):
        folder = directory / key
        problem = json.loads((folder / 'input.json').read_text(encoding='utf-8'))
        layout = json.loads((folder / 'layout.json').read_text(encoding='utf-8'))
        check = validate(problem, layout)
        reference = problem['reference_layout']
        if not check['valid'] or not validate(problem, reference)['valid']:
            raise ValueError('Refusing to render packing instructions for an invalid benchmark')
        metrics = comparison(problem, layout)
        model = 'SO-ARM101' if index == 0 else 'SO-ARM102'
        text(36, height - 48, f'{model} | Alan vs computed layout', 20, True)
        text(36, height - 72, 'NOMINAL BOX LAYOUT MATCHES; FULL KIT NOT YET VERIFIED', 10, True, '#a45b16')
        value = metrics['external_volume_l']
        text(36, height - 108, f'Alan: {metrics["reference_external_volume_l"]:.5f} L', 16, True)
        text(308, height - 108, f'Computed: {value:.5f} L', 16, True)
        outer = problem['reference']['external_mm']
        text(36, height - 132, f'{outer[0]} x {outer[1]} x {outer[2]} mm | 7 of 7 boxes | volume change: 0%')
        text(36, height - 151, f'Search: {layout["stats"]["elapsed_seconds"]:.3f} s | no reference coordinates supplied to search')
        text(36, height - 184, 'Alan: reconstructed box positions', 11, True)
        text(308, height - 184, 'Independent computed positions', 11, True)
        for level, z in enumerate(sorted({p['position_mm'][2] for p in layout['placements']})):
            y = height - 375 - level * 205
            plan(problem, reference, 36, y, z)
            plan(problem, layout, 308, y, z)
        text(36, 220, 'What is checked', 12, True)
        text(36, 202, 'Box quantities, rotations, containment, overlap, support and vertical insertion.', 9)
        text(36, 185, '7 mm carton wall; 15 mm foam; 1 mm top reserve; zero nominal lateral gap.', 9)
        text(36, 155, 'What remains open', 12, True)
        lines = [
            'Original part poses and box interiors are not validated by these box diagrams.',
            '101 uses user-confirmed Visual Layout R3: electronics in BOX4; ArUco disassembled.',
        ] if index == 0 else [
            'Current BOM: SO-ARM-102 main 4b9d7eb8; 44 robot + 17 educational printed pieces.',
            'Part poses and purchased-item envelopes remain open; 102 foam is inferred from 101.',
        ]
        lines += ['No claim of full-kit equivalence, manufacturing tolerance or transport qualification.']
        for line_index, line in enumerate(lines):
            text(36, 137 - 16 * line_index, line, 9)
        text(36, 63, 'Sources and hashes: evidence-manifest.json. Coordinates and contents: instruction.html.', 8)
        text(36, 47, 'Reproduce: python scripts/run_benchmarks.py && python scripts/build_comparison_pdf.py', 8)
        text(width - 58, 27, f'{index + 1} / 2', 8)
        pdf.showPage()
    pdf.save()
    return destination


if __name__ == '__main__':
    print(build())
