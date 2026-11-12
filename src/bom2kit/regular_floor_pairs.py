"""Repeated adjacent floor pairs, always handled as individual original parts."""
from copy import deepcopy
import math
from time import perf_counter


def make_floor_pairs(units,choices,source_items,padding,gap,*,seconds=3):
    import numpy as np
    import trimesh
    from .practical_geometry import load_mesh
    from .packing_states import declared_state
    started=perf_counter();pending=sorted(units,key=lambda u:-math.prod(u['dimensions'][:2]))
    shapes={};pairs=[];expansions={};certificates=[];has_void={}
    for iid,(_,option) in choices.items():
        mesh=load_mesh(source_items[iid]);mesh.apply_transform(option['transform']);shapes[iid]=mesh
        # A hollow declared clamp/bearing proxy can provide floor-space savings
        # without being assumed a load-bearing carton. Preserve its evidence
        # status; independent source/floor replay remains mandatory.
        has_void[iid]=abs(mesh.volume)<.9*math.prod(mesh.extents)
    while pending:
        first=pending.pop(0);members=[{'unit':first,'offset_mm':[0.,0.,0.]}];size=first['dimensions'].copy()
        if has_void[first['item_id']] and perf_counter()-started<seconds:
            a=shapes[first['item_id']];manager=trimesh.collision.CollisionManager();manager.add_object('base',a)
            candidates=list(enumerate(pending))
            candidates.sort(key=lambda iu:(iu[1]['item_id']!=first['item_id'],-math.prod(iu[1]['dimensions'][:2])))
            best=None
            for index,other in candidates[:4]:
                if perf_counter()-started>=seconds:break
                for angle in (180,0,90,270):
                    yaw=trimesh.transformations.rotation_matrix(math.radians(angle),[0,0,1])
                    b=shapes[other['item_id']].copy();b.apply_transform(yaw);yaw[:3,3]-=b.bounds[0];b.apply_translation(-b.bounds[0])
                    area=sum(math.prod(u['dimensions'][:2]) for u in (first,other))
                    for dy in (0.,.25,-.25,.5,-.5,.75,-.75):
                        y=dy*max(a.extents[1],b.extents[1]);pitch=max(2.,min(a.extents[0],b.extents[0])/16)
                        for x in np.arange(0.,a.extents[0]+2*padding+gap+pitch,pitch):
                            if perf_counter()-started>=seconds:break
                            low=np.minimum([0.,0.,0.],[x,y,0.]);high=np.maximum(a.bounds[1],b.bounds[1]+[x,y,0.])
                            dims=(high-low+2*padding).tolist();score=math.prod(dims[:2])
                            if score>=area*.94 or (best and score>=best[0]):continue
                            transform=np.eye(4);transform[:3,3]=[x,y,0.]
                            if manager.in_collision_single(b,transform) or manager.min_distance_single(b,transform)<2*padding+gap-1e-6:continue
                            best=(score,index,other,yaw,[x,y,0.],low,dims)
            if best:
                _,index,other,yaw,offset,low,size=best;pending.pop(index)
                first_offset=(-low).tolist();second_offset=(np.asarray(offset)-low).tolist()
                transformed=yaw@np.asarray(choices[other['item_id']][1]['transform'])
                mesh=shapes[other['item_id']].copy();mesh.apply_transform(yaw)
                second=deepcopy(other);second['dimensions']=(mesh.extents+2*padding).tolist()
                members=[{'unit':first,'offset_mm':first_offset},
                         {'unit':second,'offset_mm':second_offset,'transform_override':transformed.tolist()}]
                certificates.append({'unit_ids':[first['unit_id'],other['unit_id']],
                                     'method':'adjacent_individually_supported_floor_pair','bounding_floor_mm':size[:2]})
        cid=f'floor-pattern-{len(pairs)+1}'
        pairs.append({'item_id':cid,'unit_id':cid+'#1','dimensions':size,
                      'orientations':[((0,1,2),tuple(size)),((1,0,2),(size[1],size[0],size[2]))]})
        expansions[cid+'#1']={'members':members,'separators':[]}
    return pairs,expansions,certificates
