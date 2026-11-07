"""Whole-family CAD proposals using shape-aware vertical insertion heightfields.

Raster proposals are never certificates: original triangles and insertion paths
must pass independently before a compound can enter carton design.
"""
from collections import Counter
from hashlib import sha256
from itertools import permutations, product
import json
import math
from pathlib import Path
from time import perf_counter


def insertion_heights(top, bottom, mask):
    """At each valid XY origin, return max(top[x+i,y+j] - bottom[i,j])."""
    import numpy as np
    from scipy.ndimage import grey_erosion
    nx,ny=top.shape[0]-bottom.shape[0]+1,top.shape[1]-bottom.shape[1]+1
    if nx<=0 or ny<=0:return None
    field=-grey_erosion(-top,footprint=mask,structure=-bottom,mode="constant",cval=-1e9)
    ox,oy=bottom.shape[0]//2,bottom.shape[1]//2
    return np.maximum(0,field[ox:ox+nx,oy:oy+ny])


def prepare_shapes(items, pitch):
    import numpy as np
    import trimesh
    from .mesh_frames import packing_bounds
    shapes={}
    for item in items:
        raw=Path(item["mesh"]["path"]).read_bytes()
        if sha256(raw).hexdigest()!=item["mesh"]["sha256"]:raise ValueError("Source mesh hash mismatch")
        data=json.loads(raw)
        if data.get("units")!="mm":raise ValueError("Source millimetres required")
        mesh=trimesh.Trimesh(data["vertices_mm"],data["triangles"],process=False)
        if not mesh.is_volume:raise ValueError("Positive watertight original source required")
        frame,_=packing_bounds(mesh);mesh.apply_transform(frame)
        shift=-mesh.bounds[0];frame[:3,3]+=shift;mesh.apply_translation(shift)
        vox=mesh.voxelized(pitch).fill();grid=vox.matrix
        origin=vox.transform[:3,3]
        choices=[]
        for perm in permutations(range(3)):
            for signs in product((1,-1),repeat=3):
                rotation=np.zeros((3,3))
                for axis,col in enumerate(perm):rotation[axis,col]=signs[axis]
                if np.linalg.det(rotation)<0:continue
                occupied=np.transpose(grid,perm);correction=-rotation@origin
                for axis,sign in enumerate(signs):
                    if sign<0:
                        occupied=np.flip(occupied,axis=axis)
                        correction[axis]+=(occupied.shape[axis]-1)*pitch
                mask=occupied.any(axis=2)
                bottom=occupied.argmax(axis=2).astype(float)
                upper=(occupied.shape[2]-occupied[:,:,::-1].argmax(axis=2)).astype(float)
                choices.append({"rotation":rotation,"correction":correction,"bottom":bottom,
                                "upper":upper,"mask":mask,"size":occupied.shape})
        shapes[item["id"]]={"mesh":mesh,"frame":frame,"choices":choices,
                            "box_volume":float(np.prod(mesh.extents)),"material_volume":float(mesh.volume)}
    return shapes


def pack_heightfield(items, shapes, width, depth, *, pitch=4, clearance=2, order="volume", time_limit=30):
    import numpy as np
    import trimesh
    started=perf_counter();top=np.zeros((int(width),int(depth)),dtype=float)
    units=[(item["id"],f"{item['id']}#{copy+1}") for item in items for copy in range(item["quantity"])]
    if order=="volume":units.sort(key=lambda p:(-shapes[p[0]]["box_volume"],p[1]))
    elif order=="void":units.sort(key=lambda p:(-(shapes[p[0]]["box_volume"]-shapes[p[0]]["material_volume"]),p[1]))
    elif order=="area":units.sort(key=lambda p:(-max(math.prod(c["size"][:2]) for c in shapes[p[0]]["choices"]),p[1]))
    else:raise ValueError("Unknown shape ordering")
    manager=trimesh.collision.CollisionManager();poses=[];extent=np.zeros(3);parts=[]
    for iid,uid in units:
        if perf_counter()-started>time_limit:return None
        shape=shapes[iid];options=[]
        for index,choice in enumerate(shape["choices"]):
            heights=insertion_heights(top,choice["bottom"],choice["mask"])
            if heights is None:continue
            sx,sy,sz=choice["size"];xs,ys=np.indices(heights.shape)
            ex=np.maximum(extent[0],xs+sx);ey=np.maximum(extent[1],ys+sy);ez=np.maximum(extent[2],heights+sz)
            scores=(ex+4)*(ey+4)*(ez+4)+(ys*width+xs)*1e-6
            # Several candidates permit exact clearance corrections without
            # assuming the raster's best point must be geometrically feasible.
            indices=np.argpartition(scores.ravel(),min(2,scores.size-1))[:3]
            for flat in indices:
                x,y=np.unravel_index(flat,scores.shape)
                options.append((float(scores[x,y]),float(ez[x,y]),index,int(x),int(y),float(heights[x,y])))
        accepted=None
        for _,_,index,x,y,z in sorted(options):
            choice=shape["choices"][index]
            for rise in range(9):
                actual_z=z*pitch+rise*pitch/4
                transform=np.eye(4);transform[:3,:3]=choice["rotation"]
                transform[:3,3]=choice["correction"]+np.array([x*pitch,y*pitch,actual_z])
                mesh=shape["mesh"].copy();mesh.apply_transform(transform)
                if poses and (manager.in_collision_single(mesh) or manager.min_distance_single(mesh)+1e-7<clearance):continue
                accepted=(choice,x,y,actual_z/pitch,transform,mesh);break
            if accepted:break
            if perf_counter()-started>time_limit:return None
        if accepted is None:return None
        choice,x,y,z,transform,mesh=accepted;sx,sy,sz=choice["size"]
        region=top[x:x+sx,y:y+sy];mask=choice["mask"]
        region[mask]=np.maximum(region[mask],math.ceil(z)+choice["upper"][mask])
        extent=np.maximum(extent,[x+sx,y+sy,z+sz]);manager.add_object(uid,mesh);parts.append(mesh)
        poses.append({"item_id":iid,"unit_id":uid,"transform":(transform@shape["frame"]).tolist()})
    low=np.min([m.bounds[0] for m in parts],axis=0);high=np.max([m.bounds[1] for m in parts],axis=0)
    offset=np.eye(4);offset[:3,3]=1-low
    for pose in poses:pose["transform"]=(offset@np.asarray(pose["transform"])).tolist()
    return {"layout":{"units":"mm","placements":poses},"bounds_mm":(high-low).tolist(),
            "container_mm":(high-low+2).tolist(),"seconds":perf_counter()-started}


