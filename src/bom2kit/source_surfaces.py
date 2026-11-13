"""Bounded 3D extreme-point proposals with real source surfaces and load trees."""
import math
from time import perf_counter
from functools import lru_cache


@lru_cache(maxsize=512)
def _prepared_variant(path,digest,transform,angle):
    """Source-bound collision BVH and support faces reused across concepts."""
    import numpy as np
    import trimesh
    from shapely.affinity import affine_transform
    from .regular_cavity_pairs import _surfaces
    base_frame=np.asarray(transform).reshape(4,4)
    base_mesh,base_faces,base_bottom=_surfaces(path,digest,transform)
    yaw=trimesh.transformations.rotation_matrix(math.radians(angle),[0,0,1])
    if angle==90:yaw[0,3]=base_mesh.extents[1]
    if angle==0:mesh,faces,bottom=base_mesh,base_faces,base_bottom
    else:
        mesh=base_mesh.copy();mesh.apply_transform(yaw)
        planar=[0,-1,1,0,base_mesh.extents[1],0]
        faces=[(z,affine_transform(p,planar)) for z,p in base_faces]
        bottom=affine_transform(base_bottom,planar)
    collision=trimesh.collision.CollisionManager();collision.add_object('moving',mesh)
    return {'frame':yaw@base_frame,'mesh':mesh,'faces':faces,'bottom':bottom,'collision':collision}


