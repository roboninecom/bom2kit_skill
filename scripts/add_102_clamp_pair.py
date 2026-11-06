"""Add two declared legacy clamp proxies beside the certified lower 28 units."""
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


def vertices(item, transform):
    raw = Path(item["mesh"]["path"]).read_bytes()
    if sha256(raw).hexdigest() != item["mesh"]["sha256"]:
        raise ValueError("Source geometry hash changed")
    points = np.asarray(json.loads(raw)["vertices_mm"])
    return points @ transform[:3, :3].T + transform[:3, 3]


def main():
    lower = ROOT / "packaging-results/so-arm-102/split-bottom-28-manual"
    problem = json.loads((lower / "input.json").read_text())
    layout = json.loads((lower / "layout.json").read_text())
    lookup = {item["id"]: item for item in problem["items"]}
    max_x = max(vertices(lookup[p["item_id"]], np.asarray(p["transform"]))[:, 0].max()
                for p in layout["placements"])
    source = ROOT / "packaging-results/evidence-audit/purchased-assumptions"
    pair_problem = json.loads((source / "clamp-pair-problem.json").read_text())
    pair = json.loads((source / "clamp-pair-wide-result.json").read_text())
    item = deepcopy(pair_problem["items"][0])
    item["contents"] = {"C_clamp_3inch": 1}
    item["dimension_basis"] = "ASSUMPTION: historical closed-clamp Boolean union proxy; current supplier geometry unmeasured"
    turn = np.eye(4)
    turn[:3, :3] = [[0, 0, 1], [1, 0, 0], [0, 1, 0]]
    all_points = np.concatenate([vertices(item, turn @ np.asarray(p["transform"])) for p in pair["placements"]])
    turn[:3, 3] = np.asarray([max_x + .1, 0, 0]) - all_points.min(axis=0)
    for pose in pair["placements"]:
        adjusted = deepcopy(pose)
        adjusted["transform"] = (turn @ np.asarray(pose["transform"])).tolist()
        layout["placements"].append(adjusted)
    problem["items"].append(item)
    problem["container"]["inner_mm"] = [329, 243, 72]
    problem["scope"] = "26 current printed meshes, two bagged bearing assumption envelopes, and TWO of FOUR clamp proxies; remaining hardware excluded."
    problem["clamp_pair_provenance"] = {"layout_sha256": sha256((source / "clamp-pair-wide-result.json").read_bytes()).hexdigest(),
                                         "group_transform": turn.tolist(), "assumption": item["dimension_basis"]}
    started = perf_counter()
    certificate = validate_mesh_layout(problem, layout)
    elapsed = perf_counter() - started
    output = ROOT / "packaging-results/so-arm-102/lower-30-with-clamp-pair"
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("input", problem), ("layout", layout), ("validation", certificate),
                        ("timing", {"validation_seconds": elapsed})):
        (output / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({"valid": certificate["valid"], "errors": certificate["errors"], "validation_seconds": elapsed}))
    return 0 if certificate["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
