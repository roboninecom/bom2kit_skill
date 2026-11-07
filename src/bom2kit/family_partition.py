"""Geometry-driven compatible carton membership without supplied layouts."""
import math
from time import perf_counter

from .strip_packing import pack_strip


def packing_partition(units, count, *, wall=1.5, gap=.2, increment=1, time_limit=4):
    """Compare partial floor packings, then assign every remaining unit exactly once.

    Returned memberships are proposals. The caller regenerates and validates
    complete module layouts and the full original CAD hierarchy afterward.
    """
    if count < 2 or count > len(units):
        raise ValueError("Partition count must be between two and the unit count")
    start=perf_counter();volume=sum(math.prod(u["dimensions"]) for u in units)
    scale=(volume/count)**(1/3)
    minimum=max(min(u["dimensions"]) for u in units)
    heights=sorted({minimum,*(max(minimum,scale*f) for f in (.5,.7,.9,1.15,1.5)),
                    *(v for u in units for v in u["dimensions"] if minimum<=v<=scale*1.5)})
    if len(heights)>12:
        heights=[heights[round(i*(len(heights)-1)/11)] for i in range(12)]
    heights.sort(key=lambda h:abs(math.log(h/scale)))
    by_id={u["unit_id"]:u for u in units};best=None;attempts=0
    for h in heights:
        area=sum(min(s[0]*s[1] for _,s in u["orientations"] if s[2]<=h+1e-8) for u in units)/count
        for aspect in (1,.75,1.35,.55,1.8):
            for density in (.95,1.1,1.3):
                if perf_counter()-start>time_limit:break
                width=math.ceil(math.sqrt(area)*aspect*density/increment)*increment
                depth=math.ceil(math.sqrt(area)/aspect*density/increment)*increment
                for mode,order in (("short_side","compact"),("height_fill","volume")):
                    pending=list(units);groups=[];sizes=[]
                    for index in range(count):
                        last=index==count-1
                        p=pack_strip(pending,width,h,gap,depth=None if last else depth,
                                     allow_partial=not last,placement_score=mode,item_order=order)
                        if not p or not p["placements"]:break
                        ids={pose["unit_id"] for pose in p["placements"]}
                        # Leave at least one real part for each future carton.
                        if not last and len(pending)-len(ids)<count-index-1:break
                        groups.append([by_id[uid] for uid in sorted(ids)])
                        sizes.append([math.ceil((v+2*wall)/increment)*increment for v in p["usable_mm"]])
                        pending=[u for u in pending if u["unit_id"] not in ids]
                    attempts+=1
                    if pending or len(groups)!=count:continue
                    # Rank compatible subdivisions by material envelope and
                    # common-footprint stacking; no engineer dimensions enter.
                    raw=sum(math.prod(s) for s in sizes)
                    stack=max(s[0] for s in sizes)*max(s[1] for s in sizes)*sum(s[2] for s in sizes)
                    key=(raw+.2*(stack-raw),max(max(s)/min(s) for s in sizes))
                    if best is None or key<best[0]:best=(key,groups,sizes)
            if perf_counter()-start>time_limit:break
        if perf_counter()-start>time_limit:break
    return {"groups":best[1] if best else None,"proposal_cartons_mm":best[2] if best else None,
            "attempts":attempts,"seconds":perf_counter()-start,"reference_used":False}
