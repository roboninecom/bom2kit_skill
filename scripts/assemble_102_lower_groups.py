"""Place two certified printed groups using proper rigid quarter-turns."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_validation import validate_mesh_layout


def main():
    inputs = [
        (ROOT / "packaging-results/evidence-audit/box1-experiment/manual-16-merged-problem.json",
         ROOT / "packaging-results/evidence-audit/box1-experiment/manual-16-merged-layout.json"),
        (ROOT / "packaging-results/so-arm-102/current-box2-remaining-ten/input.json",
         ROOT / "packaging-results/so-arm-102/current-box2-remaining-ten/layout.json")]
    items, placements, records = [], [], []
    cursor = 0.0
    turn = np.eye(4)
    turn[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
    for input_path, layout_path in inputs:
        problem = json.loads(input_path.read_text())
        layout = json.loads(layout_path.read_text())
        certificate = validate_mesh_layout(problem, layout)
        if not certificate["valid"]:
            raise ValueError(certificate["errors"])
        lookup = {item["id"]: item for item in problem["items"]}
        bounds = []
        for pose in layout["placements"]:
            ref = lookup[pose["item_id"]]["mesh"]
            raw = Path(ref["path"]).read_bytes()
            if sha256(raw).hexdigest() != ref["sha256"]:
                raise ValueError("Source changed")
            source = json.loads(raw)
            mesh = trimesh.Trimesh(source["vertices_mm"], source["triangles"], process=False)
            mesh.apply_transform(turn @ np.asarray(pose["transform"]))
            bounds.append(mesh.bounds)
        low = np.min(np.asarray(bounds)[:, 0], axis=0)
        high = np.max(np.asarray(bounds)[:, 1], axis=0)
        group_transform = turn.copy()
        group_transform[:3, 3] = np.asarray([cursor, 0, 0]) - low
        for pose in layout["placements"]:
            adjusted = deepcopy(pose)
            adjusted["transform"] = (group_transform @ np.asarray(pose["transform"])).tolist()
            placements.append(adjusted)
        items.extend(deepcopy(problem["items"]))
        records.append({"input_path": str(input_path), "input_sha256": sha256(input_path.read_bytes()).hexdigest(),
                        "layout_path": str(layout_path), "layout_sha256": sha256(layout_path.read_bytes()).hexdigest(),
                        "group_transform": group_transform.tolist(), "rotated_extent_mm": (high - low).tolist()})
        cursor += high[0] - low[0] + .1
    problem = {"units": "mm", "container": {"inner_mm": [329, 243, 72]}, "clearance_mm": .1,
               "items": items, "provenance": records,
               "scope": "26 current printed meshes in two rigid groups. Bearings and purchased components excluded, not full kit."}
    layout = {"units": "mm", "placements": placements}
    certificate = validate_mesh_layout(problem, layout)
    output = ROOT / "packaging-results/so-arm-102/lower-26-assembled"
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("input", problem), ("layout", layout), ("validation", certificate)):
        (output / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({"validation": certificate, "occupied_width_mm": cursor - .1,
                      "remaining_width_mm": 329 - cursor}, indent=2))
    return 0 if certificate["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
