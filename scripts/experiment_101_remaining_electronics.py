from pathlib import Path
import json
from bom2kit.mesh_search import solve_mesh_kit
r=Path('packaging-results/so-arm-101/regrouped-complete');p=json.loads((r/'input.json').read_text());p['items']=[i for i in p['items'] if i['id']!='camera_protected_packet'];p['reassigned_items']={'camera_protected_packet#1':'box7-with-camera'}
s=json.loads((r/'checkpoint.json').read_text())['placements']
l=solve_mesh_kit(p,time_limit=240,beam_width=4,pitch_mm=2,positions_per_rotation=16,voxel_overlap_cells=100,seed_placements=s,checkpoint_dir='packaging-results/so-arm-101/regrouped-without-camera',progress=lambda e:print(json.dumps(e),flush=True))
print(l['status'],len(l['placements']),l['validation']['errors'],flush=True)
