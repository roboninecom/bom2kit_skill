"""Co-design compatible cartons against common footprints derived from contents."""
from itertools import product
import math
from time import perf_counter

from .strip_packing import pack_strip
from .supported_packing import pack_supported
from .column_packing import make_mixed_columns,expand_columns
from .validation import validate


def search_shared_footprints(module_sets, carton, *, time_limit=60, keep=6):
    """Search exact stacks of closed cartons; never insert shelves or spacers.

    Generated module patterns may subsequently participate in other slicing
    layouts. Footprints come only from source envelope volumes and dimensions.
    """
    start=perf_counter();wall=carton["inner_wall_mm"];gap=carton["gap_mm"]
    increment=carton["dimension_increment_mm"];foam=carton["protection_mm"];outer_wall=carton["wall_mm"]
    volume=sum(math.prod(u["dimensions"]) for _,units in module_sets for u in units)
    scale=volume**(1/3)
    ceil=lambda v:math.ceil(v/increment-1e-9)*increment
    footprints={(ceil(scale*f*a),ceil(scale*f/a)) for f,a in product((.65,.8,.95,1.1,1.3,1.5),(.7,.85,1,1.2,1.45))}
    def lower_score(size):
        w,d=size
        height=sum(sum(math.prod(u["dimensions"]) for u in units)/max(1,(w-2*wall)*(d-2*wall))+2*wall for _,units in module_sets)
        return (w+2*(foam+outer_wall))*(d+2*(foam+outer_wall))*(height+2*(foam+outer_wall))
    footprints=sorted(footprints,key=lower_score)
    candidates=[];attempts=0
    for width,depth in footprints:
        if perf_counter()-start>=time_limit:break
        selected=[]
        for family,units in module_sets:
            w,d=width-2*wall,depth-2*wall;best=None
            maximum=scale*3
            def consider(p,method):
                nonlocal best
                if not p:return
                h=max(q["position_mm"][2]+q["dimensions_mm"][2] for q in p["placements"])
                if best and h>=best[0]-1e-8:return
                problem={"container":{"inner_mm":[w,d,h]},"gap_mm":gap,
                         "items":[{"id":u["unit_id"],"dimensions_mm":u["dimensions"],"allowed_rotations":[list(r) for r,_ in u["orientations"]]} for u in units]}
                poses=[{**q,"item_id":q["unit_id"],"unit_id":q["unit_id"]+"#1"} for q in p["placements"]]
                if validate(problem,{"placements":poses})["valid"]:
                    best=(h,{"external_mm":[width,depth,ceil(h+2*wall)],"placements":p["placements"],"method":method})
            for mode,order in (("height","volume"),("height","area"),("fit","area"),("height","perturb-2")):
                if perf_counter()-start>=time_limit:break
                consider(pack_supported(units,w,d,maximum,gap,mode,order),"shared_footprint_supported")
            heights=sorted({s[2] for u in units for _,s in u["orientations"]})
            if len(heights)>16:heights=[heights[round(i*(len(heights)-1)/15)] for i in range(16)]
            for height in heights:
                if best and height>=best[0]:break
                if perf_counter()-start>=time_limit:break
                for mode,order in (("short_side","compact"),("height_fill","volume")):
                    consider(pack_strip(units,w,height,gap,depth=d,placement_score=mode,item_order=order),"shared_footprint_floor")
            for height in sorted({max(min(u["dimensions"]) for u in units),*(scale*f for f in (.25,.4,.6,.8))}):
                if perf_counter()-start>=time_limit:break
                if best and height>=best[0]:continue
                columns,expansion=make_mixed_columns(units,height)
                if not columns:continue
                p=pack_strip(columns,w,height,gap,depth=d,placement_score="short_side")
                if p:consider(expand_columns(p,expansion),"shared_footprint_columns")
            if best is None:break
            selected.append(best[1])
        attempts+=1
        if len(selected)!=len(module_sets):continue
        block=[width,depth,sum(p["external_mm"][2] for p in selected)]
        external=[ceil(v+2*(foam+outer_wall)+(carton["reserved_top_mm"] if k==2 else 0)) for k,v in enumerate(block)]
        candidates.append({"patterns":selected,"external_mm":external,"volume_mm3":math.prod(external)})
    candidates.sort(key=lambda c:c["volume_mm3"])
    return {"candidates":candidates[:keep],"attempts":attempts,"seconds":perf_counter()-start,"reference_used":False}
