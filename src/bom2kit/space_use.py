"""Measured carton space outside protected source bounds, not usable capacity."""
import math


def clipped_box_union_volume(boxes, low, high):
    """Exact axis-aligned union by coordinate-compressed X slabs, in mm3."""
    import numpy as np
    low=np.asarray(low,dtype=float);high=np.asarray(high,dtype=float)
    if not np.all(np.isfinite([low,high])) or np.any(high<=low):
        raise ValueError('Invalid cavity bounds')
    clipped=[]
    for box in boxes:
        b=np.asarray(box,dtype=float)
        if b.shape!=(2,3) or not np.all(np.isfinite(b)) or np.any(b[1]<b[0]):
            raise ValueError('Invalid protected box')
        a=np.maximum(b[0],low);z=np.minimum(b[1],high)
        if np.all(z>a):clipped.append([a,z])
    if not clipped:return 0.
    boxes=np.asarray(clipped)
    axes=[np.unique(boxes[:,:,k]) for k in range(3)]
    area=np.diff(axes[1])[:,None]*np.diff(axes[2])[None,:]
    indices=[[(int(np.searchsorted(axes[k],b[0,k])),int(np.searchsorted(axes[k],b[1,k])))
              for k in range(3)] for b in boxes]
    total=0.
    for x,dx in enumerate(np.diff(axes[0])):
        occupied=np.zeros(area.shape,dtype=bool)
        for ranges in indices:
            if ranges[0][0]<=x<ranges[0][1]:
                occupied[ranges[1][0]:ranges[1][1],ranges[2][0]:ranges[2][1]]=True
        total+=float(dx)*float(area[occupied].sum())
    return total


def measure_space_use(result,meshes):
    """Separate wall/foam overhead from within-carton unused bounds volume.

    Protected AABBs overestimate irregular part occupancy. Space outside their
    union is a lower bound on unoccupied space, not a claim that another part fits.
    Purchased envelopes retain their accepted dimensional uncertainty.
    """
    import numpy as np
    layers={l['id']:l for l in result['envelope_design']['candidate']['layout']['layers']}
    padding=result['logistics']['policy']['item_padding_mm']
    panels=[*result.get('practical',{}).get('floor_liners',[]),*result.get('practical',{}).get('protective_separators',[])]
    records=[]
    for module in result['logistics']['modules']:
        layer=layers[module['id']];low=np.asarray(layer['position_mm'])+layer['wall_mm'];high=low+layer['inner_mm']
        bounds=[meshes[uid].bounds+np.array([[-padding]*3,[padding]*3]) for uid in module['unit_ids']]
        bounds.extend([p['origin_mm'],np.asarray(p['origin_mm'])+p['dimensions_mm']]
                      for p in panels if p['carton_id']==module['id'])
        cavity=math.prod(layer['inner_mm'])
        occupied=clipped_box_union_volume(bounds,low,high)
        records.append({'carton_id':module['id'],'cavity_l':cavity/1e6,
                        'protected_bounds_union_l':occupied/1e6,
                        'space_outside_protected_bounds_l':max(0.,cavity-occupied)/1e6})
    cavity=sum(r['cavity_l'] for r in records);empty=sum(r['space_outside_protected_bounds_l'] for r in records)
    exterior=math.prod(result['envelope_design']['candidate']['external_mm'])/1e6
    return {'cartons':records,'cavity_l':cavity,'external_l':exterior,
            'outside_inner_cavities_l':exterior-cavity,
            'space_outside_protected_bounds_l':empty,
            'space_outside_protected_bounds_percent':100*empty/cavity if cavity else None,
            'interpretation':'Lower bound on unoccupied cavity space; not additional packable capacity or restraint proof',
            'method':'Exact union of clipped protected source AABBs and declared liners/contact sheets',
            'reference_used':False}
