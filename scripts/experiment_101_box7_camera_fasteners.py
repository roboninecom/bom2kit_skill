"""Reflow all seventeen figures, unchanged camera and fastener packet in BOX7."""
from hashlib import sha256
from pathlib import Path
import json
import numpy as np
import trimesh
from bom2kit.mesh_validation import validate_mesh_layout
from bom2kit.mesh_motion import check_vertical_sequence

problem = json.loads(Path('packaging-results/so-arm-101/box7-with-camera/input.json').read_text())
catalogue = json.loads(Path('packaging-inputs/benchmarks/purchased-assumptions/101-hardware-flexible.json').read_text())
fastener = next(item for item in catalogue['items'] if item['id'] == 'fastener_and_tools_packet')
output = Path('packaging-results/so-arm-101/box7-with-camera-fasteners')
output.mkdir(exist_ok=True)
mesh = trimesh.creation.box(fastener['dimensions_mm'])
source = output / 'fastener-envelope.json'
source.write_text(json.dumps({'units':'mm','vertices_mm':mesh.vertices.tolist(),'triangles':mesh.faces.tolist()}, indent=2))
problem['items'].append({**fastener,'mesh':{'path':str(source.resolve()),'sha256':sha256(source.read_bytes()).hexdigest()}})
problem['scope'] = 'All original seventeen figures plus unchanged declared camera and fastener/tool envelopes.'
placements=[]
cube_count=panel_count=0
for item in sorted(problem['items'],key=lambda i:{'cube':0,'cylinder':1,'cone':2}.get(i['id'],3)):
    data=json.loads(Path(item['mesh']['path']).read_text())
    vertices=np.array(data['vertices_mm'])
    for index in range(item.get('quantity',1)):
        item_id=item['id']
        rotation=np.eye(3)
        if item_id=='fastener_and_tools_packet':corner=[0,0,0]
        elif item_id=='camera_protected_packet':corner=[0,0,18.12]
        elif item_id=='ArUco_core':corner=[70.3,0,18.12]
        elif item_id in ['cube','cylinder','cone']:
            slot=cube_count;cube_count+=1
            corner=[110.3+30.3*(slot%2),30.3*((slot//2)%2),30.3*(slot//4)]
        elif item_id=='hex_nut_figure':
            corner=[70.3,39.5,18.12+15.3*index] if index<2 else [140.6,30.3,30.3]
        else:
            slot=panel_count;panel_count+=1
            if slot==0:corner=[0,0,54.24]
            elif slot<=3:corner=[140.6,30.3,45.42+4.97*(slot-1)]
            else:
                rotation=np.array([[0,0,1],[0,1,0],[-1,0,0]])
                corner=[181+4.97*(slot-4),0,0]
        transform=np.eye(4);transform[:3,:3]=rotation
        transform[:3,3]=np.array(corner)-(vertices@rotation.T).min(axis=0)
        placements.append({'item_id':item_id,'unit_id':f'{item_id}#{index+1}','transform':transform.tolist()})
layout={'units':'mm','placements':placements}
validation=validate_mesh_layout(problem,layout)
layout['validation']=validation
motion=check_vertical_sequence(problem,layout)
for name,value in [('input',problem),('layout',layout),('validation',validation),('motion-validation',motion)]:
    (output/f'{name}.json').write_text(json.dumps(value,indent=2),encoding='utf8')
print(json.dumps({'valid':validation['valid'],'errors':validation['errors'],'motion_valid':motion['valid'],'unresolved':motion.get('unresolved_groups')}),flush=True)
