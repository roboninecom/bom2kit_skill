"""Revalidate a low-height four-arm pattern against current, unchanged meshes.

Only rigid translations align the older centered CAD frame to current CAD.
No geometry or scale is transferred from the older source.
"""
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_validation import validate_mesh_layout


def main():
    older = ROOT / "packaging-results/so-arm-102/mesh-upper-pair"
    input_path = older / "four-upper-164-problem.json"
    layout_path = older / "four-upper-164-layout.json"
    previous = json.loads(input_path.read_text())
    layout = json.loads(layout_path.read_text())
    current_path = ROOT / "packaging-results/so-arm-102/current-box2-beam-alternating/problem.json"
    current = {i["id"]: i for i in json.loads(current_path.read_text())["items"]}
    mapping = {"SO102.02.080 Upper arm": "left", "SO102.02.080-01 Upper arm right": "right"}
    items, frames = [], []
    for item in previous["items"]:
        iid = mapping[item["id"]]
        old_bytes = Path(item["mesh"]["path"]).read_bytes()
        new_bytes = Path(current[iid]["mesh"]["path"]).read_bytes()
        if sha256(old_bytes).hexdigest() != item["mesh"]["sha256"]:
            raise ValueError("Prior coordinate-frame source hash changed")
        if sha256(new_bytes).hexdigest() != current[iid]["mesh"]["sha256"]:
            raise ValueError("Current geometry source hash changed")
        old_vertices = np.asarray(json.loads(old_bytes)["vertices_mm"])
        new_vertices = np.asarray(json.loads(new_bytes)["vertices_mm"])
        align = np.eye(4)
        align[:3, 3] = old_vertices.min(axis=0) - new_vertices.min(axis=0)
        frames.append({"item_id": iid, "current_to_previous_frame": align.tolist(),
                       "previous_frame_source": item["mesh"]})
        for pose in layout["placements"]:
            if pose["item_id"] == item["id"]:
                pose["transform"] = (np.asarray(pose["transform"]) @ align).tolist()
                pose["item_id"] = iid
                pose["unit_id"] = iid + "#" + pose["unit_id"].split("#")[-1]
        items.append({key: value for key, value in current[iid].items() if key != "orientation_hint"})
    problem = {"units": "mm", "container": {"inner_mm": [204, 147, 57]},
               "clearance_mm": .1, "items": items,
               "scope": "Current-source rigid replay of prior four-arm pattern; no scaling; static geometry only.",
               "provenance": {"prior_input_sha256": sha256(input_path.read_bytes()).hexdigest(),
                              "prior_layout_sha256": sha256(layout_path.read_bytes()).hexdigest(),
                              "frames": frames}}
    certificate = validate_mesh_layout(problem, layout)
    output = ROOT / "packaging-results/so-arm-102/current-four-arm-top"
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("input", problem), ("layout", layout), ("validation", certificate)):
        (output / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps(certificate, indent=2))
    return 0 if certificate["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
