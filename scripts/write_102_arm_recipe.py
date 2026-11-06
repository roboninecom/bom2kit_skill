"""Reproduce the independently checked 65 mm spacing of two current arm pairs."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_validation import validate_mesh_layout


def main():
    directory = ROOT / "packaging-results/so-arm-102/current-four-arm-top"
    problem = json.loads((directory / "input.json").read_text())
    layout = deepcopy(json.loads((directory / "layout.json").read_text()))
    poses = {pose["unit_id"]: pose for pose in layout["placements"]}
    for item_id in ("left", "right"):
        first, second = poses[item_id + "#1"], poses[item_id + "#2"]
        if abs(second["transform"][1][3] - first["transform"][1][3] - 68) > 1e-6:
            raise ValueError("Expected the original current-source 68 mm pair spacing")
        second["transform"][1][3] -= 3
    certificate = validate_mesh_layout(problem, layout)
    if not certificate["valid"]:
        raise ValueError(certificate["errors"])
    layout["validation"] = certificate
    (directory / "compact-65-layout.json").write_text(json.dumps(layout, indent=2))
    print("Four current arm meshes validated with 65 mm pair spacing; no scaling.")


if __name__ == "__main__":
    main()
