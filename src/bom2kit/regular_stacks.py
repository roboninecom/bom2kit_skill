"""Simple individually loaded stacks with real flat interfaces and protective sheets.

These are not rigid nesting groups. A specified separator occupies the existing
two facing item-padding allowances; geometry is not shrunk to manufacture contact.
"""
import math
from functools import lru_cache


@lru_cache(maxsize=512)
def _pose_caps(path,digest,transform_values):
    import numpy as np
    from .practical_geometry import load_mesh
    mesh=load_mesh({'mesh':{'path':path,'sha256':digest}})
    mesh.apply_transform(np.asarray(transform_values).reshape(4,4))
    return {'top':horizontal_cap(mesh,mesh.bounds[1,2]),'bottom':horizontal_cap(mesh,mesh.bounds[0,2]),
            'center':mesh.center_mass.tolist(),'height':float(mesh.bounds[1,2])}


def horizontal_cap(mesh, z, tolerance=.02,normal_sign=None):
    import numpy as np
    from shapely import polygons,union_all
    triangles=mesh.triangles
    flat=np.max(np.abs(triangles[:,:,2]-z),axis=1)<=tolerance
    if normal_sign is not None:flat &= mesh.face_normals[:,2]*normal_sign>.99
    xy=triangles[flat,:,:2]
    if not len(xy):
        from shapely.geometry import Polygon
        return Polygon()
    a,b=xy[:,1]-xy[:,0],xy[:,2]-xy[:,0]
    area=np.abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])
    return union_all(polygons(xy[area>1e-10]))


def interface_certificate(lower,upper,thickness,*,tolerance=.02,plane_z=None):
    """Real coplanar source faces must support the upper center of mass."""
    import numpy as np
    from shapely.geometry import Point
    z=lower.bounds[1,2] if plane_z is None else plane_z;gap=upper.bounds[0,2]-z
    bottom=horizontal_cap(upper,upper.bounds[0,2],tolerance,normal_sign=-1)
    top=horizontal_cap(lower,z,tolerance,normal_sign=1)
    contact=bottom.intersection(top)
    center=Point(upper.center_mass[:2])
    hull=contact.convex_hull
    margin=hull.boundary.distance(center) if hull.area>0 and hull.covers(center) else -1.
    valid=abs(gap-thickness)<=tolerance and contact.area>1e-6 and margin>=.05
    return {'valid':bool(valid),'source_gap_mm':float(gap),'separator_mm':thickness,
            'actual_interface_area_mm2':float(contact.area),'center_margin_mm':float(margin),
            'interface_bounds_mm':list(contact.bounds) if not contact.is_empty else None,
            'load_capacity_verified':False,'mass_model':'uniform source solids; envelope contents unmeasured'}