def discover_heightfield_groups(library, policy, output, time_limit=180, pitch=4):
    import numpy as np
    from .mesh_validation import validate_mesh_layout
    from .mesh_motion import check_vertical_sequence
    from .report import fingerprint
    started=perf_counter();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    alternatives=[];attempts=[]
    families=sorted(set(policy["families"].values()))
    shapes=prepare_shapes(library["items"],pitch)
    families.sort(key=lambda f:-sum((shapes[i["id"]]["box_volume"]-shapes[i["id"]]["material_volume"])*i["quantity"]
                                    for i in library["items"] if policy["families"][i["id"]]==f))
    for family in families:
        items=[i for i in library["items"] if policy["families"][i["id"]]==family]
        count=sum(i["quantity"] for i in items)
        volume=sum(shapes[i["id"]]["box_volume"]*i["quantity"] for i in items)
        material=sum(shapes[i["id"]]["material_volume"]*i["quantity"] for i in items)
        if count<3 or material/volume>.85:continue
        scale=(volume**(1/3))/pitch
        minimum=max(min(c["size"][2] for c in shapes[i["id"]]["choices"]) for i in items)
        footprints=[]
        # Thin or long source parts need broad shallow footprints; volume's
        # cube root alone can exclude all useful orientations of such parts.
        for h in sorted({minimum,max(minimum,scale*.65),max(minimum,scale),max(minimum,scale*1.5)}):
            area=sum(min(c["size"][0]*c["size"][1] for c in shapes[i["id"]]["choices"] if c["size"][2]<=h+1e-8)*i["quantity"] for i in items)
            for density,aspect,order in ((.85,1,"volume"),(.75,1.4,"void"),(.95,.75,"volume")):
                footprints.append((math.ceil(math.sqrt(area)*density*aspect),math.ceil(math.sqrt(area)*density/aspect),order))
        footprints.extend((math.ceil(scale*f*a),math.ceil(scale*f/a),order) for f,a,order in
                          ((.9,1,"volume"),(.8,1.4,"volume"),(1.1,.8,"void"),(.75,1,"area"),(1.1,1.4,"volume"),(.9,.65,"void")))
        for width,depth,order in dict.fromkeys(footprints):
            left=time_limit-(perf_counter()-started)
            if left<5:break
            proposal=pack_heightfield(items,shapes,width,depth,pitch=pitch,
                                     clearance=max(policy["clearance_mm"],2*policy["item_padding_mm"]),
                                     order=order,time_limit=min(40,left))
            attempt={"family":family,"footprint_cells":[width,depth],"order":order,"status":"proposal_failed"}
            attempts.append(attempt)
            if proposal is None:continue
            attempt["volume_mm3"]=math.prod(proposal["bounds_mm"])
            if attempt["volume_mm3"]>=volume:attempt["status"]="no_envelope_saving";continue
            problem={"units":"mm","items":[{"id":i["id"],"quantity":i["quantity"],"mesh":i["mesh"]} for i in items],
                     "container":{"inner_mm":proposal["container_mm"]},
                     "clearance_mm":max(policy["clearance_mm"],2*policy["item_padding_mm"])}
            validation=validate_mesh_layout(problem,proposal["layout"])
            if not validation["valid"]:attempt["status"]="original_geometry_rejected";attempt["errors"]=validation["errors"][:4];continue
            motion=check_vertical_sequence(problem,proposal["layout"],time_limit=30)
            if not motion["valid"]:attempt["status"]="insertion_unverified";continue
            assembly={"input":problem,"layout":proposal["layout"],"certificate":motion,
                      "source_to_workbench":np.eye(4).tolist(),"source_removal_direction":[0,0,1]}
            alternative={"members":[i["id"] for i in items for _ in range(i["quantity"])],
                         "input":problem,"layout":proposal["layout"],"assembly":assembly,
                         "envelope_mm":proposal["bounds_mm"],"separate_box_volume_mm3":volume,
                         "group_box_volume_mm3":attempt["volume_mm3"]}
            alternatives.append((family,alternative));attempt["status"]="validated_family_compound"
            (output/"progress.json").write_text(json.dumps({"attempts":attempts,"seconds":perf_counter()-started},indent=2),encoding="utf8")
    result={"alternatives":alternatives,"attempts":attempts,"seconds":perf_counter()-started,
            "source_fingerprint":fingerprint(library),"policy_fingerprint":fingerprint(policy),
            "pitch_mm":pitch,"reference_used":False,"physical_retention_verified":False}
    (output/"heightfield-groups.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    return result
