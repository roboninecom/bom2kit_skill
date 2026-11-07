"""Constructive 3D envelope packing on explicitly supported rectangular surfaces."""
import math
from .strip_packing import subtract_rectangle


def pack_supported(units,width,depth,height,gap=.2,score="height",item_order="volume"):
    """Place several small units on a larger unit without imaginary shelves.

    Supports are envelope faces only; irregular CAD contact and material load
    bearing are outside this geometric construction and remain unqualified.
    """
    surfaces=[(0.,[(0.,0.,width,depth)])]
    placements=[];used=[0.,0.,0.]
    if score not in ("height","volume","fit"):raise ValueError("Unknown support score")
    if item_order=="input":pending=list(units)
    elif item_order=="area":
        pending=sorted(units,key=lambda u:(-math.prod(sorted(u["dimensions"])[-2:]),-math.prod(u["dimensions"]),u["unit_id"]))
    elif item_order.startswith("perturb-"):
        import random
        rng=random.Random(int(item_order.removeprefix("perturb-")))
        priorities={u["unit_id"]:math.prod(u["dimensions"])*math.exp(rng.uniform(-.6,.6)) for u in sorted(units,key=lambda u:u["unit_id"])}
        pending=sorted(units,key=lambda u:(-priorities[u["unit_id"]],u["unit_id"]))
    elif item_order=="volume":pending=sorted(units,key=lambda u:(-math.prod(u["dimensions"]),u["unit_id"]))
    else:raise ValueError("Unknown supported packing order")
    for unit in pending:
        options=[]
        for surface_index,(z,rectangles) in enumerate(surfaces):
            for x,y,w,d in rectangles:
                for rotation,size in unit["orientations"]:
                    if size[0]>w+1e-8 or size[1]>d+1e-8 or z+size[2]>height+1e-8:continue
                    position=[x,y,z]
                    blocked=False
                    for other in placements:
                        q=other["position_mm"];s=other["dimensions_mm"]
                        z_overlap=min(z+size[2],q[2]+s[2])-max(z,q[2])>1e-8
                        if z_overlap and not any(position[k]+size[k]+gap<=q[k]+1e-8 or q[k]+s[k]+gap<=position[k]+1e-8 for k in (0,1)):
                            blocked=True;break
                    if blocked:continue
                    extent=[max(used[k],position[k]+size[k]) for k in range(3)]
                    key=(extent[2],extent[0]*extent[1],w*d-size[0]*size[1]) if score=="height" else (
                        math.prod(v+min(width,depth)*.15 for v in extent),max(extent),extent[2])
                    if score=="fit":key=(extent[2],w*d-size[0]*size[1],min(w-size[0],d-size[1]))
                    options.append(((*key,z,y,x,tuple(size)),surface_index,rotation,size,position))
        if not options:return None
        _,index,rotation,size,position=min(options)
        z,rectangles=surfaces[index]
        # Exclude the lateral gap only on the used face. The new upper face is
        # exactly the placed envelope's footprint, so no overhang is supported.
        surfaces[index]=(z,subtract_rectangle(rectangles,position[0],position[1],size[0]+gap,size[1]+gap))
        surfaces.append((position[2]+size[2],[(position[0],position[1],size[0],size[1])]))
        placements.append({"item_id":unit["item_id"],"unit_id":unit["unit_id"],"position_mm":position,
                           "dimensions_mm":list(size),"rotation":list(rotation)})
        used=[max(used[k],position[k]+size[k]) for k in range(3)]
    placements.sort(key=lambda p:(p["position_mm"][2],p["unit_id"]))
    return {"placements":placements,"usable_mm":used}
