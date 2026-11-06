from pathlib import Path
import json,numpy as np,trimesh
from bom2kit.mesh_validation import validate_mesh_layout
p=json.loads(Path('packaging-results/so-arm-102/current-box2-greedy-clean/trial-0-problem.json').read_text())
p['items']=[i for i in p['items'] if i['id'] not in ['left','right']]
p['container']={'inner_mm':[233.1,122,68.1],'wall_mm':0};p['clearance_mm']=.1
RX=np.array([[1,0,0],[0,0,-1],[0,1,0]])
positions={'servo':[[0,0,0],[96.5,0,0]],'bottom':[[0,85.2,0],[114,85.2,0],[0,85.2,20.2],[114,85.2,20.2]],'board':[[193,0,0],[193,0,28.2]],'cap':[[193,0,56.4],[0,85.2,40.4]]}
poses=[]
for item in p['items']:
 d=json.loads(Path(item['mesh']['path']).read_text());raw=trimesh.Trimesh(d['vertices_mm'],d['triangles'],process=False)
 for k,pos in enumerate(positions[item['id']]):
  t=np.eye(4)
  if item['id']=='servo':t[:3,:3]=RX
  if item['id']=='cap' and k==1:t[:3,:3]=[[0,-1,0],[1,0,0],[0,0,1]]
  m=raw.copy();m.apply_transform(t);t[:3,3]=-m.bounds[0]+pos
  poses.append({'item_id':item['id'],'unit_id':item['id']+'#'+str(k+1),'transform':t.tolist()})
r={'units':'mm','placements':poses};r['validation']=validate_mesh_layout(p,r)
out=Path('packaging-results/so-arm-102/current-box2-remaining-ten');out.mkdir(exist_ok=True)
for name,data in [('input',p),('layout',r),('validation',r['validation'])]:(out/(name+'.json')).write_text(json.dumps(data,indent=2))
print(json.dumps(r['validation']),flush=True)
