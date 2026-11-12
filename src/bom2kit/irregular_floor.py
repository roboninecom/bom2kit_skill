"""PackingSolver polygon proposals on complete stable-pose projections."""
from collections import Counter
import json
import math
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter


def polygon_data(polygon):
    from shapely.geometry.polygon import orient
    polygon=orient(polygon,sign=1.)
    result={'type':'polygon','vertices':[{'x':float(x),'y':float(y)} for x,y in list(polygon.exterior.coords)[:-1]]}
    if polygon.interiors:
        result['holes']=[{'type':'polygon','vertices':[{'x':float(x),'y':float(y)} for x,y in list(ring.coords)[:-1]]} for ring in polygon.interiors]
    return result


def propose(items,options,seed,padding,wall,*,executable,time_limit=3.,gap=.2,hand_border=8.,increment=1.,access_lane_mm=0.):
    import numpy as np
    import trimesh
    from shapely.geometry import shape,mapping,Polygon
    from shapely.affinity import translate,rotate,scale
    from .planar_validation import validate_floor_footprints
    started=perf_counter();geometries=[];bases=[];definitions=[]
    width=seed['external_mm'][0]-2*(wall+hand_border)
    if width<=0:return {'status':'invalid_width'}
    for item in items:
        option=options[item['id']][seed['stable_sku_orientations'][item['id']]]
        projection=shape(option['footprint'])
        full=projection.buffer(padding,join_style='round')
        extra=max(0.,access_lane_mm-gap)/2
        if extra:
            # An anisotropic dilation preserves the original isotropic padding
            # while reserving finger access primarily between rows. It only
            # enlarges the solver footprint; original CAD is never scaled.
            factor=(padding+extra)/padding
            full=scale(scale(projection,xfact=1,yfact=1/factor,origin=(0,0)).buffer(padding),
                       xfact=1,yfact=factor,origin=(0,0)).union(full)
        # Bounded outward approximation is only a solver proposal. Never shrink
        # the required complete projection or allow mirroring of a physical part.
        simplified=full.simplify(.25,preserve_topology=True).buffer(.26,join_style='mitre')
        if not simplified.covers(full):simplified=full.convex_hull
        if simplified.geom_type!='Polygon':simplified=simplified.convex_hull
        # Filling through holes is conservative and avoids fragile shape-library
        # interpretations; concave exterior outlines still save space.
        simplified=Polygon(simplified.exterior)
        minx,miny,_,_=simplified.bounds
        normalized=translate(simplified,xoff=-minx,yoff=-miny)
        base=np.asarray(option['transform']).copy();base[0,3]-=minx;base[1,3]-=miny
        geometries.append(normalized);bases.append(base)
        definitions.append({**polygon_data(normalized),'copies':item['quantity'],
                            'allowed_rotations':[{'start':a,'end':a} for a in (0,90,180,270)]})
    depth=sum(max(g.bounds[2],g.bounds[3])*i['quantity']+gap*i['quantity'] for g,i in zip(geometries,items))
    data={'objective':'open-dimension-y','bin_types':[{'type':'rectangle','width':width,'height':depth,'copies':1}],
          'item_types':definitions}
    with tempfile.TemporaryDirectory(prefix='bom2kit-irregular-') as directory:
        source=Path(directory)/'input.json';target=Path(directory)/'solution.json'
        source.write_text(json.dumps(data),encoding='utf8')
        try:
            run=subprocess.run([str(executable),'--input',str(source),'--certificate',str(target),'--time-limit',str(time_limit),
                                '--item-item-minimum-spacing',str(gap),'--verbosity-level','0'],capture_output=True,text=True,
                               timeout=time_limit+5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired:return {'status':'timeout','seconds':perf_counter()-started}
        if run.returncode or not target.exists():return {'status':'backend_error','message':run.stderr[-1200:],'seconds':perf_counter()-started}
        certificate=json.loads(target.read_bytes())
    bins=certificate.get('bins',[])
    if len(bins)!=1 or bins[0].get('copies')!=1:return {'status':'incomplete'}
    poses=bins[0].get('items',[]);counts=Counter(p['id'] for p in poses)
    if counts!=Counter({index:i['quantity'] for index,i in enumerate(items)}):return {'status':'incomplete'}
    original=[];envelopes=[];envelope_items=[];numbers=Counter()
    for pose in poses:
        index=pose['id'];item=items[index];angle=pose['angle']
        if pose.get('mirror') or angle not in (0,90,180,270):return {'status':'forbidden_orientation'}
        if not all(math.isfinite(pose[k]) for k in ('x','y','angle')):return {'status':'invalid_coordinate'}
        yaw=trimesh.transformations.rotation_matrix(math.radians(angle),[0,0,1])
        transform=yaw@bases[index]
        transform[:3,3]+=np.array([pose['x']+hand_border,pose['y']+hand_border,padding])
        polygon=translate(rotate(geometries[index],angle,origin=(0,0)),xoff=pose['x']+hand_border,yoff=pose['y']+hand_border)
        x,y,right,top=polygon.bounds;footprint=mapping(translate(polygon,xoff=-x,yoff=-y))
        height=options[item['id']][seed['stable_sku_orientations'][item['id']]]['dimensions_mm'][2]+2*padding
        size=[right-x,top-y,height];numbers[item['id']]+=1
        uid=item.get('packing_unit_ids',[f"{item['id']}#{k+1}" for k in range(item['quantity'])])[numbers[item['id']]-1]
        original.append({'item_id':item['id'],'unit_id':uid,'transform':transform.tolist(),
                         'envelope_position_mm':[x,y,0.],'envelope_dimensions_mm':size,'footprint':footprint})
        envelope_items.append({'id':uid,'quantity':1,'dimensions_mm':size,'footprint':footprint})
        envelopes.append({'item_id':uid,'unit_id':uid+'#1','rotation':[0,1,2],'position_mm':[x,y,0.],'dimensions_mm':size})
    used=[max(p['envelope_position_mm'][k]+p['envelope_dimensions_mm'][k] for p in original) for k in range(3)]
    used[:2]=[v+hand_border for v in used[:2]]
    check=validate_floor_footprints(envelope_items,envelopes,used,gap)
    if used[0]>width+2*hand_border+1e-5 or not check['valid']:
        return {'status':'rejected_certificate','validation':check}
    pattern={'external_mm':[math.ceil((v+2*wall)/increment-1e-9)*increment for v in used],
             'placements':original,'method':'packingsolver_stable_projection_floor',
             'preassemblies':0,'stable_sku_orientations':seed['stable_sku_orientations']}
    pattern['access_lane_mm']=access_lane_mm
    return {'status':'validated_planar_proposal','pattern':pattern,'seconds':perf_counter()-started,
            'validation':check,'source_mesh_replay_required':True}
