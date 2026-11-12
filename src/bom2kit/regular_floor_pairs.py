"""Repeated adjacent floor pairs, always handled as individual original parts."""
from copy import deepcopy
import math
from time import perf_counter
from functools import lru_cache
from .part_properties import motif_neighbors


@lru_cache(maxsize=512)
def _source_pose(path,digest,transform):
    import numpy as np
    from .practical_geometry import load_mesh
    mesh=load_mesh({'mesh':{'path':path,'sha256':digest}})
    mesh.apply_transform(np.asarray(transform).reshape(4,4))
    return mesh


_pair_recipes = {}
_pair_attempts = {}


def _recipe_key(first,second,padding,gap):
    # Identical raw mesh hashes and frames can share proposals across file paths.
    return (first[1:],second[1:],padding,gap)


def _feature_offsets(a,b,axis,clearance,low,high,limit=24):
    """Align frequently occurring CAD feature planes; exact CAD still gates fit."""
    import numpy as np
    def planes(mesh):
        values,counts=np.unique(np.round(mesh.vertices[:,axis],2),return_counts=True)
        indices=np.argsort(counts)[-12:]
        return np.unique(np.r_[values[indices],mesh.bounds[:,axis]])
    differences=(planes(a)[:,None]-planes(b)[None,:]).ravel()
    values=np.unique(np.round(np.r_[differences-clearance,differences+clearance,0.],3))
    values=values[(values>=low-1e-7)&(values<=high+1e-7)]
    if len(values)>limit:values=values[np.unique(np.linspace(0,len(values)-1,limit).astype(int))]
    return sorted(values,key=abs)


def _pair_recipe(first_key, second_key, padding, gap, seconds):
    """Reuse a discovered source-relative motif, never another unit's identity.

    Cache keys bind both source hashes, rigid frames and protection. A timed
    search may cache a feasible proposal, but never treats failure as infeasible.
    Independent source and insertion replay is still required by the caller.
    """
    import numpy as np
    import trimesh
    key = _recipe_key(first_key,second_key,padding,gap)
    if key in _pair_recipes:
        return deepcopy(_pair_recipes[key])
    if seconds>0 and _pair_attempts.get(key,0.)>=seconds*.95:
        # Defer an already explored bounded probe; this is not an infeasibility
        # certificate. A larger budget can revisit it, and other partners remain.
        return None
    started = perf_counter()
    a = _source_pose(*first_key); original_b = _source_pose(*second_key)
    area = math.prod(a.extents[:2]+2*padding)+math.prod(original_b.extents[:2]+2*padding)
    manager = trimesh.collision.CollisionManager(); manager.add_object('base', a)
    best = None
    for angle in (180, 0, 90, 270):
        if perf_counter()-started >= seconds: break
        yaw = trimesh.transformations.rotation_matrix(math.radians(angle), [0, 0, 1])
        b = original_b.copy(); b.apply_transform(yaw)
        yaw[:3, 3] -= b.bounds[0]; b.apply_translation(-b.bounds[0])
        moving = trimesh.collision.CollisionManager(); moving.add_object('other', b)
        span=max(a.extents[1],b.extents[1]);clearance=2*padding+gap
        ys=list(dict.fromkeys([0.,*_feature_offsets(a,b,1,clearance,-span,span),
                               *(f*span for f in (.25,-.25,.5,-.5,.75,-.75))]))
        pitch=max(2.,min(a.extents[0],b.extents[0])/16)
        xs=list(dict.fromkeys([*_feature_offsets(a,b,0,clearance,0.,a.extents[0]+clearance),
                               *np.arange(0.,a.extents[0]+clearance+pitch,pitch)]))
        from .floor_pair_voxels import floor_offsets
        voxel_positions=floor_offsets(first_key,second_key,yaw,angle,a.extents,b.extents,padding)
        positions=list(dict.fromkeys([*voxel_positions,*[(x,y) for y in ys for x in xs]]))
        # Charge preparation to elapsed time, but permit a small bounded narrow
        # phase after cold voxel preparation; the runner enforces the hard wall.
        deadline=max(started+seconds,perf_counter()+min(.1,seconds))
        for x,y in positions:
            if perf_counter()>=deadline: break
            low = np.minimum([0., 0., 0.], [x, y, 0.])
            high = np.maximum(a.bounds[1], b.bounds[1]+[x, y, 0.])
            dims = (high-low+2*padding).tolist(); score = math.prod(dims[:2])
            if score >= area*.94 or (best and score >= best['score']): continue
            transform = np.eye(4); transform[:3, 3] = [x, y, 0.]
            moving.set_transform('other', transform)
            if manager.min_distance_other(moving) < 2*padding+gap-1e-6: continue
            best = {'score': score, 'yaw': yaw.tolist(), 'offset': [float(x), float(y), 0.],
                    'low': low.tolist(), 'size': dims,
                    'proposal_method':'voxel_floor_correlation' if (x,y) in voxel_positions else 'feature_planes'}
    if best is not None:
        if len(_pair_recipes) >= 512: _pair_recipes.pop(next(iter(_pair_recipes)))
        _pair_recipes[key] = deepcopy(best)
    if len(_pair_attempts)>=2048:_pair_attempts.pop(next(iter(_pair_attempts)))
    _pair_attempts[key]=max(_pair_attempts.get(key,0.),seconds)
    return best


