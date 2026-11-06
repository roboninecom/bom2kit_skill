"""Validate seventeen SO101 figures plus the unchanged estimated camera packet."""
from pathlib import Path
import json
import numpy as np
from bom2kit.mesh_validation import validate_mesh_layout

problem = json.loads(Path('packaging-results/so-arm-101/box7-mesh/input.json').read_text())
purchased = json.loads(Path('packaging-results/so-arm-101/regrouped-complete/input.json').read_text())
problem['items'].append(next(item for item in purchased['items'] if item['id'] == 'camera_protected_packet'))
problem['clearance_mm'] = 0.1
placements = []
cube_count = panel_count = 0
# The cone occupies an upper position, so another figure is not placed on its tip.
for item in sorted(problem['items'], key=lambda value: {'cube': 0, 'cylinder': 1, 'cone': 2}.get(value['id'], 3)):
    source = json.loads(Path(item['mesh']['path']).read_text())
    vertices = np.array(source['vertices_mm'])
    for index in range(item.get('quantity', 1)):
        item_id = item['id']
        if item_id == 'camera_protected_packet':
            corner = [0, 0, 0]
        elif item_id in ['cube', 'cylinder', 'cone']:
            slot = cube_count
            cube_count += 1
            corner = [70.3 + 30.3 * (slot % 2), 30.3 * ((slot // 2) % 2), 30.3 * (slot // 4)]
        elif item_id == 'ArUco_core':
            corner = [131, 0, 0]
        elif item_id == 'hex_nut_figure':
            corner = [131, 40.3, 15.3 * index]
        else:
            slot = panel_count
            panel_count += 1
            corner = [0, 0, 36.12 + 4.97 * slot] if slot < 5 else [131, 0, 39.5]
        transform = np.eye(4)
        transform[:3, 3] = np.array(corner) - vertices.min(axis=0)
        placements.append({'item_id': item_id, 'unit_id': f'{item_id}#{index + 1}',
                           'transform': transform.tolist()})
layout = {'units': 'mm', 'placements': placements}
validation = validate_mesh_layout(problem, layout)
layout['validation'] = validation
output = Path('packaging-results/so-arm-101/box7-with-camera')
output.mkdir(exist_ok=True)
for name, data in [('input', problem), ('layout', layout), ('validation', validation)]:
    (output / f'{name}.json').write_text(json.dumps(data, indent=2), encoding='utf8')
print(validation['valid'], validation['errors'], flush=True)
