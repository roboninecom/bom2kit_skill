"""Assemble all 61 current printed parts inside the proposed outer carton.

Purchased hardware is excluded explicitly; this is a printed-geometry certificate.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_validation import validate_mesh_layout
from bom2kit.validation import validate


def main():
    outer_dir = ROOT / "packaging-results/regrouping/so-arm-102/split-upper-arms"
    outer = json.loads((outer_dir / "input.json").read_text())
    outer_layout = json.loads((outer_dir / "layout.json").read_text())
    if not validate(outer, outer_layout)["valid"]:
        raise ValueError("Outer carton arrangement is invalid")
    cartons = {pose["item_id"]: pose for pose in outer_layout["placements"]}
    groups = [("LOWER_REASSIGNED", ROOT / "packaging-results/so-arm-102/lower-26-assembled"),
              ("FOUR_UPPER_ARMS", ROOT / "packaging-results/so-arm-102/current-four-arm-top"),
              ("BOX7", ROOT / "packaging-results/box7-nested-experiment")]
    items, placements, provenance = [], [], []
    for carton_id, directory in groups:
        problem_path, layout_path = directory / "input.json", directory / "layout.json"
        group = json.loads(problem_path.read_text())
        layout = json.loads(layout_path.read_text())
        carton = cartons[carton_id]
        if carton["rotation"] != [0, 1, 2]:
            raise ValueError("This assembly requires the documented carton orientation")
        group_transform = np.eye(4)
        group_transform[:3, 3] = np.asarray(carton["position_mm"]) + 1.5
        items.extend(deepcopy(group["items"]))
        for pose in layout["placements"]:
            adjusted = deepcopy(pose)
            adjusted["transform"] = (group_transform @ np.asarray(pose["transform"])).tolist()
            placements.append(adjusted)
        provenance.append({"carton_id": carton_id, "input_path": str(problem_path),
                           "input_sha256": sha256(problem_path.read_bytes()).hexdigest(),
                           "layout_path": str(layout_path), "layout_sha256": sha256(layout_path.read_bytes()).hexdigest(),
                           "transform": group_transform.tolist()})
    if sum(item["quantity"] for item in items) != 61:
        raise ValueError("Expected exactly 61 printed parts")
    problem = {"units": "mm", "container": deepcopy(outer["container"]), "clearance_mm": .1,
               "items": items, "provenance": provenance,
               "scope": "All 61 current printed parts only. Purchased hardware, booklet, protective strength and physical trial excluded.",
               "outer_carton_input_sha256": sha256((outer_dir / "input.json").read_bytes()).hexdigest(),
               "outer_carton_layout_sha256": sha256((outer_dir / "layout.json").read_bytes()).hexdigest()}
    layout = {"units": "mm", "placements": placements}
    started = perf_counter()
    certificate = validate_mesh_layout(problem, layout)
    elapsed = perf_counter() - started
    output = ROOT / "packaging-results/so-arm-102/full-printed-61"
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("input", problem), ("layout", layout), ("validation", certificate),
                        ("timing", {"validation_seconds": elapsed})):
        (output / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({"valid": certificate["valid"], "errors": certificate["errors"],
                      "expected_units": certificate["expected_units"], "placed_units": certificate["placed_units"],
                      "validation_seconds": elapsed}))
    return 0 if certificate["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
