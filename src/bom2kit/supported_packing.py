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


def optimize_supported(units,width,depth,height,gap=.2,*,time_limit=1,max_iterations=96):
    """Bounded order/orientation evolution on real supporting envelope faces."""
    import random
    from time import perf_counter
    from .validation import validate
    start=perf_counter();rng=random.Random(0);best=None;elites=[];seen=set();attempts=0
    by_id={u["unit_id"]:u for u in units}
    if not units or len(by_id)!=len(units) or not math.isfinite(time_limit) or time_limit<=0 or type(max_iterations) is not int or max_iterations<1:
        raise ValueError("Unique supported units and positive search limits required")
    initial=[sorted(by_id,key=lambda uid:-math.prod(by_id[uid]["dimensions"])),
             sorted(by_id,key=lambda uid:-math.prod(sorted(by_id[uid]["dimensions"])[-2:]))]
    while attempts<max_iterations and perf_counter()-start<time_limit:
        if attempts<len(initial):order=initial[attempts].copy();vertical={}
        elif elites and rng.random()<.8:
            _,parent,parent_vertical=elites[rng.randrange(len(elites))]
            order=parent.copy();vertical=parent_vertical.copy()
            for _ in range(rng.randint(1,3)):
                a,b=rng.randrange(len(order)),rng.randrange(len(order));order[a],order[b]=order[b],order[a]
            if rng.random()<.6:
                uid=rng.choice(order)
                vertical[uid]=rng.choice([r[2] for r,_ in by_id[uid]["orientations"]])
        else:
            order=sorted(by_id,key=lambda uid:-math.prod(by_id[uid]["dimensions"])*math.exp(rng.uniform(-1.5,1.5)));vertical={}
        key=(tuple(order),tuple(sorted(vertical.items())))
        attempts+=1
        if key in seen:continue
        seen.add(key)
        pending=[{**by_id[uid],"orientations":[(r,s) for r,s in by_id[uid]["orientations"] if uid not in vertical or r[2]==vertical[uid]]} for uid in order]
        p=pack_supported(pending,width,depth,height,gap,"fit" if attempts%4==0 else "height",item_order="input")
        if not p:continue
        score=(p["usable_mm"][2],math.prod(p["usable_mm"]))
        elites.append((score,order,vertical));elites.sort(key=lambda e:e[0]);elites=elites[:8]
        if best is not None and score>=best[0]:continue
        problem={"container":{"inner_mm":[width,depth,p["usable_mm"][2]]},"gap_mm":gap,
                 "items":[{"id":u["unit_id"],"dimensions_mm":u["dimensions"],"allowed_rotations":[list(r) for r,_ in u["orientations"]]} for u in units]}
        poses=[{**q,"item_id":q["unit_id"],"unit_id":q["unit_id"]+"#1"} for q in p["placements"]]
        if validate(problem,{"placements":poses})["valid"]:best=(score,p)
    return {"packing":best[1] if best else None,"attempts":attempts,"seconds":perf_counter()-start}
