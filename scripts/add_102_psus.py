"""Place explicit folded-lead PSU envelopes beside the lower printed group."""
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_validation import validate_mesh_layout


def main():
    lower = ROOT / "packaging-results/so-arm-102/split-bottom-28-manual"
    problem = json.loads((lower / "input.json").read_text())
    layout = json.loads((lower / "layout.json").read_text())
    catalogue_path = ROOT / "packaging-inputs/benchmarks/purchased-assumptions/102-hardware-flexible.json"
    catalogue = json.loads(catalogue_path.read_text())
    output = ROOT / "packaging-results/so-arm-102/lower-30-with-psus"
    output.mkdir(parents=True, exist_ok=True)
    lookup = {item["id"]: item for item in problem["items"]}
    max_x = 0
    for pose in layout["placements"]:
        item = lookup[pose["item_id"]]
        raw = Path(item["mesh"]["path"]).read_bytes()
        if sha256(raw).hexdigest() != item["mesh"]["sha256"]:
            raise ValueError("Lower source changed")
        vertices = np.asarray(json.loads(raw)["vertices_mm"])
        transform = np.asarray(pose["transform"])
        max_x = max(max_x, (vertices @ transform[:3, :3].T + transform[:3, 3])[:, 0].max())
    y = 0.0
    expected = {"PSU12_with_DC_lead": [120, 52, 45], "PSU5_with_DC_lead": [102, 47, 46]}
    for iid, dimensions in expected.items():
        source_item = next(item for item in catalogue["items"] if item["id"] == iid)
        if source_item["dimensions_mm"] != dimensions or source_item["quantity"] != 1:
            raise ValueError("PSU declared packing state changed; recompute placement")
        mesh = trimesh.creation.box(extents=dimensions)
        mesh.apply_translation(-mesh.bounds[0])
        path = output / f"{iid}.json"
        path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(),
                                    "triangles": mesh.faces.tolist(), "assumption_source": source_item}, indent=2))
        item = {**source_item, "mesh": {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}}
        problem["items"].append(item)
        transform = np.eye(4)
        transform[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
        transform[:3, 3] = [max_x + .1 + dimensions[1], y, 0]
        layout["placements"].append({"item_id": iid, "unit_id": iid + "#1", "transform": transform.tolist()})
        y += dimensions[0] + .1
    problem["container"]["inner_mm"] = [329, 243, 72]
    problem["scope"] = "26 current printed parts, two bagged bearing envelopes and two explicitly assumed folded-lead PSU envelopes. Remaining hardware excluded."
    problem["purchased_manifest_sha256"] = sha256(catalogue_path.read_bytes()).hexdigest()
    started = perf_counter()
    certificate = validate_mesh_layout(problem, layout)
    elapsed = perf_counter() - started
    for name, value in (("input", problem), ("layout", layout), ("validation", certificate),
                        ("timing", {"validation_seconds": elapsed})):
        (output / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({"valid": certificate["valid"], "errors": certificate["errors"], "validation_seconds": elapsed}))
    return 0 if certificate["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