def propose(items,options,footprint,padding,wall,*,gap=.2,border=7.2,seconds=8,max_height=None,objective='height',priority_units=(),semantic_labels=None,compact_voids=False,minimum_sheet_side=0.):
    import numpy as np
    import trimesh
    from shapely.affinity import translate
    from shapely.geometry import Point
    from .packing_states import declared_state
    if objective not in ('height','volume','footprint'):raise ValueError('Unknown source surface objective')
    started=perf_counter()
    width,depth=[v-2*wall for v in footprint]
    maximum=max_height or 2*max(min(p['dimensions_mm'][2] for p in options[i['id']]) for i in items)
    source_items={i['id']:i for i in items}
    units=[(i['id'],uid) for i in items for uid in i.get('packing_unit_ids',[f"{i['id']}#{n+1}" for n in range(i['quantity'])])]
    priority={uid:index for index,uid in enumerate(priority_units)}
    if set(priority)-{u[1] for u in units}:raise ValueError('Unknown priority source unit')
    units.sort(key=lambda u:(priority.get(u[1],len(priority)),
                             -max(math.prod(p['dimensions_mm'][:2]) for p in options[u[0]]),u[1]))
    manager=trimesh.collision.CollisionManager();placed=[];sheets=[];records=[];variants={};checks=0;preparation=0.;narrow=0
    def poses(iid):
        nonlocal preparation
        if iid in variants:return variants[iid]
        prepare_start=perf_counter()
        source=source_items[iid];available=list(enumerate(options[iid]))
        seeds=[min(available,key=lambda ip:ip[1]['dimensions_mm'][2]),
               min(available,key=lambda ip:math.prod(ip[1]['dimensions_mm'][:2])),
               min(available,key=lambda ip:math.prod(ip[1]['dimensions_mm']))]
        if any('contact_frame_signature' in p for _,p in available):
            for _,seed in list(seeds):
                normal=np.asarray(seed['transform'])[2,:3]
                opposite=[(j,p) for j,p in available if np.dot(normal,np.asarray(p['transform'])[2,:3])<-.999]
                if opposite:seeds.append(max(opposite,key=lambda jp:jp[1]['contact']['center_margin_mm']))
        selected=[]
        for index,option in seeds:
            if index in [p['index'] for p in selected]:continue
            for angle in (0,90):
                variant=_prepared_variant(source['mesh']['path'],source['mesh']['sha256'],
                    tuple(np.asarray(option['transform']).ravel()),angle)
                selected.append({'index':index,**variant})
        preparation+=perf_counter()-prepare_start
        variants[iid]=selected;return selected
    # Source preparation is charged to elapsed time, but cannot consume the
    # entire placement budget before the first large CAD group is considered.
    for iid in source_items:poses(iid)
    deadline=perf_counter()+seconds
    for iid,uid in units:
        if perf_counter()>deadline:break
        candidates=[];current_top=max((p['mesh'].bounds[1,2] for p in placed),default=padding)
        used_x=max((p['mesh'].bounds[1,0] for p in placed),default=0.)
        used_y=max((p['mesh'].bounds[1,1] for p in placed),default=0.)
        occupied_bounds=np.array([p['mesh'].bounds for p in placed])
        def separated_bounds(bounds):
            if not len(occupied_bounds):return True
            distances=np.maximum(0,np.maximum(bounds[0]-occupied_bounds[:,1],occupied_bounds[:,0]-bounds[1]))
            return bool(np.all(np.linalg.norm(distances,axis=1)>=2*padding+gap-1e-6))
        for variant in poses(iid):
            if perf_counter()>deadline:break
            mesh=variant['mesh'];mesh_bounds=mesh.bounds;sx,sy,sz=mesh.extents
            surfaces=[(None,padding,None)]
            for parent in placed:
                if parent['depth']>=2 or declared_state(source_items[parent['item_id']])['kind'] not in ('source_part','factory_carton'):continue
                if semantic_labels and not compact_voids and semantic_labels[parent['item_id']]!=semantic_labels[iid]:continue
                for z,polygon in parent['faces']:
                    surfaces.append((parent,z+2*padding+gap,polygon))
            for parent,z,polygon in surfaces:
                if perf_counter()>deadline:break
                if z+sz+padding>maximum+1e-7:continue
                if parent is None:
                    xs={border+padding,width-border-padding-sx};ys={border+padding,depth-border-padding-sy}
                else:
                    if variant['bottom'].is_empty:continue
                    x0,y0,x1,y1=polygon.bounds
                    xs={x0,x1-sx,polygon.centroid.x-mesh.center_mass[0]}
                    ys={y0,y1-sy,polygon.centroid.y-mesh.center_mass[1]}
                for previous in placed:
                    low,high=previous['mesh'].bounds
                    xs.update((high[0]+2*padding+gap,low[0]-sx-2*padding-gap))
                    ys.update((high[1]+2*padding+gap,low[1]-sy-2*padding-gap))
                if parent is not None:
                    xs={x for x in xs if x0<=x+mesh.center_mass[0]<=x1}
                    ys={y for y in ys if y0<=y+mesh.center_mass[1]<=y1}
                xy=[(x,y) for x in xs for y in ys if x>=border+padding-1e-6 and y>=border+padding-1e-6
                    and x+sx<=width-border-padding+1e-6 and y+sy<=depth-border-padding+1e-6]
                # Preserve collision-free extremes before the bounded narrow
                # phase. Otherwise compact but obviously overlapping candidates
                # can consume the whole queue and hide an empty floor corner.
                ranked_xy=[(not separated_bounds(mesh_bounds+[x,y,z]),x,y) for x,y in xy]
                ranked_xy.sort(key=lambda p:(p[0],max(p[1]+sx,used_x)*max(p[2]+sy,used_y),p[2],p[1]))
                if compact_voids:
                    compact=sorted(ranked_xy,key=lambda p:(max(p[1]+sx,used_x)*max(p[2]+sy,used_y),p[0],p[2],p[1]))
                    ranked_xy=list(dict.fromkeys([*compact[:48],*ranked_xy[:16]]))
                for overlap,x,y in ranked_xy[:64]:
                    if perf_counter()>deadline:break
                    # Prefer low total height, then compact used footprint.
                    occupied_height=max(current_top,z+sz)
                    occupied_area=max(x+sx,used_x)*max(y+sy,used_y)
                    cost=(occupied_height if objective=='height' else occupied_area if objective=='footprint'
                          else occupied_height*occupied_area)
                    if compact_voids:
                        neighbors=[p['mesh'].bounds for p in placed if semantic_labels and semantic_labels[p['item_id']]==semantic_labels[iid]]
                        if neighbors:
                            low=np.min([b[0,:2] for b in neighbors],axis=0);high=np.max([b[1,:2] for b in neighbors],axis=0)
                            growth=np.prod(np.maximum(high,[x+sx,y+sy])-np.minimum(low,[x,y]))-np.prod(high-low)
                            cost+=.1*growth*(occupied_height if objective=='volume' else 1. if objective=='footprint' else 1/max(width,depth))
                        score=(cost,occupied_area,z,overlap,y,x)
                    else:score=(overlap,cost,occupied_area,z,y,x)
                    candidates.append((score,variant,[x,y,z],parent,polygon))
        accepted=None
        ranked_candidates=sorted(candidates,key=lambda row:row[0])
        shortlisted=ranked_candidates[:256]
        # A compact queue can contain hundreds of colliding cavity proposals.
        # Preserve a separately ranked, broad-phase-clear floor fallback so the
        # queue cap cannot hide an existing empty corner behind those proposals.
        shortlist_ids={id(candidate) for candidate in shortlisted}
        free_floor=[candidate for candidate in ranked_candidates[256:]
                    if candidate[3] is None and separated_bounds(candidate[1]['mesh'].bounds+candidate[2])]
        shortlisted.extend(candidate for candidate in free_floor[:32] if id(candidate) not in shortlist_ids)
        for _,variant,position,parent,polygon in shortlisted:
            if perf_counter()>deadline:break
            transform=np.eye(4);transform[:3,3]=position;mesh=variant['mesh'];checks+=1
            bounds=mesh.bounds+position;required=2*padding+gap
            close=any(np.linalg.norm(np.maximum(0,np.maximum(bounds[0]-p['mesh'].bounds[1],p['mesh'].bounds[0]-bounds[1])))<required-1e-6 for p in placed)
            if close:
                narrow+=1;moving=variant['collision'];moving.set_transform('moving',transform)
                if manager.in_collision_other(moving) or manager.min_distance_other(moving)<required-1e-6:continue
            sheet=None
            if parent is not None:
                contact=polygon.intersection(translate(variant['bottom'],xoff=position[0],yoff=position[1]))
                center=Point(mesh.center_mass[0]+position[0],mesh.center_mass[1]+position[1])
                if contact.area<1e-6 or not contact.convex_hull.covers(center) or contact.convex_hull.boundary.distance(center)<.05:continue
                x,y,right,back=contact.bounds;plane=position[2]-2*padding-gap
                if min(right-x,back-y)<minimum_sheet_side-1e-7:continue
                panel=trimesh.creation.box([right-x-.002,back-y-.002,2*padding+gap-.002])
                panel.apply_translation([(x+right)/2,(y+back)/2,plane+padding+gap/2])
                if manager.in_collision_single(panel):continue
                sheet={'lower_unit_id':parent['unit_id'],'upper_unit_id':uid,'origin_mm':[x,y,plane],
                       'dimensions_mm':[right-x,back-y,2*padding+gap],'extra_clearance_mm':gap,
                       'support_surface':'actual_horizontal_face'}
            accepted=(variant,position,parent,sheet);break
        if accepted is None:break
        variant,position,parent,sheet=accepted
        mesh=variant['mesh'].copy();mesh.apply_translation(position)
        frame=variant['frame'].copy();frame[:3,3]+=position
        record={'item_id':iid,'unit_id':uid,'mesh':mesh,'depth':0 if parent is None else parent['depth']+1,
                'faces':[(z+position[2],translate(p,xoff=position[0],yoff=position[1])) for z,p in variant['faces']]}
        placed.append(record);manager.add_object(uid,mesh)
        if sheet:sheets.append(sheet)
        records.append({'item_id':iid,'unit_id':uid,'transform':frame.tolist(),'stable_option':variant['index'],
                        'envelope_position_mm':(mesh.bounds[0]-padding).tolist(),
                        'envelope_dimensions_mm':(mesh.extents+2*padding).tolist()})
    diagnostic={'seconds':perf_counter()-started,'placed':len(placed),'required':len(units),'exact_tests':checks,
                'supported_units':len(sheets),'footprint_mm':list(footprint),
                'preparation_seconds':preparation,'narrow_phase_checks':narrow,'objective':objective,
                'maximum_height_mm':maximum,'priority_units':list(priority_units),'compact_voids':compact_voids,
                'used_source_bounds_mm':None if not placed else [max(p['mesh'].bounds[1,k] for p in placed) for k in range(3)],
                'first_unplaced_unit':None if len(placed)==len(units) else units[len(placed)][1]}
    if len(placed)!=len(units):return {'status':'incomplete_source_surface_proposal',
                                     'reason':'time_budget_exhausted' if perf_counter()>deadline else 'no_checked_placement',**diagnostic}
    used=[max(p['mesh'].bounds[1,k] for p in placed)+padding+(border if k<2 else 0) for k in range(3)]
    pattern={'external_mm':[math.ceil(v+2*wall-1e-8) for v in used],'placements':records,
             'method':'actual_source_surface_tree','protective_separators':sheets,'source_contact_slots':True,
             'preassemblies':0,'source_replay_required':True}
    return {'status':'complete_source_surface_proposal','pattern':pattern,**diagnostic}
