from pathlib import Path
import json,numpy as np,trimesh
from bom2kit.mesh_motion import check_vertical_sequence
root=Path('packaging-results/so-arm-101/regrouped-without-camera');p=json.loads((root/'problem.json').read_text());l=json.loads((root/'layout.json').read_text());groups=json.loads((root/'motion-blocking-diagnostics.json').read_text())['proposed_groups'];items={i['id']:i for i in p['items']};poses={x['unit_id']:x for x in l['placements']}
rots=[np.eye(3),np.diag([1,-1,-1]),np.array([[0,0,1],[0,1,0],[-1,0,0]]),np.array([[0,0,-1],[0,1,0],[1,0,0]]),np.array([[1,0,0],[0,0,1],[0,-1,0]]),np.array([[1,0,0],[0,0,-1],[0,1,0]])]
results={}
for name,uids in groups.items():
 attempts=[]
 for index,R in enumerate(rots):
  T=np.eye(4);T[:3,:3]=R;low=np.full(3,np.inf);high=-low.copy();placed=[]
  for uid in uids:
   pose=poses[uid];d=json.loads(Path(items[pose['item_id']]['mesh']['path']).read_text());t=T@np.array(pose['transform']);v=np.array(d['vertices_mm'])@t[:3,:3].T+t[:3,3];low=np.minimum(low,v.min(axis=0));high=np.maximum(high,v.max(axis=0));placed.append({**pose,'transform':t.tolist()})
  for pose in placed:
   t=np.array(pose['transform']);t[:3,3]-=low;pose['transform']=t.tolist()
  q={**p,'container':{'inner_mm':(high-low+.01).tolist()},'items':[items[poses[u]['item_id']] for u in uids]};lay={'units':'mm','placements':placed};r=check_vertical_sequence(q,lay,time_limit=30);attempts.append({'rotation_index':index,'rotation':R.tolist(),'certificate':r});print(name,index,r['valid'],r.get('unresolved_groups'),flush=True)
  if r['valid']:
   out=root/name;out.mkdir(exist_ok=True)
   for k,v in [('input',q),('layout',lay),('motion-validation',r)]:(out/(k+'.json')).write_text(json.dumps(v,indent=2))
   break
 results[name]=attempts
 (root/'internal-group-motion.json').write_text(json.dumps(results,indent=2))
