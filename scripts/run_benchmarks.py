"""Reproduce nominal 101/102 carton benchmarks from local evidence JSON.

Run from the repository: python scripts/run_benchmarks.py
Downloaded evidence and generated artifacts remain in ignored directories.
"""

import argparse
import copy
from hashlib import sha256
from itertools import permutations
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bom2kit.models import normalize, number
from bom2kit.report import comparison, render_report
from bom2kit.solver import solve
from bom2kit.validation import validate


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def source_record(path, root=ROOT):
    source = Path(path)
    actual = source if source.is_absolute() else root / source
    result = {"path": str(source), "available": actual.is_file()}
    if actual.is_file():
        result.update({"sha256": sha256(actual.read_bytes()).hexdigest(), "size_bytes": actual.stat().st_size})
    return result


def reference_reconstruction(problem):
    """Reconstruct the documented two-layer scheme, not measured CAD poses."""
    boxes = {item["id"]: item for item in problem["items"]}
    offset = normalize(problem)["protection"]
    first_width = boxes["BOX1"]["dimensions_mm"][1]
    third_width = boxes["BOX3"]["dimensions_mm"][2]
    second_length = boxes["BOX2"]["dimensions_mm"][0]
    specification = [
        ("BOX1", (0, 0, 0), (1, 0, 2)),
        ("BOX3", (first_width, 0, 0), (2, 0, 1)),
        ("BOX2", (first_width + third_width, 0, 0), (1, 0, 2)),
        ("BOX4", (first_width + third_width, second_length, 0), (0, 2, 1)),
        ("BOX5", (0, 0, 75), (1, 0, 2)),
        ("BOX6", (124, 0, 75), (0, 1, 2)),
        ("BOX7", (124, 168, 75), (0, 1, 2)),
    ]
    placements = [{"item_id": item_id, "unit_id": f"{item_id}#1",
                   "position_mm": [p + shift for p, shift in zip(position, offset)],
                   "dimensions_mm": [boxes[item_id]["dimensions_mm"][axis] for axis in rotation],
                   "rotation": list(rotation)} for item_id, position, rotation in specification]
    return {"kind": "Alan reference reconstruction", "placements": placements,
            "provenance": "Reconstructed nominal two-layer closed-box layout from source dimensions; not measured part poses"}


def build_problem(evidence, evidence_path, root=ROOT):
    model = evidence["model"]
    if model not in ("SO-ARM101", "SO-ARM102"):
        raise ValueError(f"Unsupported benchmark model: {model}")
    inner = [350 if model == "SO-ARM101" else 362, 276, 170]
    records = [source_record(evidence_path, root)]
    paths = list(evidence.get("sources", []))
    foam_source = evidence.get("foam", {}).get("source")
    if foam_source and foam_source not in paths:
        paths.append(foam_source)
    records.extend(source_record(path, root) for path in paths)
    items = copy.deepcopy(evidence["boxes"])
    for item in items:
        item["allowed_rotations"] = [list(rotation) for rotation in permutations(range(3))]
    limitations = [
        "Nominal closed-box benchmark only. Declared box contents are copied from evidence and are not geometrically validated here.",
        "Orthogonal rotations of closed boxes are permitted for this benchmark. BOX3 and BOX4 are turned to produce a 75 mm lower layer; lid-up operation is not verified.",
        "Lateral clearance is zero, as in the nominal engineering scheme; this is not a manufacturing tolerance or insertion-clearance certification.",
        "The top 1 mm is reserved for a booklet. Booklet plan dimensions and physical thickness remain unverified.",
        "Alan's diagram is an explicitly labeled reconstruction from dimensions, not an imported authoritative 3D packing assembly.",
    ] + evidence.get("unresolved", []) + evidence.get("unresolved_content", [])
    if model == "SO-ARM102":
        limitations.append("102 uses the assumed 7 mm carton wall and 15 mm foam adopted from 101; a 102-specific foam drawing is not available.")
    problem = {"name": f"{model}: nominal carton benchmark", "units": "mm", "items": items,
               "container": {"inner_mm": inner, "wall_mm": 7, "protection_mm": 15, "reserved_top_mm": 1},
               "gap_mm": 0, "allow_dunnage": False,
               "reference": {"author": evidence.get("reference_author", "Alan Subin"),
                             "external_mm": evidence["reference_outer_mm"],
                             "kind": "Source nominal external carton dimensions"},
               "sources": [f"{r['path']} | SHA-256 {r.get('sha256', 'unavailable')}" for r in records],
               "source_records": records, "content_basis": evidence.get("content_basis"),
               "limitations": limitations}
    problem["reference_layout"] = reference_reconstruction(problem)
    return problem


def run_benchmarks(input_dir=None, output_dir=None, time_limit=5, root=ROOT):
    time_limit = number(time_limit, "time_limit", True)
    input_dir = Path(input_dir) if input_dir else root / "packaging-inputs" / "benchmarks"
    output_dir = Path(output_dir) if output_dir else root / "packaging-results" / "benchmarks"
    results = []
    for model in ("so-arm-101", "so-arm-102"):
        evidence_path = input_dir / f"{model}-evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
        problem = build_problem(evidence, evidence_path, root)
        reference_check = validate(problem, problem["reference_layout"])
        if not reference_check["valid"]:
            raise ValueError(f"Reference reconstruction failed for {model}: {reference_check['errors']}")
        # The reference is only for comparison: do not pass reference coordinates
        # to the independent search, even though the solver ignores that field.
        search_problem = {key: value for key, value in problem.items() if key != "reference_layout"}
        start = time.perf_counter()
        layout = solve(search_problem, time_limit=time_limit)
        elapsed = time.perf_counter() - start
        validation = validate(problem, layout)
        directory = output_dir / model
        write_json(directory / "input.json", problem)
        write_json(directory / "layout.json", layout)
        write_json(directory / "validation.json", validation)
        write_json(directory / "reference-validation.json", reference_check)
        write_json(directory / "evidence-manifest.json", problem["source_records"])
        render_report(problem, layout, validation, directory)
        measured = comparison(problem, layout)
        results.append({"model": evidence["model"], "status": layout["status"],
                        "geometry_valid": validation["valid"],
                        "placed_boxes": validation["placed_units"], "expected_boxes": validation["expected_units"],
                        "alan_reference_l": measured["reference_external_volume_l"],
                        "computed_l": measured["external_volume_l"],
                        "volume_change_percent": measured["volume_change_percent"],
                        "not_worse_nominal_carton_volume": measured["no_worse_nominal_carton_volume"],
                        "solver_seconds": layout["stats"]["elapsed_seconds"], "solve_call_seconds": elapsed,
                        "nodes": layout["stats"]["nodes"], "support_pads": validation["support_pads"],
                        "full_kit_acceptance": False, "input_sha256": measured["input_sha256"],
                        "layout_sha256": measured["layout_sha256"],
                        "report": str((directory / "instruction.html").resolve())})
    summary = {"scope": "Nominal seven-box carton comparison only; no part-level or physical acceptance",
               "results": results, "full_kit_acceptance": False,
               "all_nominal_benchmarks_pass": all(result["not_worse_nominal_carton_volume"] for result in results)}
    write_json(output_dir / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--time-limit", type=float, default=5)
    args = parser.parse_args(argv)
    try:
        result = run_benchmarks(args.input_dir, args.output_dir, args.time_limit)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"benchmark: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["all_nominal_benchmarks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
