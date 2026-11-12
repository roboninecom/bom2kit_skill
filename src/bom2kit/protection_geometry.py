"""Nominal butt-jointed six-panel foam enclosure, without overlapping corners."""
from itertools import combinations
import math


def foam_panels(inner, thickness):
    x,y,z=inner;t=thickness
    if not all(math.isfinite(v) and v>0 for v in (*inner,t)) or min(inner)<=2*t:
        raise ValueError("Positive enclosure and foam dimensions required")
    definitions=[("bottom",[0,0,0],[x,y,t]),("top",[0,0,z-t],[x,y,t]),
                 ("front",[0,0,t],[x,t,z-2*t]),("back",[0,y-t,t],[x,t,z-2*t]),
                 ("left",[0,t,t],[t,y-2*t,z-2*t]),("right",[x-t,t,t],[t,y-2*t,z-2*t])]
    return [{"id":"foam-"+name,"kind":"foam_panel","quantity":1,"origin_mm":origin,"dimensions_mm":size,
             "material":"EPE; grade and cushion performance require qualification","thickness_mm":t}
            for name,origin,size in definitions]


def validate_foam_shell(inner, thickness, pieces):
    errors=[];t=thickness
    if len(inner)!=3 or not all(math.isfinite(v) and v>0 for v in (*inner,t)) or min(inner)<=2*t:
        return {"valid":False,"errors":["Invalid foam enclosure dimensions"]}
    if len(pieces)!=6 or len({p["id"] for p in pieces})!=6:
        errors.append("Six uniquely identified foam panels required")
    for p in pieces:
        o,d=p["origin_mm"],p["dimensions_mm"]
        if p.get("quantity")!=1 or p.get("thickness_mm")!=t or not any(abs(v-t)<1e-7 for v in d):
            errors.append("Each foam panel must have quantity one and the declared thickness")
        if any(not math.isfinite(v) for v in (*o,*d)) or any(s<=0 or a<0 or a+s>b+1e-7 for a,s,b in zip(o,d,inner)):
            errors.append("Foam outside outer cavity")
        if all(min(a+s,b-t)-max(a,t)>1e-7 for a,s,b in zip(o,d,inner)):
            errors.append("Foam intrudes into central cavity")
    for a,b in combinations(pieces,2):
        if all(min(a["origin_mm"][k]+a["dimensions_mm"][k],b["origin_mm"][k]+b["dimensions_mm"][k])-
               max(a["origin_mm"][k],b["origin_mm"][k])>1e-7 for k in range(3)):
            errors.append("Overlapping foam panel interiors")
    expected=math.prod(inner)-math.prod(v-2*t for v in inner)
    if not math.isclose(sum(math.prod(p["dimensions_mm"])*p["quantity"] for p in pieces),expected,rel_tol=1e-10):
        errors.append("Incomplete or excess foam shell volume")
    return {"valid":not errors,"errors":errors,"nominal_shell_volume_mm3":expected,
            "scope":"Nominal panel coverage; no cushion performance or manufacturing tolerance certification"}