def make_floor_pairs(units,choices,source_items,padding,gap,*,seconds=3,all_options=None):
    import numpy as np
    started=perf_counter();pending=sorted(units,key=lambda u:-math.prod(u['dimensions'][:2]))
    shapes={};keys={};pairs=[];expansions={};certificates=[];has_void={}
    for iid,(_,option) in choices.items():
        ref=source_items[iid]['mesh']
        keys[iid]=(ref['path'],ref['sha256'],tuple(np.asarray(option['transform']).ravel()))
        mesh=_source_pose(*keys[iid]);shapes[iid]=mesh
        # A hollow declared clamp/bearing proxy can provide floor-space savings
        # without being assumed a load-bearing carton. Preserve its evidence
        # status; independent source/floor replay remains mandatory.
        has_void[iid]=abs(mesh.volume)<.9*math.prod(mesh.extents)
    while pending:
        first=pending.pop(0);members=[{'unit':first,'offset_mm':[0.,0.,0.]}];size=first['dimensions'].copy()
        if has_void[first['item_id']]:
            candidates=[(i,u) for i,u in enumerate(pending) if motif_neighbors(u,first)]
            candidates.sort(key=lambda iu:(iu[1]['item_id']!=first['item_id'],-math.prod(iu[1]['dimensions'][:2])))
            best=None
            for index,other in candidates[:4]:
                iid=other['item_id'];selected_index,selected=choices[iid]
                alternatives=[(selected_index,selected)]
                if all_options and any('contact_frame_signature' in p for p in all_options[iid]):
                    normal=np.asarray(selected['transform'])[2,:3]
                    opposite=[(j,p) for j,p in enumerate(all_options[iid]) if j!=selected_index
                        and np.dot(normal,np.asarray(p['transform'])[2,:3])<-.999
                        and abs(p['dimensions_mm'][2]-selected['dimensions_mm'][2])<.05]
                    alternatives=[*opposite[:1],*alternatives]
                for number,(option_index,option) in enumerate(alternatives):
                    ref=source_items[iid]['mesh'];other_key=(ref['path'],ref['sha256'],tuple(np.asarray(option['transform']).ravel()))
                    cache_key=_recipe_key(keys[first['item_id']],other_key,padding,gap)
                    if perf_counter()-started>=seconds and cache_key not in _pair_recipes:continue
                    recipe=_pair_recipe(keys[first['item_id']],other_key,padding,gap,
                        max(0.,seconds-(perf_counter()-started))/(len(alternatives)-number))
                    if recipe and (best is None or recipe['score']<best[0]):
                        best=(recipe['score'],index,other,np.asarray(recipe['yaw']),recipe['offset'],
                              np.asarray(recipe['low']),recipe['size'],other_key,option_index,recipe.get('proposal_method','feature_planes'))
            if best:
                _,index,other,yaw,offset,low,size,other_key,option_index,search_backend=best;pending.pop(index)
                first_offset=(-low).tolist();second_offset=(np.asarray(offset)-low).tolist()
                transformed=yaw@np.asarray(other_key[2]).reshape(4,4)
                mesh=_source_pose(*other_key).copy();mesh.apply_transform(yaw)
                second=deepcopy(other);second['dimensions']=(mesh.extents+2*padding).tolist()
                members=[{'unit':first,'offset_mm':first_offset},
                         {'unit':second,'offset_mm':second_offset,'transform_override':transformed.tolist(),
                          'stable_option_override':option_index}]
                certificates.append({'unit_ids':[first['unit_id'],other['unit_id']],
                                     'method':'adjacent_individually_supported_floor_pair','bounding_floor_mm':size[:2],
                                     'proposal_search':search_backend})
        cid=f'floor-pattern-{len(pairs)+1}'
        pairs.append({'item_id':cid,'unit_id':cid+'#1','dimensions':size,
                      'orientations':[((0,1,2),tuple(size)),((1,0,2),(size[1],size[0],size[2]))]})
        expansions[cid+'#1']={'members':members,'separators':[]}
    return pairs,expansions,certificates
