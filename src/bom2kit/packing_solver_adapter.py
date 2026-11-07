"""Optional PackingSolver CLI proposals with conservative integer envelopes.

Returned layouts are independently checked; CLI success is not acceptance.
The binary is supplied explicitly and never downloaded during a design run.
"""
from collections import Counter
import csv
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter

from .validation import validate


def _decode_rows(rows, units, grid_mm):
    placements=[]
    for row in rows:
        if row["TYPE"]!="ITEM":continue
        index=int(row["ID"])
        if index not in range(len(units)) or int(row["BIN"])!=0 or int(row["COPIES"])!=1:
            raise ValueError("Invalid certificate identity, bin or copies")
        unit=units[index]
        rotation=tuple("XYZ".index(c) for c in row["ROTATION"])
        if sorted(rotation)!=[0,1,2] or rotation not in [tuple(r) for r,_ in unit["orientations"]]:
            raise ValueError("Forbidden certificate orientation")
        position=[float(row[k])*grid_mm for k in ("X","Y","Z")]
        if any(not math.isfinite(v) or v<0 for v in position):raise ValueError("Invalid certificate coordinates")
        placements.append({"unit_id":unit["unit_id"],"item_id":unit["item_id"],"position_mm":position,
                           "dimensions_mm":[unit["dimensions"][k] for k in rotation],"rotation":list(rotation)})
    return placements


def pack_boxes(units, width, depth, *, executable, time_limit=2, grid_mm=.1, gap=0):
    """Minimize height for complete rectangular units; enforce support afterwards."""
    started = perf_counter()
    executable = Path(executable).resolve()
    if not all(math.isfinite(v) and v>0 for v in (grid_mm,time_limit,width,depth)) or not executable.is_file() or not units:
        raise ValueError("Existing PackingSolver binary and positive budgets required")
    dims = [[math.ceil((v+gap)/grid_mm-1e-9) for v in u["dimensions"]] for u in units]
    height = sum(max(d) for d in dims)
    integer_width = math.floor((width+gap)/grid_mm+1e-9)
    integer_depth = math.floor((depth+gap)/grid_mm+1e-9)
    instance = {"objective": "open-dimension-z",
                "bin_types": [{"x": integer_width, "y": integer_depth, "z": height}],
                "item_types": [dict(zip(("x", "y", "z"), d), copies=1,
                                    rotations=["".join("XYZ"[k] for k in r) for r, _ in u["orientations"]])
                               for u, d in zip(units, dims)]}
    with tempfile.TemporaryDirectory(prefix="bom2kit-packing-") as directory:
        source, target = Path(directory)/"input.json", Path(directory)/"solution.csv"
        source.write_text(json.dumps(instance), encoding="utf8")
        try:
            completed = subprocess.run([str(executable), "--input", str(source), "--certificate", str(target),
                                        "--time-limit", str(time_limit)], capture_output=True, text=True,
                                       timeout=time_limit+5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "elapsed_seconds": perf_counter()-started}
        if completed.returncode or not target.exists():
            return {"status": "backend_error", "message": completed.stderr[-1000:],
                    "elapsed_seconds": perf_counter()-started}
        rows = list(csv.DictReader(target.open(encoding="utf8")))
    try:
        placements=_decode_rows(rows,units,grid_mm)
    except (KeyError,ValueError,TypeError,OverflowError) as error:
        return {"status":"invalid_backend_certificate","message":str(error),"elapsed_seconds":perf_counter()-started}
    if Counter(p["unit_id"] for p in placements) != Counter(u["unit_id"] for u in units):
        return {"status": "incomplete", "elapsed_seconds": perf_counter()-started}
    # Round-up vertical coordinates can create artificial floating gaps. Compact
    # down onto exact supporting envelopes; independent support checking follows.
    placed = []
    for p in sorted(placements, key=lambda p: (p["position_mm"][2], p["unit_id"])):
        overlaps = [q for q in placed if all(min(p["position_mm"][k]+p["dimensions_mm"][k],
                    q["position_mm"][k]+q["dimensions_mm"][k])-max(p["position_mm"][k],q["position_mm"][k])>1e-7
                    for k in (0, 1))]
        p["position_mm"][2] = max((q["position_mm"][2]+q["dimensions_mm"][2] for q in overlaps), default=0)
        placed.append(p)
    actual_height = max(p["position_mm"][2]+p["dimensions_mm"][2] for p in placed)
    # Unique item identities make the independent validator apply the exact
    # per-unit source dimensions and orientation set, even for compound units.
    problem = {"container": {"inner_mm": [width, depth, actual_height]}, "gap_mm": gap,
               "items": [{"id": u["unit_id"], "dimensions_mm": list(u["dimensions"]),
                          "allowed_rotations": [list(r) for r, _ in u["orientations"]]} for u in units]}
    check_poses = [{**p, "item_id": p["unit_id"], "unit_id": p["unit_id"]+"#1"} for p in placed]
    certificate = validate(problem, {"placements": check_poses})
    return {"status": "validated_envelopes" if certificate["valid"] else "rejected",
            "placements": placed, "usable_mm": [width, depth, actual_height], "validation": certificate,
            "elapsed_seconds": perf_counter()-started,
            "backend_sha256": sha256(executable.read_bytes()).hexdigest()}
