import csv
from pathlib import Path
from types import SimpleNamespace
import pytest

from bom2kit.packing_solver_adapter import pack_boxes


def run_certificate(tmp_path,monkeypatch,rows):
    executable=tmp_path/"test-backend.exe";executable.write_bytes(b"mock backend")
    def execute(command,**kwargs):
        path=Path(command[command.index("--certificate")+1])
        with path.open("w",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=["TYPE","ID","BIN","COPIES","X","Y","Z","ROTATION"])
            writer.writeheader();writer.writerows(rows)
        return SimpleNamespace(returncode=0,stderr="")
    monkeypatch.setattr("bom2kit.packing_solver_adapter.subprocess.run",execute)
    units=[{"item_id":"part","unit_id":f"part#{i}","dimensions":[10,10,10],
            "orientations":[((0,1,2),(10,10,10))]} for i in (1,2)]
    return pack_boxes(units,20.2,10,executable=executable,time_limit=.1,gap=.2)


def certificate(second_x=102,second_z=0):
    return [{"TYPE":"ITEM","ID":i,"BIN":0,"COPIES":1,"X":x,"Y":0,"Z":z,"ROTATION":"XYZ"}
            for i,x,z in ((0,0,0),(1,second_x,second_z))]


def test_backend_success_requires_independent_geometry(tmp_path,monkeypatch):
    assert run_certificate(tmp_path,monkeypatch,certificate())["status"]=="validated_envelopes"
    unsupported=run_certificate(tmp_path,monkeypatch,certificate(50,120))
    assert unsupported["status"]=="rejected"
    assert any("support" in error for error in unsupported["validation"]["errors"])


@pytest.mark.parametrize("field,value",[("ROTATION","XXY"),("X","nan"),("BIN",2),("COPIES",2),("ID",99)])
def test_malformed_backend_certificate_is_rejected(tmp_path,monkeypatch,field,value):
    rows=certificate();rows[1][field]=value
    assert run_certificate(tmp_path,monkeypatch,rows)["status"]=="invalid_backend_certificate"


def test_duplicate_or_missing_backend_units_are_incomplete(tmp_path,monkeypatch):
    rows=certificate();rows[1]["ID"]=0
    assert run_certificate(tmp_path,monkeypatch,rows)["status"]=="incomplete"
    assert run_certificate(tmp_path,monkeypatch,rows[:1])["status"]=="incomplete"


@pytest.mark.parametrize("fault",[None,"dimensions","overlap","missing","turn"])
def test_rectangle_certificate_preserves_source_and_floor_support(tmp_path,monkeypatch,fault):
    from bom2kit.packing_solver_adapter import pack_floor
    executable=tmp_path/"rectangle.exe";executable.write_bytes(b"mock rectangle")
    units=[{"item_id":"part","unit_id":f"part#{i}","dimensions":[10,20,5],
            "orientations":[((0,1,2),(10,20,5))]} for i in (1,2)]
    seed=[{"item_id":"part","unit_id":u["unit_id"],"position_mm":[i*10.2,0,0],
           "dimensions_mm":[10,20,5],"rotation":[0,1,2]} for i,u in enumerate(units)]
    def execute(command,**kwargs):
        import json
        instance=json.loads(Path(command[command.index("--input")+1]).read_text())
        assert all(i["oriented"] for i in instance["item_types"])
        rows=[{"TYPE":"ITEM","ID":i,"BIN":0,"COPIES":1,"X":i*102,"Y":0,"LX":102,"LY":202} for i in (0,1)]
        if fault=="dimensions":rows[1]["LX"]=100
        if fault=="overlap":rows[1]["X"]=50
        if fault=="missing":rows.pop()
        if fault=="turn":rows[1]["LX"],rows[1]["LY"]=202,102
        path=Path(command[command.index("--certificate")+1])
        with path.open("w",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        return SimpleNamespace(returncode=0,stderr="")
    monkeypatch.setattr("bom2kit.packing_solver_adapter.subprocess.run",execute)
    result=pack_floor(units,seed,20.2,executable=executable,time_limit=.1,gap=.2)
    expected={None:"validated_envelopes","dimensions":"invalid_backend_certificate","overlap":"rejected",
              "missing":"incomplete","turn":"invalid_backend_certificate"}
    assert result["status"]==expected[fault]
    if fault is None:assert all(p["position_mm"][2]==0 for p in result["placements"])
