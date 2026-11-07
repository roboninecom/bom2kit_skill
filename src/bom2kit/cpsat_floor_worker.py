"""Optional isolated OR-Tools worker: choose vertical axes and floor positions."""
import json
import math
from pathlib import Path
import sys


def solve(data):
    import ortools
    from ortools.sat.python import cp_model
    grid=data["grid_mm"];gap=data["gap_mm"];width=math.floor((data["width_mm"]+gap)/grid+1e-9)
    height=data["height_mm"];units=data["units"];seed={p["unit_id"]:p for p in data["seed"]}
    max_depth=sum(math.ceil((max(u["dimensions"])+gap)/grid) for u in units)
    if seed:
        seed_depth=max(p["position_mm"][1]+p["dimensions_mm"][1] for p in seed.values())
        max_depth=min(max_depth,math.ceil((seed_depth*1.1+gap+2*len(units)*grid)/grid))
    model=cp_model.CpModel();depth=model.new_int_var(0,max_depth,"depth")
    xs=[];ys=[];records=[];area=0
    for i,unit in enumerate(units):
        x=model.new_int_var(0,width,f"x{i}");y=model.new_int_var(0,max_depth,f"y{i}")
        choices=[];seen=set()
        for rotation,size in unit["orientations"]:
            if size[2]>height+1e-8:continue
            dx,dy=[math.ceil((v+gap)/grid-1e-9) for v in size[:2]]
            if dx>width or (dx,dy,size[2]) in seen:continue
            seen.add((dx,dy,size[2]));present=model.new_bool_var(f"r{i}_{len(choices)}")
            model.add(x+dx<=width).only_enforce_if(present)
            model.add(y+dy<=depth).only_enforce_if(present)
            xs.append(model.new_optional_fixed_size_interval_var(x,dx,present,f"ix{i}_{len(choices)}"))
            ys.append(model.new_optional_fixed_size_interval_var(y,dy,present,f"iy{i}_{len(choices)}"))
            choices.append((present,rotation,size,dx*dy))
        if not choices:return {"status":"no_orientation","ortools_version":ortools.__version__}
        model.add_exactly_one([c[0] for c in choices]);area+=min(c[3] for c in choices)
        if unit["unit_id"] in seed:
            pose=seed[unit["unit_id"]];model.add_hint(x,round(pose["position_mm"][0]/grid));model.add_hint(y,round(pose["position_mm"][1]/grid))
            hinted=False
            for present,rotation,size,_ in choices:
                match=not hinted and list(size)==pose["dimensions_mm"]
                model.add_hint(present,int(match));hinted=hinted or match
        records.append((unit,x,y,choices))
    model.add(depth>=math.ceil(area/width));model.add_no_overlap_2d(xs,ys);model.minimize(depth)
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=data["time_limit"]
    solver.parameters.num_search_workers=1;solver.parameters.random_seed=0
    status=solver.solve(model)
    result={"status":solver.status_name(status),"ortools_version":ortools.__version__,"solver_seconds":solver.wall_time,
            "scope":"Rounded floor-envelope model only; original geometry and physical shipping remain outside this solver"}
    if status not in (cp_model.FEASIBLE,cp_model.OPTIMAL):return result
    poses=[]
    for unit,x,y,choices in records:
        _,rotation,size,_=next(c for c in choices if solver.value(c[0]))
        poses.append({"unit_id":unit["unit_id"],"item_id":unit["item_id"],"rotation":list(rotation),
                      "dimensions_mm":list(size),"position_mm":[solver.value(x)*grid,solver.value(y)*grid,0.]})
    result["placements"]=poses
    return result


if __name__=="__main__":
    source,target=map(Path,sys.argv[1:3]);target.write_text(json.dumps(solve(json.loads(source.read_text()))),encoding="utf8")
