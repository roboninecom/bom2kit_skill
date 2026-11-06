"""Validate alternate nominal cartons without claiming their contents fit.

Run after run_benchmarks.py. Source groups and their declared quantities remain
traceable even where the source has no detailed contents ledger.
"""

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bom2kit.solver import solve
from bom2kit.validation import validate
from bom2kit.report import render_report


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf8")


def split_upper_arms():
    problem = json.loads((ROOT / "packaging-results/benchmarks/so-arm-102/input.json").read_text())
    problem.pop("reference_layout", None)
    boxes = {item["id"]: item for item in problem["items"]}
    rotations = boxes["BOX1"]["allowed_rotations"]
    groups = [deepcopy(boxes[key]) for key in ("BOX1", "BOX2", "BOX3", "BOX4", "BOX6")]
    arms = {"SO102.02.080 Upper arm left": 2, "SO102.02.080-01 Upper arm right": 2}
    for key, quantity in arms.items():
        if groups[1]["contents"].get(key) != quantity:
            raise ValueError("Upper-arm source allocation changed")
        del groups[1]["contents"][key]
    problem["items"] = [
        {"id": "LOWER_REASSIGNED", "quantity": 1, "dimensions_mm": [332, 246, 75],
         "inner_dimensions_mm": [329, 243, 72], "wall_mm": 1.5, "allowed_rotations": rotations,
         "source_groups": groups, "contents_validation": "Not yet validated; purchased source groups remain unexpanded"},
        deepcopy(boxes["BOX5"]), deepcopy(boxes["BOX7"]),
        {"id": "FOUR_UPPER_ARMS", "quantity": 1, "dimensions_mm": [207, 150, 60],
         "inner_dimensions_mm": [204, 147, 57], "wall_mm": 1.5, "allowed_rotations": rotations,
         "contents": arms, "mesh_certificate": "packaging-results/so-arm-102/current-four-arm-top/validation.json"}]
    problem["name"] = "SO-ARM102: split upper arms, reassigned lower contents catalogue"
    problem["limitations"] += [
        "All BOX1/2/3/4/6 source groups remain assigned to the lower carton, except four upper arms explicitly reassigned upstairs. This is not a lower part-level fit certificate.",
        "PSUs, clamps, electronics and bags require lower-cavity validation. BOX3 and BOX6 cartons are replaced; their contents cannot be omitted."]
    directory = ROOT / "packaging-results/regrouping/so-arm-102/split-upper-arms"
    layout = solve(problem, time_limit=5)
    certificate = validate(problem, layout)
    for name, value in (("input", problem), ("layout", layout), ("validation", certificate)):
        write(directory / f"{name}.json", value)
    render_report(problem, layout, certificate, directory)
    return {"model": "so-arm-102", "variant": "split-upper-arms", "lower_inner_mm": [329, 243, 72],
            "carton_external_mm": [376, 290, 184], "nominal_outer_geometry_valid": certificate["valid"],
            "full_kit_acceptance": False, "directory": str(directory)}


def run():
    summary = []
    for model, width in (("so-arm-101", 268), ("so-arm-102", 280)):
        source = ROOT / "packaging-results/benchmarks" / model / "input.json"
        original = json.loads(source.read_text(encoding="utf8"))
        ledger_path = ROOT / "packaging-inputs/benchmarks" / f"{model}-r3-declared-contents.json"
        ledgers = {}
        if ledger_path.exists():
            ledgers = {i["id"]: i["contents"] for i in json.loads(ledger_path.read_text())["problem"]["items"]}
        variants = [(["BOX2", "BOX4"], [164, 246, 75], 1),
                    (["BOX1", "BOX2", "BOX4"], [width, 246, 75], 1)]
        if model == "so-arm-101":
            variants.append((["BOX1", "BOX2", "BOX4"], [width, 246, 75.2], .8))
        for members, dimensions, reserved_top in variants:
            problem = deepcopy(original)
            problem.pop("reference_layout", None)
            merged_id = "MERGED_" + "_".join(members)
            if reserved_top != 1:
                merged_id += "_H75_2"
                problem["container"]["reserved_top_mm"] = reserved_top
            records, total, unknown = [], Counter(), []
            for item in original["items"]:
                if item["id"] in members:
                    contents = ledgers.get(item["id"], item.get("contents"))
                    records.append({"source_group": item["id"], "quantity": item["quantity"], "contents": contents})
                    if contents is None:
                        unknown.append(item["id"])
                    else:
                        total.update(contents)
            merged = {"id": merged_id, "quantity": 1, "dimensions_mm": dimensions,
                      "inner_dimensions_mm": [d - 3 for d in dimensions], "wall_mm": 1.5,
                      "allowed_rotations": original["items"][0]["allowed_rotations"],
                      "contents": dict(total), "source_groups": records,
                      "unexpanded_source_groups": unknown}
            problem["items"] = [i for i in problem["items"] if i["id"] not in members] + [merged]
            problem["name"] = f"{model}: {merged_id} alternate nominal carton"
            problem["limitations"] += [
                "Merged carton is a proposed replacement. Contents have not been packed or geometrically validated inside it.",
                "Unknown source-group contents remain explicitly unexpanded. No full-kit claim.",
                "Bags, separators, material strength and protective performance need separate validation."]
            if reserved_top != 1:
                box3 = next(item for item in problem["items"] if item["id"] == "BOX3")
                box3["original_dimensions_mm"] = box3["dimensions_mm"][:]
                box3["dimensions_mm"][1] = 75.2
                box3["inner_dimensions_mm"][1] = 72.2
                problem["limitations"] = [text for text in problem["limitations"]
                                          if "top 1 mm is reserved" not in text]
                problem["limitations"].append(
                    "Explicit alternate height: merged carton outer 75.2 mm / inner 72.2 mm. "
                    "Only 0.8 mm remains for the booklet; its actual thickness is unverified. "
                    "BOX3 is also redesigned from 246x75x52 to 246x75.2x52 mm externally, "
                    "forming an equal-height fully supported lower layer without shims. "
                    "New-carton material, load performance and cost are unverified. "
                    "No mesh scaling or relaxed cavity tolerance is implied.")
            layout = solve(problem, time_limit=5)
            certificate = validate(problem, layout)
            directory = ROOT / "packaging-results/regrouping" / model / merged_id.lower()
            preservation = {"source_input_sha256": sha256(source.read_bytes()).hexdigest(),
                            "original_source_groups": records, "merged_declared_contents": dict(total),
                            "unexpanded_source_groups": unknown,
                            "source_groups_preserved": len(records) == len(members),
                            "full_item_ledger_known": not unknown, "full_kit_acceptance": False}
            if ledgers:
                preservation["contents_source_sha256"] = sha256(ledger_path.read_bytes()).hexdigest()
            for name, value in (("input", problem), ("layout", layout), ("validation", certificate), ("contents-ledger", preservation)):
                write(directory / f"{name}.json", value)
            render_report(problem, layout, certificate, directory)
            summary.append({"model": model, "merged_group": merged_id,
                            "outer_mm": dimensions, "inner_mm": merged["inner_dimensions_mm"],
                            "carton_external_mm": original["reference"]["external_mm"],
                            "reserved_top_mm": reserved_top,
                            "nominal_outer_geometry_valid": certificate["valid"],
                            "full_kit_acceptance": False, "directory": str(directory)})
    summary.append(split_upper_arms())
    write(ROOT / "packaging-results/regrouping/summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if all(r["nominal_outer_geometry_valid"] for r in summary) else 1


if __name__ == "__main__":
    raise SystemExit(run())
