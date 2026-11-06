"""Audit SO102 BOX1 sources and test a rigid two-base packing seed.

This experiment deliberately does not certify the complete BOX1 contents.
"""
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
import trimesh
from bom2kit.mesh_validation import validate_mesh_layout


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / 'packaging-inputs/so-arm-102/repository-main/models'
    output = root / 'packaging-results/evidence-audit/box1-experiment'
    output.mkdir(parents=True, exist_ok=True)
    specification = {
        'SO102.02.010 Base': 2, 'SO102.02.020 Base ring': 2,
        'SO102.02.040 Bottom top plate': 2, 'SO102.02.050 Bottom ring': 2,
        'RB9.01.062.025 Clamp (D6.1)': 2, 'RB9.01.062.012 Main frame (D6.1)': 1,
        'RB9.01.062.075 Camera holder': 1, 'RB9.01.062.090 Camera spacer': 1,
        'SO102 Handle': 1, 'SO102 Trigger': 1, 'SO102 Wrist roll': 1,
    }
    items, audit, meshes = [], [], {}
    for name, quantity in specification.items():
        file = next(p for p in (source / 'stl').rglob('*') if p.is_file() and p.stem == name)
        mesh = trimesh.load(file, force='mesh')
        original_valid = bool(mesh.is_volume)
        provenance = {'path': str(file.relative_to(root)), 'sha256': sha256(file.read_bytes()).hexdigest()}
        if not original_valid:
            # Only disconnected singleton triangles with mathematically zero
            # cross product may be removed. Retained vertices stay unchanged.
            cross = np.cross(mesh.triangles[:,1] - mesh.triangles[:,0],
                             mesh.triangles[:,2] - mesh.triangles[:,0])
            components = trimesh.graph.connected_components(
                mesh.face_adjacency, nodes=np.arange(len(mesh.faces)))
            removed = sorted(int(group[0]) for group in components
                             if len(group) == 1 and np.all(cross[group[0]] == 0))
            if removed:
                keep = np.ones(len(mesh.faces), dtype=bool)
                keep[removed] = False
                mesh = trimesh.Trimesh(mesh.vertices.copy(), mesh.faces[keep], process=False)
                provenance['filter'] = {'removed_face_indices':removed,
                    'criterion':'Disconnected singleton triangle with exactly zero cross product',
                    'retained_vertices_unchanged':True,
                    'index_basis':'trimesh.load process=True face ordering'}
        if not mesh.is_volume:
            step = next(p for p in (source / 'step').rglob('*') if p.is_file() and p.stem == name)
            import cadquery as cq
            shape = cq.importers.importStep(str(step)).val()
            if not shape.isValid():
                raise ValueError(f'Invalid STEP source: {step}')
            vertices, faces = shape.tessellate(0.05)
            # Weld identical positions only; no hole filling or face removal.
            vertices = np.array([[v.x, v.y, v.z] for v in vertices])
            unique, inverse = np.unique(vertices, axis=0, return_inverse=True)
            mesh = trimesh.Trimesh(unique, inverse[np.array(faces)], process=False)
            provenance = {'path': str(step.relative_to(root)), 'sha256': sha256(step.read_bytes()).hexdigest(),
                          'method': 'CAD tessellation tolerance0.05mm, exact duplicate vertex welding only'}
        artifact = output / (name.replace(' ', '_') + '.json')
        artifact.write_text(json.dumps({'units':'mm', 'vertices_mm':mesh.vertices.tolist(),
                                       'triangles':mesh.faces.tolist(), 'provenance':provenance}), encoding='utf-8')
        items.append({'id':name, 'quantity':quantity, 'mesh':{'path':str(artifact),
                      'sha256':sha256(artifact.read_bytes()).hexdigest()}})
        meshes[name] = mesh
        audit.append({'id':name, 'quantity':quantity, 'source':provenance,
                      'original_stl_positive_volume':original_valid,
                      'selected_mesh_positive_volume':bool(mesh.is_volume),
                      'aabb_mm':mesh.extents.tolist(), 'volume_mm3':float(mesh.volume)})
    container = {'inner_mm':[243,113,72], 'protection_mm':0}
    problem = {'units':'mm', 'container':container, 'clearance_mm':0.1, 'items':items,
               'scope':'16 printed pieces only; two6812 bearings omitted; not fullBOX1',
               'container_basis':'User-confirmed external246x116x75 and1.5mm walls: inner243x113x72'}
    (output/'problem-printed-subset.json').write_text(json.dumps(problem,indent=2),encoding='utf-8')
    name = 'SO102.02.010 Base'
    mesh = meshes[name]
    rotation = np.array([[1,0,0],[0,0,1],[0,-1,0]])
    rotated = mesh.vertices @ rotation.T
    placements = []
    for index in range(2):
        transform = np.eye(4)
        transform[:3,:3] = rotation
        transform[:3,3] = -rotated.min(axis=0) + [0.1,0.1,0.1+index*20.2]
        placements.append({'item_id':name, 'unit_id':f'{name}#{index+1}', 'transform':transform.tolist()})
    pair = {**problem, 'items':[items[0]], 'scope':'Two-base rigid packing seed only'}
    layout = {'units':'mm','placements':placements}
    validation = validate_mesh_layout(pair,layout)
    for filename, data in [('source-audit.json',audit),('base-pair-problem.json',pair),
                           ('base-pair-layout.json',layout),('base-pair-validation.json',validation)]:
        (output/filename).write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps({'printed_count':sum(specification.values()), 'pair_valid':validation['valid'],
                      'pair_errors':validation['errors'], 'full_box1_validated':False}))


