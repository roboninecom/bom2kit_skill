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


def test_column_candidates_preserve_identity_and_full_parent_support():
    from bom2kit.cpsat_floor_worker import column_options
    units=[{"item_id":"a","unit_id":f"a#{i}","dimensions":[10,10,6],
            "orientations":[((0,1,2),(10,10,6))]} for i in range(4)]
    candidates=column_options(units,12)
    assert any(len(c["members"])==2 for c in candidates)
    for column in candidates:
        members=column["members"]
        assert len({p["unit_id"] for p in members})==len(members)
        assert column["size"][2]<=12
        for lower,upper in zip(members,members[1:]):
            assert upper["position_mm"][2]==lower["position_mm"][2]+lower["dimensions_mm"][2]
            assert all(a<=b for a,b in zip(upper["dimensions_mm"][:2],lower["dimensions_mm"][:2]))


def test_optional_real_cpsat_columns():
    import os
    python=os.environ.get("BOM2KIT_CPSAT_PYTHON")
    if not python:pytest.skip("Set BOM2KIT_CPSAT_PYTHON for the optional isolated solver integration")
    units=[{"item_id":"a","unit_id":f"a#{i}","dimensions":[10,10,6],
            "orientations":[((0,1,2),(10,10,6))]} for i in range(4)]
    seed=[{"item_id":"a","unit_id":u["unit_id"],"dimensions_mm":[10,10,6],"rotation":[0,1,2],
           "position_mm":[i%2*10.2,i//2*10.2,0]} for i,u in enumerate(units)]
    result=pack_floor(units,seed,20.2,12,python=python,time_limit=5,allow_columns=True)
    assert result["status"]=="validated_envelopes",result
    assert result["usable_mm"][1]==pytest.approx(10)
    assert result["usable_mm"][2]==pytest.approx(12)


def test_experimental_columns_do_not_replace_floor_proposals(monkeypatch):
    from bom2kit.logistics_design import module_patterns
    calls=[]
    def propose(*args,**kwargs):
        calls.append(kwargs['allow_columns'])
        return {'status':'UNKNOWN'}
    monkeypatch.setattr('bom2kit.cpsat_floor_adapter.pack_floor',propose)
    units=[{'item_id':'a','unit_id':f'a#{i}','dimensions':[10,10,6],
            'orientations':[((0,1,2),(10,10,6))]} for i in range(4)]
    module_patterns(units,1.5,time_limit=.1,cp_sat_python='mock')
    floors=calls.copy()
    assert floors and not any(floors)
    calls.clear()
    module_patterns(units,1.5,time_limit=.1,cp_sat_python='mock',cp_sat_columns=True)
    assert calls==floors+[True]
