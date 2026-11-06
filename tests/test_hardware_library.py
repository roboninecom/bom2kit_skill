import importlib.util
import json
from hashlib import sha256
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("prepare_hardware_library", Path(__file__).resolve().parents[1] / "scripts/prepare_hardware_library.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def test_packet_grid_contains_every_component_with_seal_allowance():
    dims, grid = adapter.packet_dimensions([4,4,10],37)
    nx,ny,nz = grid["grid"]
    assert nx*ny*nz >= 37
    assert grid["occupied_cells"] == 37
    assert all(d >= (c+.5)*n-.5+.4 for d,c,n in zip(dims,[4,4,10],[nx,ny,nz]))
    assert dims[2] >= (10+.5)*nz-.5+.4+5


def test_source_quantity_and_packet_contents_are_reconciled(tmp_path):
    pytest.importorskip("trimesh")
    source = tmp_path / "bom.md"
    source.write_text("test source")
    rows = tmp_path / "rows.json"
    rows.write_text(json.dumps({"source": str(source), "source_sha256": sha256(source.read_bytes()).hexdigest(),
                              "rows": [{"source_line": 1, "item": "bolt", "quantity": 37, "optional_alternative": False}]}))
    specification = {"source_rows_sha256": sha256(rows.read_bytes()).hexdigest(), "row_geometry": {
        "1": {"shape": {"kind": "box", "dimensions_mm": [4,4,10]}, "batch_in_packet": True, "evidence": "Conservative cell estimate"}}}
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(specification))
    library = adapter.prepare(rows,path,tmp_path / "output")
    assert library["part_count"] == 1
    assert library["items"][0]["contents"] == {"hardware-line-1": 37}
    assert json.loads((tmp_path / "output/coverage.json").read_text())["complete"]
    specification["row_geometry"] = {}
    path.write_text(json.dumps(specification))
    with pytest.raises(ValueError,match="Every selected BOM row"):
        adapter.prepare(rows,path,tmp_path / "other")