def check_stack_support(result, meshes, layers, floor_liner):
    """Replay each source interface and every specified protective sheet.

    The load-line check assumes uniform density for CAD and envelope solids.
    It is a geometric screen, not a shipping or compressive-strength approval.
    """
    import numpy as np
    from shapely.geometry import Point, MultiPoint
    from .packing_states import declared_state
    from .practical_geometry import contact_certificate
    errors=[];records=[]
    sheets=result['practical'].get('protective_separators',[])
    packaging=result['envelope_design']['candidate']['packaging_bom']
    poses={p['unit_id']:p for p in result['layout']['placements']}
    items={i['id']:i for i in result['input']['items']}
    modules={uid:m['id'] for m in result['logistics']['modules'] for uid in m['unit_ids']}
    parents={};children={};by_upper={}
    for sheet in sheets:
        lower=sheet.get('lower_unit_id');upper=sheet.get('upper_unit_id')
        if lower not in meshes or upper not in meshes or lower==upper or upper in parents:
            errors.append('Invalid or duplicate regular-stack dependency');continue
        if modules[lower]!=modules[upper] or sheet.get('carton_id')!=modules[upper]:
            errors.append('Stack interface crosses carton membership');continue
        parents[upper]=lower;children.setdefault(lower,[]).append(upper);by_upper[upper]=sheet
        if declared_state(items[poses[lower]['item_id']])['kind'] not in ('source_part','factory_carton'):
            errors.append(f'Unknown or flexible envelope cannot support a stack: {lower}')
        try:
            origin=np.asarray(sheet['origin_mm'],dtype=float);size=np.asarray(sheet['dimensions_mm'],dtype=float)
            if not np.all(np.isfinite([origin,size])) or min(size)<=0:raise ValueError('Invalid sheet geometry')
            extra=sheet.get('extra_clearance_mm',0.)
            if not math.isfinite(extra) or extra<0 or (extra>0 and extra<result['logistics']['policy']['carton']['gap_mm']-1e-7):
                raise ValueError('Invalid contact sheet clearance')
            plane=origin[2] if sheet.get('support_surface')=='actual_horizontal_face' else meshes[lower].bounds[1,2]
            certificate=interface_certificate(meshes[lower],meshes[upper],2*floor_liner+extra,plane_z=plane)
            bounds=certificate['interface_bounds_mm']
            if bounds is None:raise ValueError('Missing actual contact surface')
            expected_origin=[bounds[0],bounds[1],plane]
            expected_size=[bounds[2]-bounds[0],bounds[3]-bounds[1],2*floor_liner+extra]
            if (sheet not in packaging or sheet.get('quantity')!=1 or sheet.get('type')!='protective_contact_sheet'
                or not np.allclose(origin,expected_origin,atol=.02,rtol=0)
                or not np.allclose(size,expected_size,atol=.02,rtol=0)):
                raise ValueError('Contact sheet does not match the actual source interface and BOM')
            layer=layers[modules[upper]];low=np.asarray(layer['position_mm'])+layer['wall_mm']
            if np.any(origin<low-1e-6) or np.any(origin+size>low+layer['inner_mm']+1e-6):
                raise ValueError('Contact sheet escapes its carton')
            # No third part may occupy the modeled protective sheet volume.
            for uid,mesh in meshes.items():
                if modules[uid]!=modules[upper]:continue
                if uid in (lower,upper) and sheet.get('support_surface')!='actual_horizontal_face':continue
                if np.all(np.minimum(origin+size,mesh.bounds[1])-np.maximum(origin,mesh.bounds[0])>1e-6):
                    import trimesh
                    panel=trimesh.creation.box(size-.002);panel.apply_translation(origin+size/2)
                    manager=trimesh.collision.CollisionManager();manager.add_object('sheet',panel)
                    if manager.in_collision_single(mesh):raise ValueError('Contact sheet intersects another source part')
            if not certificate['valid']:raise ValueError('Actual flat interface does not support the upper part')
        except (KeyError,TypeError,ValueError) as error:errors.append(f'{upper}: {error}')
    if errors:
        return {'valid':False,'errors':errors,'parts':records}
    # Strictly increasing source heights make cycles invalid independently of flags.
    for uid,mesh in meshes.items():
        ancestors=set();current=uid
        while current in parents:
            if current in ancestors:
                errors.append('Cyclic stack support');break
            ancestors.add(current);current=parents[current]
        layer=layers[modules[uid]];floor=layer['position_mm'][2]+layer['wall_mm']+floor_liner
        if uid not in parents:
            certificate=contact_certificate(mesh,plane_z=floor)
            # Several feet/edges can support a source on a continuous floor;
            # a single coplanar triangle is not required for that base contact.
            points=mesh.vertices[np.abs(mesh.vertices[:,2]-floor)<=.02,:2]
            contact=MultiPoint(points).convex_hull
            kind='floor'
        else:
            lower=meshes[parents[uid]]
            sheet=by_upper[uid]
            plane=sheet['origin_mm'][2] if sheet.get('support_surface')=='actual_horizontal_face' else lower.bounds[1,2]
            certificate=interface_certificate(lower,mesh,2*floor_liner+sheet.get('extra_clearance_mm',0.),plane_z=plane)
            contact=horizontal_cap(lower,plane,normal_sign=1).intersection(horizontal_cap(mesh,mesh.bounds[0,2],normal_sign=-1)).convex_hull
            kind='flat_protected_interface'
        descendants=[uid]
        for current in descendants:
            descendants.extend(child for child in children.get(current,[]) if child not in descendants)
        masses=np.array([abs(meshes[k].volume) for k in descendants])
        center=np.average([meshes[k].center_mass for k in descendants],axis=0,weights=masses)
        point=Point(center[:2]);margin=contact.boundary.distance(point) if contact.area>0 and contact.covers(point) else -1
        valid=certificate['valid'] and margin>=.05
        records.append({'unit_id':uid,'carton_id':modules[uid],**certificate,'valid':bool(valid),
                        'support_kind':kind,'upper_load_margin_mm':float(margin),'load_units':descendants})
        if not valid:errors.append(f'No stable actual support for complete stack: {uid}')
    return {'valid':not errors,'errors':errors,'parts':records}


