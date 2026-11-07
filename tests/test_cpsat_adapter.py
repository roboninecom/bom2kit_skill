from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from bom2kit.cpsat_floor_adapter import pack_floor


@pytest.mark.parametrize("fault",[None,"identity","rotation","overlap","missing"])
def test_floor_solver_cannot_bypass_independent_validation(tmp_path,monkeypatch,fault):
    executable=tmp_path/"python.exe";executable.write_bytes(b"mock")
    units=[{"item_id":"a","unit_id":f"a#{i}","dimensions":[10,20,5],
            "orientations":[((0,1,2),(10,20,5))]} for i in (1,2)]
    seed=[{"item_id":"a","unit_id":u["unit_id"],"position_mm":[i*10.2,0,0],
           "dimensions_mm":[10,20,5],"rotation":[0,1,2]} for i,u in enumerate(units)]
    def execute(command,**kwargs):
        poses=deepcopy(seed)
        if fault=="identity":poses[0]["item_id"]="other"
        if fault=="rotation":poses[0]["rotation"]=[1,0,2]
        if fault=="overlap":poses[1]["position_mm"][0]=5
        if fault=="missing":poses.pop()
        Path(command[-1]).write_text(json.dumps({"status":"OPTIMAL","placements":poses,"ortools_version":"mock"}))
        return SimpleNamespace(returncode=0,stderr="")
    monkeypatch.setattr("bom2kit.cpsat_floor_adapter.subprocess.run",execute)
    result=pack_floor(units,seed,20.2,5,python=executable)
    if fault is None:assert result["status"]=="validated_envelopes" and result["validation"]["valid"]
    else:assert result["status"] in ("invalid_backend_certificate","rejected","incomplete")
