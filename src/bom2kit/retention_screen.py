"""Conservative evidence of free rigid translation inside a closed carton.

An empty swept AABB proves a free path in the declared geometry. A blocked AABB
does not prove restraint: concavities, rotation, friction and compliance are not
resolved here. This screen cannot issue a shipping qualification.
"""
import math


def free_box_translation(bounds, obstacles, cavity_low, cavity_high, axis, sign):
    """Return a conservative free-path length, or unknown for initial overlaps."""
    import numpy as np
    b=np.asarray(bounds,dtype=float)
    length=float(cavity_high[axis]-b[1,axis] if sign>0 else b[0,axis]-cavity_low[axis])
    if length < -1e-6:return None
    for obstacle in obstacles:
        o=np.asarray(obstacle,dtype=float)
        if any(min(b[1,k],o[1,k])-max(b[0,k],o[0,k])<=1e-8 for k in range(3) if k!=axis):
            continue
        if min(b[1,axis],o[1,axis])-max(b[0,axis],o[0,axis])>1e-8:
            return None
        distance=o[0,axis]-b[1,axis] if sign>0 else b[0,axis]-o[1,axis]
        if distance>=-1e-8:length=min(length,max(0.,float(distance)))
    return max(0.,length)


def screen_retention(result, *, movement_threshold_mm=5.):
    import numpy as np
    from .practical_geometry import load_mesh
    if not math.isfinite(movement_threshold_mm) or movement_threshold_mm<=0:
        raise ValueError('Positive finite diagnostic movement threshold required')
    items={i['id']:i for i in result['input']['items']};sources={iid:load_mesh(i) for iid,i in items.items()}
    bounds={}
    for p in result['layout']['placements']:
        mesh=sources[p['item_id']].copy();mesh.apply_transform(p['transform']);bounds[p['unit_id']]=mesh.bounds
    layers={l['id']:l for l in result['envelope_design']['candidate']['layout']['layers']}
    panels=[*result.get('practical',{}).get('floor_liners',[]),*result.get('practical',{}).get('protective_separators',[])]
    records=[]
    for module in result['logistics']['modules']:
        layer=layers[module['id']];low=np.asarray(layer['position_mm'])+layer['wall_mm'];high=low+layer['inner_mm']
        sheets=[np.array([p['origin_mm'],np.asarray(p['origin_mm'])+p['dimensions_mm']]) for p in panels if p['carton_id']==module['id']]
        for uid in module['unit_ids']:
            obstacles=[bounds[other] for other in module['unit_ids'] if other!=uid]+sheets
            distances={f'{"+" if sign>0 else "-"}{"XYZ"[axis]}':free_box_translation(bounds[uid],obstacles,low,high,axis,sign)
                       for axis in range(3) for sign in (-1,1)}
            known=[v for v in distances.values() if v is not None]
            maximum=max(known,default=0.)
            records.append({'unit_id':uid,'carton_id':module['id'],'proven_free_translation_mm':distances,
                            'maximum_demonstrated_mm':maximum,'movement_demonstrated':maximum>movement_threshold_mm,
                            'initial_aabb_overlap':any(v is None for v in distances.values())})
    return {'scope':'Declared rigid-source geometry and closed carton walls; conservative empty-AABB sweep',
            'movement_threshold_mm':movement_threshold_mm,'threshold_basis':'Diagnostic reporting threshold, not a transport standard',
            'units_with_demonstrated_movement':sum(r['movement_demonstrated'] for r in records),
            'maximum_demonstrated_mm':max((r['maximum_demonstrated_mm'] for r in records),default=0.),
            'units_with_indeterminate_axes':sum(r['initial_aabb_overlap'] for r in records),'parts':records,
            'physical_retention_verified':False,
            'limitations':['Blocked bounding boxes do not prove restraint or stability.',
                           'No friction, rotation, deformation, strength or dynamic transit qualification.',
                           'Purchased packing envelopes retain their declared uncertainty.']}
