"""Search all fourteen BOX2 meshes in a flexible layer, then certify its envelope."""
import json
from pathlib import Path
import numpy as np
from bom2kit.mesh_search import solve_mesh_kit
from bom2kit.mesh_validation import validate_mesh_layout

source = Path('packaging-results/so-arm-102/current-box2-greedy-clean/trial-0-problem.json')
problem = json.loads(source.read_text())
problem['container'] = {'inner_mm': [332, 246, 68.1], 'wall_mm': 0}
problem['clearance_mm'] = 0.1
order = ['servo#1', 'servo#2', 'left#1', 'right#1', 'left#2', 'right#2',
         'bottom#1', 'bottom#2', 'bottom#3', 'bottom#4', 'board#1', 'board#2', 'cap#1', 'cap#2']
for item in problem['items']:
    if item['id'] == 'servo':
        item['orientation_hint'] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
result = solve_mesh_kit(problem, time_limit=300, beam_width=8, voxel_overlap_cells=100,
                        pitch_mm=2, positions_per_rotation=8, order=order,
                        checkpoint_dir='packaging-results/so-arm-102/current-box2-full-layer',
                        progress=lambda event: print(json.dumps(event), flush=True))
if not result['validation']['valid']:
    raise SystemExit('No complete validated candidate within this search budget')
items = {item['id']: item for item in problem['items']}
upper = np.zeros(3)
for pose in result['placements']:
    mesh = json.loads(Path(items[pose['item_id']]['mesh']['path']).read_text())
    transform = np.array(pose['transform'])
    vertices = np.array(mesh['vertices_mm']) @ transform[:3, :3].T + transform[:3, 3]
    upper = np.maximum(upper, vertices.max(axis=0))
problem['container']['inner_mm'] = (np.ceil(upper * 10 + 1e-6) / 10).tolist()
result['validation'] = validate_mesh_layout(problem, result)
output = Path('packaging-results/so-arm-102/current-box2-compact-fourteen')
output.mkdir(exist_ok=True)
for name, data in [('input', problem), ('layout', result), ('validation', result['validation'])]:
    (output / f'{name}.json').write_text(json.dumps(data, indent=2), encoding='utf8')
print(json.dumps({'valid': result['validation']['valid'], 'inner_mm': problem['container']['inner_mm']}))