def incremental_search(optimized=False, frame_first=False, resume=False):
    """Try bounded greedy orders; revalidate every flattened original placement."""
    from bom2kit.mesh_packing import solve_mesh_pair
    output = Path(__file__).resolve().parents[1] / 'packaging-results/evidence-audit/box1-experiment'
    problem = json.loads((output/'problem-printed-subset.json').read_text())
    initial = json.loads((output/('base-pair-optimized-layout.json' if optimized else 'base-pair-layout.json')).read_text())
    tag='frame-first' if frame_first else ('optimized' if optimized else 'initial')
    if optimized:
        bom_source=output.parent/'current102-bom.md'
        proxy=trimesh.creation.annulus(r_min=30,r_max=39/np.cos(np.pi/128),height=10,sections=128)
        proxy_path=output/'bearing6812-conservative-annulus.json'
        proxy_path.write_text(json.dumps({'units':'mm','vertices_mm':proxy.vertices.tolist(),
            'triangles':proxy.faces.tolist(),'provenance':{'source':'SO-ARM-102 docs/bom.md',
            'sha256':sha256(bom_source.read_bytes()).hexdigest(),'dimensions_mm':[60,78,10],
            'model':'Conservative bounding annulus: circumscribed outer polygon, inscribed hole polygon; not actual bearing CAD'}}))
        problem['items'].append({'id':'Bearing6812-proxy','quantity':2,'mesh':{'path':str(proxy_path),
                                    'sha256':sha256(proxy_path.read_bytes()).hexdigest()}})
        problem['scope']='16 printed parts and2dimensionedconservativebearingproxies; not completekit'
        problem['container_basis']='User-confirmed external dimensions and1.5mm walls'
        (output/'problem-with-bearing-proxies.json').write_text(json.dumps(problem,indent=2))
    expected_count=sum(item['quantity']for item in problem['items'])
    by_id = {item['id']:item for item in problem['items']}
    meshes = {}
    for iid, item in by_id.items():
        raw = json.loads(Path(item['mesh']['path']).read_text())
        meshes[iid] = trimesh.Trimesh(raw['vertices_mm'],raw['triangles'],process=False)
    base = 'SO102.02.010 Base'
    if frame_first:
        frame='RB9.01.062.012 Main frame (D6.1)'
        transform=np.eye(4);transform[:3,3]=-meshes[frame].bounds[0]+0.1
        initial={'placements':[{'item_id':frame,'unit_id':frame+'#1','transform':transform.tolist()}]}
    if resume:
        initial=json.loads((output/f'latest-{tag}-order0.json').read_text())
    used={}
    for p in initial['placements']:
        used[p['item_id']]=used.get(p['item_id'],0)+1
    remaining = [(iid,n+1) for iid,item in by_id.items() for n in range(used.get(iid,0),item['quantity'])]
    orderings = [remaining,
                 sorted(remaining,key=lambda u:-np.prod(meshes[u[0]].extents)),
                 sorted(remaining,key=lambda u:np.prod(meshes[u[0]].extents))]
    if optimized:
        orderings=[orderings[1],sorted(remaining,key=lambda u:(u[0]!='Bearing6812-proxy',-np.prod(meshes[u[0]].extents)))]
    if frame_first:
        priority=['RB9.01.062.075 Camera holder',base,'SO102.02.050 Bottom ring',
                  'Bearing6812-proxy','SO102.02.040 Bottom top plate']
        orderings=[sorted(remaining,key=lambda u:(priority.index(u[0]) if u[0] in priority else 99,
                                                -np.prod(meshes[u[0]].extents)))]
    trials=[]
    for order_index, order in enumerate(orderings):
        placements = json.loads(json.dumps(initial['placements']))
        steps=[]
        for iid,number in order:
            current_counts={}
            for p in placements:
                current_counts[p['item_id']]=current_counts.get(p['item_id'],0)+1
            subset={**problem,'items':[{**by_id[k],'quantity':v}for k,v in current_counts.items()]}
            before=validate_mesh_layout(subset,{'units':'mm','placements':placements})
            if not before['valid']:
                raise ValueError(before['errors'])
            parts=[]
            for p in placements:
                m=meshes[p['item_id']].copy();m.apply_transform(p['transform']);parts.append(m)
            compound=trimesh.util.concatenate(parts)
            group_path=output/f'group-{tag}-order{order_index}-step{len(placements)}.json'
            group_path.write_text(json.dumps({'units':'mm','vertices_mm':compound.vertices.tolist(),
                                             'triangles':compound.faces.tolist()}))
            pair={**problem,'items':[{'id':'validated_group','quantity':1,'mesh':{
                'path':str(group_path),'sha256':sha256(group_path.read_bytes()).hexdigest()}},
                {**by_id[iid],'quantity':1}]}
            found=solve_mesh_pair(pair,time_limit=20,pitch_mm=2,candidates_per_rotation=8)
            moving_frame=np.eye(4)
            if found['status']!='validated_static_layout':
                # A second rigid orientation family covers slanted source parts
                # that cannot be represented by the 24 axis rotations alone.
                moving_frame=np.linalg.inv(meshes[iid].bounding_box_oriented.primitive.transform)
                if np.linalg.det(moving_frame[:3,:3]) < 0:
                    moving_frame[0,:] *= -1
                obb=meshes[iid].copy();obb.apply_transform(moving_frame)
                obb_path=output/f'obb-{iid.replace(" ","_")}.json'
                obb_path.write_text(json.dumps({'units':'mm','vertices_mm':obb.vertices.tolist(),
                    'triangles':obb.faces.tolist(),'original_mesh':by_id[iid]['mesh'],
                    'original_to_obb_transform':moving_frame.tolist()}))
                pair['items'][1]={**by_id[iid],'quantity':1,'mesh':{'path':str(obb_path),
                                        'sha256':sha256(obb_path.read_bytes()).hexdigest()}}
                found=solve_mesh_pair(pair,time_limit=25,pitch_mm=1.5,candidates_per_rotation=12)
            record={'next_id':iid,'next_instance':number,'status':found['status'],'search':found['search'],
                    'moving_preorientation':moving_frame.tolist()}
            if found['status']!='validated_static_layout':
                steps.append(record);break
            group_transform=np.array(found['placements'][0]['transform'])
            candidate=[{**p,'transform':(group_transform@np.array(p['transform'])).tolist()}for p in placements]
            candidate.append({'item_id':iid,'unit_id':f'{iid}#{number}',
                              'transform':(np.array(found['placements'][1]['transform'])@moving_frame).tolist()})
            current_counts[iid]=current_counts.get(iid,0)+1
            subset={**problem,'items':[{**by_id[k],'quantity':v}for k,v in current_counts.items()]}
            validation=validate_mesh_layout(subset,{'units':'mm','placements':candidate})
            record['original_identity_validation']=validation
            steps.append(record)
            if not validation['valid']:break
            placements=candidate
            (output/f'latest-{tag}-order{order_index}.json').write_text(json.dumps({
                'units':'mm','placements':placements,'validation':validation,
                'subset_count':len(placements),'bearing_proxies_requested':optimized},indent=2))
            print(json.dumps({'order':order_index,'placed':len(placements),'added':iid}),flush=True)
        trial={'order':order_index,'steps':steps,'placements':placements,'placed_count':len(placements),
               'full_requested_subset':len(placements)==expected_count,'bearing_proxies_requested':optimized}
        trials.append(trial)
        suffix='-resume' if resume else ''
        (output/f'incremental-trials-{tag}{suffix}.json').write_text(json.dumps(trials,indent=2))
        print(json.dumps({'order':order_index,'placed':len(placements),'finished':True}),flush=True)
    return trials


