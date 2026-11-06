from pathlib import Path
import json,numpy as np,trimesh,networkx as nx
root=Path('packaging-results/so-arm-101/regrouped-without-camera');p=json.loads((root/'problem.json').read_text());l=json.loads((root/'layout.json').read_text());items={i['id']:i for i in p['items']};meshes={}
for pose in l['placements']:
 d=json.loads(Path(items[pose['item_id']]['mesh']['path']).read_text());m=trimesh.Trimesh(d['vertices_mm'],d['triangles'],process=False);m.apply_transform(pose['transform']);meshes[pose['unit_id']]=m
members={'nested_base_pair':['F_base#1','L_base#1']};meshes['nested_base_pair']=trimesh.util.concatenate([meshes.pop(k) for k in members['nested_base_pair']])
g=nx.DiGraph();g.add_nodes_from(meshes)
for name,m in meshes.items():
 mgr=trimesh.collision.CollisionManager()
 for other,v in meshes.items():
  if other!=name and all(v.bounds[1,a]>=m.bounds[0,a] and m.bounds[1,a]>=v.bounds[0,a] for a in [0,1]):mgr.add_object(other,v)
 blockers=set()
 for z in [1,2,4,8,12,16,24,32,48,64,80]:
  t=np.eye(4);t[2,3]=z;collision,names=mgr.in_collision_single(m,transform=t,return_names=True)
  blockers.update(names)
 for other in blockers:g.add_edge(name,other)
 print(name,sorted(blockers),flush=True)
components=[sorted(c) for c in nx.strongly_connected_components(g) if len(c)>1]
groups={}
for j,component in enumerate(components):groups[f'preassembled_cluster_{j+1}']=[uid for name in component for uid in members.get(name,[name])]
if not any('nested_base_pair' in c for c in components):groups.update(members)
r={'scope':'sampled_blocking_diagnostics_not_path_certificate','edges':[list(e) for e in g.edges],'components':components,'proposed_groups':groups}
(root/'motion-blocking-diagnostics.json').write_text(json.dumps(r,indent=2));print('GROUPS',json.dumps(groups),flush=True)
