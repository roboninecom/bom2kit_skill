"""Optional isolated floor solver; all returned poses require independent replay."""
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter

from .validation import validate


def pack_floor(units,seed,width,height,*,python,time_limit=2,gap=.2,grid_mm=.1,allow_columns=False):
    started=perf_counter();python=Path(python).resolve();worker=Path(__file__).with_name("cpsat_floor_worker.py")
    if not python.is_file() or not units or not all(math.isfinite(v) and v>0 for v in (width,height,time_limit,grid_mm)):
        raise ValueError("Existing Python interpreter and positive solver dimensions/budgets required")
    with tempfile.TemporaryDirectory(prefix="bom2kit-cpsat-") as directory:
        source=Path(directory)/"input.json";target=Path(directory)/"result.json"
        source.write_text(json.dumps({"units":units,"seed":seed,"width_mm":width,"height_mm":height,
                                      "gap_mm":gap,"grid_mm":grid_mm,"time_limit":time_limit,"allow_columns":allow_columns}),encoding="utf8")
        try:
            completed=subprocess.run([str(python),str(worker),str(source),str(target)],capture_output=True,text=True,
                                     timeout=time_limit+10,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        except subprocess.TimeoutExpired:return {"status":"timeout","elapsed_seconds":perf_counter()-started}
        if completed.returncode or not target.exists():return {"status":"backend_error","message":completed.stderr[-1200:],"elapsed_seconds":perf_counter()-started}
        result=json.loads(target.read_text())
    if result.get("status") not in ("FEASIBLE","OPTIMAL"):
        return {**result,"elapsed_seconds":perf_counter()-started}
    poses=result.get("placements",[])
    if Counter(p.get("unit_id") for p in poses)!=Counter(u["unit_id"] for u in units):return {"status":"incomplete"}
    try:
        identities={u["unit_id"]:u["item_id"] for u in units}
        if any(p["item_id"]!=identities[p["unit_id"]] for p in poses):raise ValueError("Changed source identity")
        used=[max(p["position_mm"][k]+p["dimensions_mm"][k] for p in poses) for k in range(3)]
        if any(not math.isfinite(v) or v<=0 for v in used):raise ValueError("Invalid solver dimensions")
        problem={"container":{"inner_mm":[width,used[1],height]},"gap_mm":gap,
                 "items":[{"id":u["unit_id"],"dimensions_mm":u["dimensions"],"allowed_rotations":[list(r) for r,_ in u["orientations"]]} for u in units]}
        check=validate(problem,{"placements":[{**p,"item_id":p["unit_id"],"unit_id":p["unit_id"]+"#1"} for p in poses]})
    except (ValueError,KeyError,TypeError,OverflowError) as error:
        return {"status":"invalid_backend_certificate","message":str(error)}
    return {"status":"validated_envelopes" if check["valid"] else "rejected","placements":poses,"usable_mm":used,
            "validation":check,"solver_status":result["status"],"ortools_version":result["ortools_version"],
            "column_candidates":result.get("column_candidates"),
            "worker_sha256":sha256(worker.read_bytes()).hexdigest(),"elapsed_seconds":perf_counter()-started}