def optimize_base_seed():
    from bom2kit.mesh_packing import solve_mesh_pair
    output=Path(__file__).resolve().parents[1]/'packaging-results/evidence-audit/box1-experiment'
    original=json.loads((output/'base-pair-problem.json').read_text())
    item=original['items'][0]
    data=json.loads(Path(item['mesh']['path']).read_text())
    vertices=np.array(data['vertices_mm'])
    rotation=np.array([[1,0,0],[0,0,1],[0,-1,0]])
    rotated=vertices@rotation.T
    transform=np.eye(4);transform[:3,:3]=rotation;transform[:3,3]=-rotated.min(0)
    path=output/'base-flat-rigid.json'
    path.write_text(json.dumps({'units':'mm','vertices_mm':(rotated-rotated.min(0)).tolist(),
                               'triangles':data['triangles'],'original_mesh':item['mesh'],
                               'original_to_flat_transform':transform.tolist()}))
    problem={**original,'items':[{**item,'mesh':{'path':str(path),
                             'sha256':sha256(path.read_bytes()).hexdigest()}}]}
    result=solve_mesh_pair(problem,time_limit=35,pitch_mm=1,candidates_per_rotation=16)
    if result['status']=='validated_static_layout':
        result['placements']=[{**p,'transform':(np.array(p['transform'])@transform).tolist()}
                              for p in result['placements']]
        result['original_validation']=validate_mesh_layout(original,result)
        if result['original_validation']['valid']:
            (output/'base-pair-optimized-layout.json').write_text(json.dumps(result,indent=2))
    (output/'base-pair-optimization.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'status':result['status'],'envelope':result.get('envelope_mm'),
                      'original_validation':result.get('original_validation',{}).get('valid')}))


if __name__ == '__main__':
    import sys
    if '--nest' in sys.argv:
        incremental_search('--optimized' in sys.argv, '--frame-first' in sys.argv, '--resume' in sys.argv)
    elif '--seed' in sys.argv:
        optimize_base_seed()
    else:
        main()
