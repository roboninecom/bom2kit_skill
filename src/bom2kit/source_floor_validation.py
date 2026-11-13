"""Original-mesh clearance inside floor patterns with overlapping bounding boxes."""
from collections import Counter
import math


def validate_source_floor(items,poses,inner,padding,gap,*,require_floor=True):
    import numpy as np
    import trimesh
    from .practical_geometry import load_mesh,contact_certificate
    errors=[];placed=[];by_id={i['id']:i for i in items}
    if not math.isfinite(padding) or padding<=0 or not math.isfinite(gap) or gap<0:
        return {'valid':False,'errors':['Positive source padding and nonnegative gap required']}
    expected=Counter({i['id']:i.get('quantity',1) for i in items})
    if Counter(p['item_id'] for p in poses)!=expected:errors.append('Source slot coverage differs')
    for pose in poses:
        try:
            item=by_id[pose['item_id']];position=np.asarray(pose['position_mm'])
            size=np.asarray(pose['dimensions_mm'])
            if pose['rotation']!=[0,1,2] or not np.allclose(size,item['dimensions_mm'],atol=1e-8,rtol=0):
                raise ValueError('Source slot dimensions/orientation changed')
            if not np.all(np.isfinite([position,size])) or np.any(size<=0) or np.any(position<-1e-7) or np.any(position+size>np.asarray(inner)+1e-7):
                raise ValueError('Source slot outside carton')
            if require_floor and abs(position[2])>1e-7:raise ValueError('Interlocking pattern must keep every source on the floor')
            transform=np.asarray(item['source_transform'],dtype=float).copy()
            if transform.shape!=(4,4) or not np.all(np.isfinite(transform)) or not np.allclose(transform[3],[0,0,0,1]) or not np.allclose(transform[:3,:3].T@transform[:3,:3],np.eye(3),atol=1e-7) or not np.isclose(np.linalg.det(transform[:3,:3]),1):
                raise ValueError('Nonrigid source transform')
            transform[:3,3]+=position
            mesh=load_mesh({'mesh':item['source_mesh']});mesh.apply_transform(transform)
            if np.any(mesh.bounds[0]-padding<position-1e-6) or np.any(mesh.bounds[1]+padding>position+size+1e-6):
                raise ValueError('Source padding omitted')
            if require_floor and not contact_certificate(mesh,plane_z=padding)['valid']:raise ValueError('Actual source lacks stable floor contact')
            manager=trimesh.collision.CollisionManager();manager.add_object('current',mesh)
            for uid,other,other_manager in placed:
                separation=np.maximum(0,np.maximum(mesh.bounds[0]-other.bounds[1],other.bounds[0]-mesh.bounds[1]))
                if np.linalg.norm(separation)>=2*padding+gap-1e-6:continue
                if manager.in_collision_other(other_manager) or manager.min_distance_other(other_manager)<2*padding+gap-1e-6:
                    errors.append(f'Original source clearance violation: {pose["unit_id"]}, {uid}')
            placed.append((pose['unit_id'],mesh,manager))
        except (KeyError,TypeError,ValueError) as error:errors.append(str(error))
    return {'valid':not errors,'errors':errors,'scope':('Original source floor support and radial protection clearance; hand access separate'
            if require_floor else 'Original source radial protection clearance; explicit actual-surface support replay required')}
