"""Write source-bound instructions for the checked SO101 hierarchical packing recipe."""
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from bom2kit.report import fingerprint

root = Path('packaging-results/so-arm-101/regrouped-without-camera')
problem = json.loads((root / 'problem.json').read_text())
layout = json.loads((root / 'layout.json').read_text())
external = json.loads((root / 'motion-grouped-validation.json').read_text())
internal = json.loads((root / 'internal-group-motion.json').read_text())
groups = json.loads((root / 'motion-blocking-diagnostics.json').read_text())['proposed_groups']
assert external['valid'] and external['input_sha256'] == fingerprint(problem)
assert external['layout_sha256'] == fingerprint(layout) and external['groups_sha256'] == fingerprint(groups)
poses = {pose['unit_id']: pose for pose in layout['placements']}
sources = {}
for item in problem['items']:
    ref = item['mesh']
    assert sha256(Path(ref['path']).read_bytes()).hexdigest() == ref['sha256']
    sources[item['id']] = ref['sha256']
lines = ['# SO-ARM-101 packing recipe', '',
         'Checked contents: 26 printed parts, two adapter packets and one cable packet in the lower group; the camera and fastener/tool packet move to BOX7 with all 17 figures.', '',
         'The lower cavity is 265 × 243 × 72.2 mm. X and Y are its floor axes; +Z points upward. Keep every group in the final orientation shown in mesh-review.html. Directions below are movement directions in this same carton frame.', '',
         '## Prepare five groups outside the carton', '',
         'Place each unit at its recorded final relative pose in the order below. +X means approach from the negative-X side; -Z means approach from above. These internal paths were checked separately from the group insertion paths.', '',
         '| Group | Internal insertion direction | Unit order |', '|---|---|---|']
bindings = {'input_sha256': fingerprint(problem), 'layout_sha256': fingerprint(layout), 'source_sha256': sources, 'groups': {}}
for name, attempts in internal.items():
    attempt = next(value for value in attempts if value['certificate']['valid'])
    rotation = np.array(attempt['rotation'])
    local_problem = json.loads((root / name / 'input.json').read_text())
    local_layout = json.loads((root / name / 'layout.json').read_text())
    certificate = json.loads((root / name / 'motion-validation.json').read_text())
    assert certificate['valid'] and certificate['input_sha256'] == fingerprint(local_problem)
    assert certificate['layout_sha256'] == fingerprint(local_layout)
    shifts = []
    for pose in local_layout['placements']:
        original = np.array(poses[pose['unit_id']]['transform'])
        transformed = np.array(pose['transform'])
        assert np.allclose(transformed[:3, :3], rotation @ original[:3, :3], atol=1e-9, rtol=0)
        shifts.append(transformed[:3, 3] - rotation @ original[:3, 3])
    assert np.allclose(shifts, shifts[0], atol=1e-8, rtol=0)
    direction = rotation.T @ np.array([0, 0, -1])
    label = '+X' if np.allclose(direction, [1, 0, 0]) else '-Z' if np.allclose(direction, [0, 0, -1]) else str(direction.tolist())
    sequence = [uid for step in certificate['packing_sequence'] for uid in step['unit_ids']]
    assert set(sequence) == set(groups[name])
    lines.append(f'| {name} | {label} | ' + ' -> '.join(sequence) + ' |')
    bindings['groups'][name] = {'input_sha256': fingerprint(local_problem), 'layout_sha256': fingerprint(local_layout),
                               'local_rotation_from_carton': rotation.tolist(), 'local_translation_from_carton': shifts[0].tolist(),
                               'insertion_direction_carton': direction.tolist(), 'sequence': sequence}
lines += ['', '## Insert into the lower carton', '', 'Insert every following group or unit vertically downward (-Z), in this order. Keep each prepared group rigid while inserting it.', '']
for index, step in enumerate(external['packing_sequence'], 1):
    lines.append(f"{index}. {step['group_id']}")
box7 = Path('packaging-results/so-arm-101/box7-with-camera-fasteners')
box7_motion = json.loads((box7 / 'motion-validation.json').read_text())
assert box7_motion['valid']
box7_problem = json.loads((box7 / 'input.json').read_text())
box7_layout = json.loads((box7 / 'layout.json').read_text())
assert box7_motion['input_sha256'] == fingerprint(box7_problem)
assert box7_motion['layout_sha256'] == fingerprint(box7_layout)
for item in box7_problem['items']:
    assert sha256(Path(item['mesh']['path']).read_bytes()).hexdigest() == item['mesh']['sha256']
bindings['box7'] = {'input_sha256': fingerprint(box7_problem), 'layout_sha256': fingerprint(box7_layout),
                    'source_sha256': {item['id']: item['mesh']['sha256'] for item in box7_problem['items']}}
lines += ['', '## Pack BOX7', '', 'Use its unchanged 193 × 75 × 61 mm cavity. Insert these units vertically downward (-Z); see ../box7-with-camera-fasteners/mesh-review.html for their recorded positions.', '']
for index, step in enumerate(box7_motion['packing_sequence'], 1):
    lines.append(f"{index}. {step['group_id']}")
lines += ['', '## Evidence and limits', '',
          'All 48 unit placements pass static mesh checks. The five groups have separate internal assembly checks; all external group paths and the 19 individual BOX7 paths pass continuous collision checks. Source and coordinate-frame bindings are in packing-recipe-bindings.json.', '',
          'Purchased packets retain declared assumptions: camera 70 × 70 × 36 mm; two adapters 48 × 39 × 17 mm each; cables 80 × 45 × 12 mm; fasteners/tools 110 x 70 x 18 mm. The geometric clearance is 0.1 mm. Support, hand access, bag behavior and physical packing trials are not certified.']
(root / 'instruction.md').write_text('\n'.join(lines) + '\n', encoding='utf8')
(root / 'packing-recipe-bindings.json').write_text(json.dumps(bindings, indent=2), encoding='utf8')
print(root / 'instruction.md')
