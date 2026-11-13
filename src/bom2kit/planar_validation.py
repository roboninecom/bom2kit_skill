"""Planar shape certificates for floor-supported, individually handled parts."""
from collections import Counter
import math


def validate_floor_footprints(items, poses, inner, gap):
    """Allow overlapping bounding boxes only when the complete padded shapes do not overlap."""
    import numpy as np
    from shapely.geometry import shape, box
    from shapely.affinity import translate
    errors=[];seen=[];placed=[];by_id={i['id']:i for i in items}
    expected=Counter({i['id']:i.get('quantity',1) for i in items})
    for p in poses:
        try:
            item=by_id[p['item_id']];seen.append(p['item_id'])
            if p['rotation'] != [0,1,2] or not np.allclose(p['dimensions_mm'],item['dimensions_mm'],atol=1e-8,rtol=0):
                raise ValueError('Changed planar envelope orientation or dimensions')
            x,y,z=p['position_mm'];w,d,h=p['dimensions_mm']
            if not all(math.isfinite(v) for v in [x,y,z,w,d,h]) or min(w,d,h)<=0:
                raise ValueError('Invalid planar dimensions')
            if abs(z)>1e-7 or min(x,y)<-1e-7 or x+w>inner[0]+1e-7 or y+d>inner[1]+1e-7 or h>inner[2]+1e-7:
                raise ValueError('Planar item must lie on its carton floor and inside its cavity')
            polygon=shape(item['footprint'])
            if not polygon.is_valid or polygon.is_empty or polygon.area<=0:
                raise ValueError('Invalid planar footprint')
            if not box(0,0,w,d).buffer(1e-7).covers(polygon):
                raise ValueError('Planar footprint escapes its declared envelope')
            polygon=translate(polygon,xoff=x,yoff=y)
            for uid,other in placed:
                if polygon.intersection(other).area>1e-7 or polygon.distance(other)<gap-1e-7:
                    errors.append(f'Projected clearance violation: {p["unit_id"]}, {uid}')
            placed.append((p['unit_id'],polygon))
        except (KeyError,ValueError,TypeError) as error:errors.append(str(error))
    if Counter(seen)!=expected:errors.append('Planar source quantities differ')
    return {'valid':not errors,'errors':errors,'scope':'Complete padded 2D footprints on carton floor; source binding checked separately'}


def check_projection_binding(result):
    """Bind every slot to its original source and unchanged XYZ protection."""
    import numpy as np
    from shapely.geometry import shape
    from shapely.affinity import translate
    from .practical_geometry import load_mesh,projected_polygon
    candidate=result['envelope_design']['candidate']
    modes={layer.get('placement_check') for layer in candidate['layout']['layers']}
    planar=candidate['input'].get('planar_footprints',False) or 'planar' in modes
    errors=[];items={i['id']:i for i in candidate['input']['items']}
    original={p['unit_id']:p for p in result['layout']['placements']}
    meshes={i['id']:load_mesh(i) for i in result['input']['items']}
    padding=result['logistics']['policy']['item_padding_mm']
    source_slots=candidate['input'].get('source_clearance_slots',False) or bool(modes & {'source_floor','source_contact'})
    if source_slots and candidate['input'].get('source_padding_mm')!=padding:
        errors.append('Source floor mode changed the protection policy')
    for slot in candidate['layout']['placements']:
        members=result.get('groups',{}).get('assembly-'+slot['unit_id'],[slot['unit_id']])
        if len(members)!=1:
            errors.append('Planar slots must represent individual source units');continue
        pose=original[members[0]];mesh=meshes[pose['item_id']].copy();mesh.apply_transform(pose['transform'])
        if source_slots:
            slot_item=items[slot['item_id']]
            transform=np.asarray(slot_item['source_transform']).copy();transform[:3,3]+=np.asarray(slot['position_mm'])
            source=next(i for i in result['input']['items'] if i['id']==pose['item_id'])
            if slot_item['source_mesh']!=source['mesh'] or not np.allclose(transform,pose['transform'],atol=1e-7,rtol=0):
                errors.append('Source floor binding differs from original CAD/pose')
        low=np.asarray(slot['position_mm']);high=low+slot['dimensions_mm']
        axes=(2,) if planar else (0,1,2)
        if any(mesh.bounds[0,k]-padding<low[k]-1e-6 or mesh.bounds[1,k]+padding>high[k]+1e-6 for k in axes):
            errors.append(f'Slot omits original geometry/protection: {members[0]}')
        if not planar:continue
        actual=projected_polygon(mesh,padding)
        declared=translate(shape(items[slot['item_id']]['footprint']),xoff=slot['position_mm'][0],yoff=slot['position_mm'][1])
        if actual.difference(declared.buffer(1e-6)).area>1e-5:
            errors.append(f'Planar footprint omits original geometry/protection: {members[0]}')
    return {'valid':not errors,'errors':errors,'scope':'Original source bounds/projections and unchanged XYZ item padding'}
