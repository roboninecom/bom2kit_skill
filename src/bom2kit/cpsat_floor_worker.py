"""Optional isolated OR-Tools worker: choose vertical axes and floor positions."""
import json
import math
from pathlib import Path
import sys


def column_options(units,height):
    """Enumerate bounded chains; every child footprint lies on its parent."""
    candidates=[]
    for base in units:
        extras=[]
        for rotation,size in base["orientations"]:
            if size[2]>height+1e-8:continue
            first={"unit_id":base["unit_id"],"item_id":base["item_id"],"rotation":list(rotation),
                   "dimensions_mm":list(size),"position_mm":[0.,0.,0.]}
            candidates.append({"members":[first],"size":list(size)})
            beam=[([first],size,size[2],set([base["unit_id"]]))]
            for level in range(3):
                proposals=[]
                for members,top,z,used in beam:
                    for unit in units:
                        if unit["unit_id"] in used:continue
                        for r,s in unit["orientations"]:
                            if s[0]>top[0]+1e-8 or s[1]>top[1]+1e-8 or z+s[2]>height+1e-8:continue
                            pose={"unit_id":unit["unit_id"],"item_id":unit["item_id"],"rotation":list(r),
                                  "dimensions_mm":list(s),"position_mm":[0.,0.,z]}
                            volume=sum(math.prod(p["dimensions_mm"]) for p in members)+math.prod(s)
                            proposals.append((volume/(size[0]*size[1]),members+[pose],s,z+s[2],used|{unit["unit_id"]}))
                proposals.sort(key=lambda p:-p[0]);beam=[]
                for _,members,top,z,used in proposals[:4]:
                    extras.append({"members":members,"size":[size[0],size[1],z]})
                    beam.append((members,top,z,used))
                if not beam:break
        extras.sort(key=lambda c:-sum(math.prod(p["dimensions_mm"]) for p in c["members"])/(c["size"][0]*c["size"][1]))
        candidates.extend(extras[:12])
    unique={}
    for c in candidates:
        key=tuple((p["unit_id"],tuple(p["rotation"])) for p in c["members"])
        unique.setdefault(key,c)
    return list(unique.values())


def solve_columns(data):
    import ortools
    from ortools.sat.python import cp_model
    grid=data["grid_mm"];gap=data["gap_mm"];units=data["units"];height=data["height_mm"]
    width=math.floor((data["width_mm"]+gap)/grid+1e-9)
    seed={p["unit_id"]:p for p in data["seed"]}
    max_depth=math.ceil((max(p["position_mm"][1]+p["dimensions_mm"][1] for p in seed.values())*1.1+gap+2*len(units)*grid)/grid)
    model=cp_model.CpModel();depth=model.new_int_var(0,max_depth,"depth")
    xs=[];ys=[];coverage={u["unit_id"]:[] for u in units};records=[];hinted=set()
    for index,column in enumerate(column_options(units,height)):
        dx,dy=[math.ceil((v+gap)/grid-1e-9) for v in column["size"][:2]]
        if dx>width or dy>max_depth:continue
        present=model.new_bool_var(f"p{index}");x=model.new_int_var(0,width-dx,f"x{index}");y=model.new_int_var(0,max_depth-dy,f"y{index}")
        model.add(y+dy<=depth).only_enforce_if(present)
        xs.append(model.new_optional_fixed_size_interval_var(x,dx,present,f"ix{index}"));ys.append(model.new_optional_fixed_size_interval_var(y,dy,present,f"iy{index}"))
        for p in column["members"]:coverage[p["unit_id"]].append(present)
        selected=False
        if len(column["members"])==1:
            p=column["members"][0];uid=p["unit_id"]
            selected=uid not in hinted and uid in seed and p["dimensions_mm"]==seed[uid]["dimensions_mm"]
            if selected:
                hinted.add(uid);model.add_hint(x,round(seed[uid]["position_mm"][0]/grid));model.add_hint(y,round(seed[uid]["position_mm"][1]/grid))
        model.add_hint(present,int(selected));records.append((present,x,y,column))
    for values in coverage.values():model.add_exactly_one(values)
    model.add_no_overlap_2d(xs,ys);model.minimize(depth)
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=data["time_limit"]
    solver.parameters.num_search_workers=4;solver.parameters.random_seed=0
    status=solver.solve(model)
    result={"status":solver.status_name(status),"ortools_version":ortools.__version__,"solver_seconds":solver.wall_time,
            "column_candidates":len(records),"scope":"Supported envelope columns; original CAD and transport remain unqualified"}
    if status not in (cp_model.FEASIBLE,cp_model.OPTIMAL):return result
    poses=[]
    for present,x,y,column in records:
        if not solver.value(present):continue
        for pose in column["members"]:
            poses.append({**pose,"position_mm":[solver.value(x)*grid,solver.value(y)*grid,pose["position_mm"][2]]})
    result["placements"]=poses
    return result


def solve(data):
    if data.get("allow_columns"):return solve_columns(data)
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
