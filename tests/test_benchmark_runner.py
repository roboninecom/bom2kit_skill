"""Benchmark reproduction is independent of private evidence availability."""

import json
from pathlib import Path
from unittest.mock import patch

from scripts.run_benchmarks import build_problem, run_benchmarks, source_record
from bom2kit.solver import solve


def evidence(variant):
    sizes = [[246, 104, 75], [180, 164, 75], [246, 75, 52], [164, 75, 66],
             [246, 124, 64], [196, 168, 64], [196, 78, 64]]
    if variant == 102:
        sizes[0], sizes[1], sizes[3] = [246, 116, 75], [204, 164, 75], [164, 75, 42]
    return {"model": f"SO-ARM{variant}", "reference_outer_mm": [364 if variant == 101 else 376, 290, 184],
            "boxes": [{"id": f"BOX{i + 1}", "quantity": 1, "dimensions_mm": size,
                       "contents": {"declared component": 1}} for i, size in enumerate(sizes)]}


def test_runner_search_never_receives_reference_coordinates(tmp_path):
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    inputs.mkdir()
    for variant in (101, 102):
        (inputs / f"so-arm-{variant}-evidence.json").write_text(json.dumps(evidence(variant)))
    calls = []

    def independent_search(problem, **kwargs):
        assert "reference_layout" not in problem
        calls.append(problem)
        return solve(problem, **kwargs)

    with patch("scripts.run_benchmarks.solve", side_effect=independent_search):
        result = run_benchmarks(inputs, outputs, root=tmp_path)
    assert len(calls) == 2
    assert result["all_nominal_benchmarks_pass"]
    assert not result["full_kit_acceptance"]
    for variant in (101, 102):
        output = outputs / f"so-arm-{variant}"
        assert (output / "instruction.html").is_file()
        problem = json.loads((output / "input.json").read_text())
        assert problem["container"]["reserved_top_mm"] == 1
        assert problem["container"]["wall_mm"] == 7
        assert problem["container"]["protection_mm"] == 15
        assert problem["items"][0]["contents"] == {"declared component": 1}
        assert json.loads((output / "reference-validation.json").read_text())["valid"]


def test_source_manifest_hashes_actual_bytes_and_missing_is_explicit(tmp_path):
    path = tmp_path / "source.txt"
    path.write_bytes(b"version one")
    first = source_record(path)
    assert first == source_record(path)
    path.write_bytes(b"version two")
    assert first["sha256"] != source_record(path)["sha256"]
    missing = source_record(tmp_path / "absent.txt")
    assert not missing["available"]
    assert "sha256" not in missing


def test_102_foam_assumption_stays_visible(tmp_path):
    problem = build_problem(evidence(102), Path("evidence.json"), tmp_path)
    assert any("assumed 7 mm" in note for note in problem["limitations"])
