"""Validate unchanged folded purchased envelopes in SO101 BOX6."""
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
import trimesh
from bom2kit.validation import validate
from bom2kit.mesh_validation import validate_mesh_layout
from bom2kit.mesh_motion import check_vertical_sequence

source = Path('packaging-inputs/benchmarks/purchased-assumptions/101-hardware-flexible.json')
catalogue = json.loads(source.read_text())
selected = ['PSU12_with_DC_lead', 'PSU5_with_DC_lead', 'USB_packet', 'regional_AC_cord_packet']
items = [item for item in catalogue['items'] if item['id'] in selected]
problem = {'units': 'mm', 'container': {'inner_mm': [193, 165, 61], 'wall_mm': 1.5},
           'gap_mm': 0.1, 'allow_dunnage': True, 'items': items,
           'source_sha256': sha256(source.read_bytes()).hexdigest(),
           'packing_assumption': 'Use the unchanged declared folded cord and sleeved PSU envelopes.',
           'reassigned_items': {'fastener_and_tools_packet#1': 'BOX7 with camera and seventeen figures; independently validated'},
           'dunnage_assumption': 'One 135 x 40 x 0.1 mm separator between the AC cord packets; geometric support only.'}
recipe = [('PSU12_with_DC_lead', 1, [0, 0, 0], [0, 1, 2]),
          ('PSU5_with_DC_lead', 1, [0, 52.1, 0], [0, 1, 2]),
          ('USB_packet', 1, [120.1, 0, 0], [1, 0, 2]),
          ('regional_AC_cord_packet', 1, [0, 110.1, 0], [0, 1, 2]),
          ('regional_AC_cord_packet', 2, [0, 110.1, 30.1], [0, 1, 2])]
by_id = {item['id']: item for item in items}
box_poses = []
mesh_poses = []
output = Path('packaging-results/so-arm-101/box6-folded-packets')
(output / 'meshes').mkdir(parents=True, exist_ok=True)
mesh_items = []
for item in items:
    mesh = trimesh.creation.box(item['dimensions_mm'])
    path = output / 'meshes' / (item['id'] + '.json')
    path.write_text(json.dumps({'units': 'mm', 'vertices_mm': mesh.vertices.tolist(), 'triangles': mesh.faces.tolist()}, indent=2))
    mesh_items.append({**item, 'mesh': {'path': str(path.resolve()), 'sha256': sha256(path.read_bytes()).hexdigest()}})
for item_id, number, corner, rotation in recipe:
    size = np.array(by_id[item_id]['dimensions_mm'])[rotation]
    if item_id == 'regional_AC_cord_packet' and number == 2:
        box_poses.append({'kind': 'dunnage', 'item_id': '__support__cord_separator', 'unit_id': '__support__cord_separator',
                          'position_mm': [0, 110.1, 30], 'dimensions_mm': [135, 40, 0.1], 'rotation': [0, 1, 2]})
    box_poses.append({'item_id': item_id, 'unit_id': f'{item_id}#{number}', 'position_mm': corner,
                      'dimensions_mm': size.tolist(), 'rotation': rotation})
    transform = np.eye(4)
    if rotation == [1, 0, 2]:
        transform[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
    transform[:3, 3] = np.array(corner) + size / 2
    mesh_poses.append({'item_id': item_id, 'unit_id': f'{item_id}#{number}', 'transform': transform.tolist()})
box_layout = {'units': 'mm', 'placements': box_poses}
box_layout['validation'] = validate(problem, box_layout)
mesh_problem = {**problem, 'items': mesh_items, 'clearance_mm': 0.1,
                'scope': 'Five purchased packet meshes; the separating sheet is certified as dunnage in the box certificate.'}
mesh_layout = {'units': 'mm', 'placements': mesh_poses}
mesh_layout['validation'] = validate_mesh_layout(mesh_problem, mesh_layout)
motion = check_vertical_sequence(mesh_problem, mesh_layout)
for name, value in [('box-input', problem), ('box-layout', box_layout), ('input', mesh_problem),
                    ('layout', mesh_layout), ('validation', mesh_layout['validation']), ('motion-validation', motion)]:
    (output / f'{name}.json').write_text(json.dumps(value, indent=2), encoding='utf8')
print(json.dumps({'box_valid': box_layout['validation']['valid'], 'box_errors': box_layout['validation']['errors'],
                  'mesh_valid': mesh_layout['validation']['valid'], 'mesh_errors': mesh_layout['validation']['errors'],
                  'motion_valid': motion['valid']}), flush=True)
