import json
import subprocess
import sys

from bom2kit.cli import main


def test_cli_round_trip_and_tamper(tmp_path):
    problem = {
        "units": "mm",
        "container": {"inner_mm": [100, 80, 30]},
        "items": [{"id": "A", "quantity": 2, "dimensions_mm": [40, 40, 20]}],
    }
    source = tmp_path / "input.json"
    source.write_text(json.dumps(problem), encoding="utf-8")
    output = tmp_path / "output"
    assert main(["solve", str(source), "--output", str(output), "--time-limit", "1"]) == 0
    layout_path = output / "layout.json"
    assert main(["validate", str(source), str(layout_path)]) == 0
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    layout["placements"].pop()
    layout_path.write_text(json.dumps(layout), encoding="utf-8")
    assert main(["validate", str(source), str(layout_path)]) == 1


def test_input_failure_has_nonzero_exit(tmp_path, capsys):
    source = tmp_path / "bad.json"
    source.write_text("[]", encoding="utf-8")
    assert main(["solve", str(source), "--output", str(tmp_path / "out")]) == 2
    assert "Expected a JSON object" in capsys.readouterr().err


def test_cli_import_does_not_load_cad():
    check = subprocess.run(
        [sys.executable, "-c", "import sys; import bom2kit.cli; assert 'cadquery' not in sys.modules"],
        capture_output=True, text=True,
    )
    assert check.returncode == 0, check.stderr


def test_reconcile_cli_rejects_missing_contents(tmp_path):
    bom = tmp_path / 'bom.json'
    job = tmp_path / 'job.json'
    result = tmp_path / 'coverage.json'
    bom.write_text(json.dumps({'components': [{'id': 'screw', 'quantity': 20}]}))
    job.write_text(json.dumps({'items': [{'id': 'packet', 'quantity': 2, 'contents': {'screw': 10}}]}))
    args = ['reconcile', str(bom), str(job), '--output', str(result)]
    assert main(args) == 0
    job.write_text(json.dumps({'items': [{'id': 'packet', 'quantity': 1, 'contents': {'screw': 10}}]}))
    assert main(args) == 1
    assert json.loads(result.read_text())['missing'] == {'screw': 10}


def test_optimize_saves_selected_actual_input_and_original_request(tmp_path):
    problem = {
        "container": {"inner_mm": [30, 10, 10], "wall_mm": 2},
        "reference": {"external_mm": [34, 14, 14]},
        "container_candidates": [{"id": "smaller", "inner_mm": [20, 10, 10]}],
        "items": [{"id": "A", "quantity": 2, "dimensions_mm": [10, 10, 10]}],
    }
    source = tmp_path / "input.json"
    source.write_text(json.dumps(problem), encoding="utf-8")
    output = tmp_path / "optimized"
    assert main(["optimize", str(source), "--output", str(output)]) == 0
    actual = json.loads((output / "input.json").read_text())
    request = json.loads((output / "request.json").read_text())
    assert actual["container"]["inner_mm"] == [20, 10, 10]
    assert request == problem
    assert main(["validate", str(output / "input.json"), str(output / "layout.json")]) == 0
    assert main(["report", str(output / "input.json"), str(output / "layout.json"),
                 "--output", str(output / "report")]) == 0
    comparison = json.loads((output / "report" / "comparison.json").read_text())
    assert comparison["external_volume_l"] == 24 * 14 * 14 / 1e6
    assert comparison["no_worse_nominal_carton_volume"]
    assert not comparison["full_kit_acceptance"]


def test_optimize_failure_is_nonzero_and_does_not_claim_success(tmp_path):
    problem = {"container": {"inner_mm": [10, 10, 10]},
               "items": [{"id": "A", "dimensions_mm": [20, 20, 20]}]}
    source = tmp_path / "input.json"
    source.write_text(json.dumps(problem), encoding="utf-8")
    output = tmp_path / "output"
    assert main(["optimize", str(source), "--output", str(output)]) == 1
    layout = json.loads((output / "layout.json").read_text())
    assert layout["status"] == "no_verified_candidate"


def test_invalid_report_has_nonzero_exit_and_visible_failure(tmp_path):
    problem = {"container": {"inner_mm": [10, 10, 10]},
               "items": [{"id": "A", "dimensions_mm": [10, 10, 10]}]}
    source = tmp_path / "input.json"
    source.write_text(json.dumps(problem), encoding="utf-8")
    layout = tmp_path / "layout.json"
    layout.write_text(json.dumps({"placements": [], "validation": {"valid": True}}))
    output = tmp_path / "report"
    assert main(["report", str(source), str(layout), "--output", str(output)]) == 1
    assert "INVALID LAYOUT" in (output / "instruction.html").read_text()


def test_mesh_validate_cli_static_geometry_and_hash_tamper(tmp_path):
    from hashlib import sha256
    import pytest

    trimesh = pytest.importorskip("trimesh")
    pytest.importorskip("fcl")
    mesh = trimesh.creation.box([2, 2, 2])
    mesh_path = tmp_path / "mesh.json"
    mesh_path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(),
                                     "triangles": mesh.faces.tolist()}))
    problem = {"units": "mm", "container": {"inner_mm": [10, 10, 10]}, "items": [
        {"id": "A", "mesh": {"path": str(mesh_path), "sha256": sha256(mesh_path.read_bytes()).hexdigest()}}]}
    layout = {"units": "mm", "placements": [{"item_id": "A", "unit_id": "A#1",
        "transform": [[1, 0, 0, 5], [0, 1, 0, 5], [0, 0, 1, 5], [0, 0, 0, 1]]}]}
    source, certificate = tmp_path / "input.json", tmp_path / "layout.json"
    source.write_text(json.dumps(problem))
    certificate.write_text(json.dumps(layout))
    output = tmp_path / "validation.json"
    args = ["mesh-validate", str(source), str(certificate), "--output", str(output)]
    assert main(args) == 0
    assert not json.loads(output.read_text())["production_validated"]
    mesh_path.write_text(mesh_path.read_text() + " ")
    assert main(args) == 1
    assert any("SHA256 mismatch" in error for error in json.loads(output.read_text())["errors"])
