"""Individually inserted pairs resting on actual horizontal source surfaces.

Internal cavity floors may support another part; an arbitrary void or a bounding
box top cannot. Geometry, padding, support and grip paths require final replay.
"""
import math
from functools import lru_cache
from time import perf_counter
from .part_properties import motif_neighbors


@lru_cache(maxsize=256)
def _surfaces(path,digest,transform):
    import numpy as np
    from .practical_geometry import load_mesh
    from .regular_stacks import horizontal_cap
    mesh=load_mesh({'mesh':{'path':path,'sha256':digest}})
    mesh.apply_transform(np.asarray(transform).reshape(4,4))
    triangles=mesh.triangles
    horizontal=(np.ptp(triangles[:,:,2],axis=1)<.02)&(mesh.face_normals[:,2]>.99)
    levels=sorted(set(np.round(triangles[horizontal,:,2].mean(axis=1),3)))
    shelves=[(float(z),horizontal_cap(mesh,z,normal_sign=1)) for z in levels]
    shelves=sorted((s for s in shelves if s[1].area>1),key=lambda s:-s[1].area)[:10]
    return mesh,shelves,horizontal_cap(mesh,mesh.bounds[0,2],normal_sign=-1)


def make_supported_pairs(units,choices,source_items,padding,gap,max_height,*,seconds=3,minimum_sheet_side=0.):
    import numpy as np
    import trimesh
    from shapely.affinity import translate
    from shapely.geometry import Point
    from .packing_states import declared_state
    started=perf_counter();surfaces={}
    for iid,(_,option) in choices.items():
        ref=source_items[iid]['mesh']
        surfaces[iid]=_surfaces(ref['path'],ref['sha256'],tuple(np.asarray(option['transform']).ravel()))
    prepared=perf_counter();deadline=prepared+seconds;tested=0
    pending=sorted(units,key=lambda u:(-math.prod(u['dimensions']),u['unit_id']))
    packed=[];expansions={};certificates=[]
    while pending:
        first=pending.pop(0);a,shelves,_=surfaces[first['item_id']]
        members=[{'unit':first,'offset_mm':[0.,0.,0.]}];sheets=[];size=first['dimensions'].copy()
        best=None
        if declared_state(source_items[first['item_id']])['kind'] in ('source_part','factory_carton') and perf_counter()<deadline:
            manager=trimesh.collision.CollisionManager();manager.add_object('lower',a)
            eligible=[(i,u) for i,u in enumerate(pending) if motif_neighbors(u,first) and all(u['dimensions'][k]<=first['dimensions'][k]*1.25 for k in (0,1))]
            ranked=sorted(eligible,key=lambda iu:(iu[1]['item_id']!=first['item_id'],-math.prod(iu[1]['dimensions'])))
            candidates=ranked[:8]+[entry for entry in ranked[-4:] if entry not in ranked[:8]]
            for index,unit in candidates:
                b,_,bottom=surfaces[unit['item_id']]
                if bottom.is_empty:continue
                for plane,shelf in shelves:
                    if perf_counter()>=deadline:break
                    offsets=[(a.bounds.mean(axis=0)[:2]-b.bounds.mean(axis=0)[:2]).tolist(),
                             [shelf.centroid.x-b.center_mass[0],shelf.centroid.y-b.center_mass[1]]]
                    # A useful recess need not lie at the whole part's centroid.
                    # Probe actual connected support patches and their boundaries.
                    components=list(shelf.geoms) if shelf.geom_type=='MultiPolygon' else [shelf]
                    for patch in sorted(components,key=lambda p:-p.area)[:6]:
                        anchor=patch.representative_point();x0,y0,x1,y1=patch.bounds
                        xs=(x0-b.bounds[0,0],x1-b.bounds[1,0],anchor.x-b.center_mass[0])
                        ys=(y0-b.bounds[0,1],y1-b.bounds[1,1],anchor.y-b.center_mass[1])
                        offsets.extend([x,y] for x in xs for y in ys)
                    offsets=list(dict.fromkeys(tuple(round(v,6) for v in xy) for xy in offsets))
                    for xy in offsets:
                        if perf_counter()>=deadline:break
                        offset=np.array([*xy,plane+2*padding+gap])
                        low=np.minimum(a.bounds[0],b.bounds[0]+offset)
                        high=np.maximum(a.bounds[1],b.bounds[1]+offset)
                        dims=high-low+2*padding
                        if dims[2]>max_height+1e-7 or any(dims[k]>first['dimensions'][k]*1.25 for k in (0,1)):continue
                        score=math.prod(dims)
                        if best and score>=best[0]:continue
                        if score>=.94*(math.prod(first['dimensions'])+math.prod(unit['dimensions'])):continue
                        contact=shelf.intersection(translate(bottom,xoff=xy[0],yoff=xy[1]))
                        center=Point(b.center_mass[0]+xy[0],b.center_mass[1]+xy[1])
                        if contact.area<1e-6 or not contact.convex_hull.covers(center) or contact.convex_hull.boundary.distance(center)<.05:continue
                        transform=np.eye(4);transform[:3,3]=offset
                        tested+=1
                        if manager.in_collision_single(b,transform) or manager.min_distance_single(b,transform)<2*padding+gap-1e-6:continue
                        # A rectangular protective sheet must also fit the cavity;
                        # disconnected contact pads cannot conceal a central boss.
                        x,y,right,back=contact.bounds
                        if min(right-x,back-y)<minimum_sheet_side-1e-7:continue
                        sheet=trimesh.creation.box([right-x-.002,back-y-.002,2*padding+gap-.002])
                        sheet.apply_translation([(x+right)/2,(y+back)/2,plane+padding+gap/2])
                        if manager.in_collision_single(sheet):continue
                        best=(score,index,unit,offset,low,dims,plane,contact)
        if best:
            _,index,unit,offset,low,dims,plane,contact=best;pending.pop(index)
            members=[{'unit':first,'offset_mm':(-low).tolist()},
                     {'unit':unit,'offset_mm':(offset-low).tolist()}]
            size=dims.tolist();x,y,right,back=contact.bounds
            sheets=[{'lower_unit_id':first['unit_id'],'upper_unit_id':unit['unit_id'],
                     'origin_mm':[x+padding-low[0],y+padding-low[1],plane+padding-low[2]],
                     'dimensions_mm':[right-x,back-y,2*padding+gap],
                     'extra_clearance_mm':gap,'support_surface':'actual_horizontal_face'}]
            certificates.append({'unit_ids':[first['unit_id'],unit['unit_id']],
                                 'method':'individually_inserted_supported_pair','internal_plane':plane<a.bounds[1,2]-.02})
        uid=f'supported-pair-{len(packed)+1}#1'
        packed.append({'item_id':uid,'unit_id':uid,'dimensions':size,
                       'orientations':[((0,1,2),tuple(size)),((1,0,2),(size[1],size[0],size[2]))]})
        expansions[uid]={'members':members,'separators':sheets}
    return packed,expansions,certificates,{'preparation_seconds':prepared-started,'search_seconds':perf_counter()-prepared,
                                         'exact_pair_tests':tested,'selected_pairs':len(certificates),
                                         'internal_support_pairs':sum(c['internal_plane'] for c in certificates)}