def removal_stability_checker(meshes,sheets,floor_z):
    """Precompute real contact polygons, then check every intermediate load tree."""
    import numpy as np
    from shapely.geometry import MultiPoint,Point
    parents={};children={};contacts={}
    for sheet in sheets:
        lower,upper=sheet['lower_unit_id'],sheet['upper_unit_id']
        if upper in parents or lower not in meshes or upper not in meshes:return lambda remaining:False
        parents[upper]=lower;children.setdefault(lower,[]).append(upper)
        plane=sheet['origin_mm'][2] if sheet.get('support_surface')=='actual_horizontal_face' else meshes[lower].bounds[1,2]
        contacts[upper]=horizontal_cap(meshes[lower],plane,normal_sign=1).intersection(
            horizontal_cap(meshes[upper],meshes[upper].bounds[0,2],normal_sign=-1)).convex_hull
    for uid,mesh in meshes.items():
        if uid not in contacts:
            contacts[uid]=MultiPoint(mesh.vertices[np.abs(mesh.vertices[:,2]-floor_z)<=.02,:2]).convex_hull
    masses={uid:abs(mesh.volume) for uid,mesh in meshes.items()}
    centers={uid:mesh.center_mass[:2] for uid,mesh in meshes.items()}
    def stable(remaining):
        for uid in remaining:
            if uid in parents and parents[uid] not in remaining:return False
            descendants=[uid]
            for current in descendants:
                for child in children.get(current,[]):
                    if child in remaining:
                        if child in descendants:return False
                        descendants.append(child)
            total=sum(masses[k] for k in descendants)
            if total<=0:return False
            center=Point(sum((centers[k]*masses[k] for k in descendants),np.zeros(2))/total)
            polygon=contacts[uid]
            if polygon.area<=0 or not polygon.covers(center) or polygon.boundary.distance(center)<.05:return False
        return True
    return stable


def make_flat_columns(units,choices,source_items,padding,max_height,*,max_count=4,max_overhang_fraction=.25):
    """Form bounded compatible stacks; only actual parts/factory cartons support others."""
    import numpy as np
    from shapely.affinity import translate
    from shapely.geometry import Point
    from .packing_states import declared_state
    surfaces={};kinds={}
    for iid,(_,option) in choices.items():
        ref=source_items[iid]['mesh']
        surfaces[iid]=_pose_caps(ref['path'],ref['sha256'],tuple(np.asarray(option['transform']).ravel()))
        kinds[iid]=declared_state(source_items[iid])['kind']
    pending=sorted(units,key=lambda u:(-math.prod(u['dimensions'][:2]),u['unit_id']))
    columns=[];expansions={}
    while pending:
        base=pending.pop(0);size=list(base['dimensions']);members=[{'unit':base,'offset_mm':[0.,0.,0.]}]
        layers=[];top=translate(surfaces[base['item_id']]['top'],xoff=padding,yoff=padding)
        top_z=surfaces[base['item_id']]['height']+padding
        topkind=kinds[base['item_id']]
        while len(members)<max_count and topkind in ('source_part','factory_carton'):
            options=[]
            for index,unit in enumerate(pending):
                dims=unit['dimensions']
                if size[2]+dims[2]>max_height+1e-7 or any(dims[k]>size[k]*(1+max_overhang_fraction)+1e-7 for k in (0,1)):
                    continue
                # Small overhang is a proposal only: real contact and the entire
                # stack load line, not bounding-box containment, determine support.
                new_footprint=[max(size[k],dims[k]) for k in (0,1)]
                base_shift=[(new_footprint[k]-size[k])/2 for k in (0,1)]
                offset=[(new_footprint[k]-dims[k])/2 for k in (0,1)]+[size[2]]
                surface=surfaces[unit['item_id']]
                contact=translate(top,xoff=base_shift[0],yoff=base_shift[1]).intersection(
                    translate(surface['bottom'],xoff=offset[0]+padding,yoff=offset[1]+padding))
                center=Point(np.asarray(surface['center'][:2])+np.asarray(offset[:2])+padding)
                hull=contact.convex_hull
                if contact.area<=1e-6 or not hull.covers(center) or hull.boundary.distance(center)<.05:continue
                options.append((unit['item_id']!=members[-1]['unit']['item_id'],-math.prod(dims[:2]),index,offset,contact,base_shift,new_footprint))
            if not options:break
            _,_,index,offset,contact,base_shift,new_footprint=min(options,key=lambda entry:entry[:3])
            for member in members:
                for k in (0,1):member['offset_mm'][k]+=base_shift[k]
            for sheet in layers:
                for k in (0,1):sheet['origin_mm'][k]+=base_shift[k]
            size[:2]=new_footprint
            unit=pending.pop(index);x,y,right,back=contact.bounds
            layers.append({'lower_unit_id':members[-1]['unit']['unit_id'],'upper_unit_id':unit['unit_id'],
                           'origin_mm':[x,y,top_z],'dimensions_mm':[right-x,back-y,2*padding]})
            members.append({'unit':unit,'offset_mm':offset});size[2]+=unit['dimensions'][2]
            surface=surfaces[unit['item_id']]
            top=translate(surface['top'],xoff=offset[0]+padding,yoff=offset[1]+padding)
            top_z=surface['height']+offset[2]+padding;topkind=kinds[unit['item_id']]
        cid=f"regular-column-{len(columns)+1}"
        columns.append({'item_id':cid,'unit_id':cid+'#1','dimensions':size,
                        'orientations':[((0,1,2),tuple(size)),((1,0,2),(size[1],size[0],size[2]))]})
        expansions[cid+'#1']={'members':members,'separators':layers}
    return columns,expansions
