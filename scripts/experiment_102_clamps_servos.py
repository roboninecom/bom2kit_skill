"""Search actual historical custom-clamp proxies and declared servo sleeves together."""
import json
from hashlib import sha256
from pathlib import Path
import sys

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_validation import validate_mesh_layout


def main():
    source = ROOT / "packaging-results/evidence-audit/purchased-assumptions"
    output = ROOT / "packaging-results/so-arm-102/upper-clamps-servos"
    output.mkdir(parents=True, exist_ok=True)
    problem = json.loads((source / "clamp-custom106-historical-four-problem.json").read_text())
    layout = json.loads((source / "clamp-custom106-historical-four-layout.json").read_text())
    problem["container"]["inner_mm"] = [127.8, 246, 64.2]
    problem["scope"] = "Four historical custom106 clamp proxies, ten 1mm EPE servo envelopes and factory extras; other kit contents excluded. Cushioning performance unverified."
    clamp = problem["items"][0]
    clamp["contents"] = {"Clamp": 1}
    geometry = json.loads(Path(clamp["mesh"]["path"]).read_text())
    vertices = np.asarray(geometry["vertices_mm"])
    rotation = np.eye(4)
    rotation[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
    transforms = [rotation @ np.asarray(p["transform"]) for p in layout["placements"]]
    points = np.concatenate([trimesh.transform_points(vertices, t) for t in transforms])
    minimum = points.min(axis=0)
    maximum = points.max(axis=0) - minimum
    seed = []
    for pose, transform in zip(layout["placements"], transforms):
        transform[:3, 3] -= minimum
        seed.append({**pose, "transform": transform.tolist()})
    catalogue = json.loads((ROOT / "packaging-inputs/benchmarks/purchased-assumptions/102-hardware-official-servo.json").read_text())
    servo_units = []
    for item in catalogue["items"]:
        if not item["id"].endswith("_protected_sleeve"):
            continue
        item = dict(item)
        item["dimensions_mm"] = [48, 27, 40]
        item["packing_state_change"] = "1 mm EPE per face around official ST3215 CAD body45.2234x24.7234x37.8 mm, rounded outward. Other servo models retain declared family-envelope assumption. This replaces estimated2mm cushioning; protection equivalence is not certified."
        item["original_dimension_basis"] = item.get("dimension_basis")
        item["dimension_basis"] = item["packing_state_change"]
        item["packing_state"] = "Individual1mm EPE sleeve; accessories separately retained."
        if "C066" in item["id"]:
            item["quantity"] -= 2
            item["allocation_note"] = "Two of six C066 units already allocated to the lower carton."
        mesh = trimesh.creation.box(extents=item["dimensions_mm"])
        mesh.apply_translation(-mesh.bounds[0])
        path = output / (item["id"] + ".json")
        path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist(), "assumption": item}, indent=2))
        item["mesh"] = {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}
        problem["items"].append(item)
        servo_units.extend((item["id"], f"{item['id']}#{n+1}") for n in range(item["quantity"]))
    for index, (item_id, unit_id) in enumerate(servo_units[:8]):
        x = (index % 2) * 48.1
        y = maximum[1] + 0.1 + ((index // 2) % 2) * 40.1
        z = (index // 4) * 27.1
        transform = [[1, 0, 0, x], [0, 0, 1, y], [0, -1, 0, z + 27], [0, 0, 0, 1]]
        seed.append({"item_id": item_id, "unit_id": unit_id, "transform": transform})
    for index, (item_id, unit_id) in enumerate(servo_units[8:]):
        transform = [[0, 1, 0, 96.2], [0, 0, 1, maximum[1] + 0.1 + index * 40.1], [1, 0, 0, 0], [0, 0, 0, 1]]
        seed.append({"item_id": item_id, "unit_id": unit_id, "transform": transform})
    flat = json.loads((ROOT / "packaging-inputs/benchmarks/purchased-assumptions/102-hardware-flat-packets.json").read_text())
    extras = next(dict(i) for i in flat["items"] if i["id"] == "all_factory_servo_accessories_packet")
    mesh = trimesh.creation.box(extents=extras["dimensions_mm"])
    mesh.apply_translation(-mesh.bounds[0])
    path = output / "factory-extras.json"
    path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist(), "assumption": extras}, indent=2))
    extras["mesh"] = {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}
    problem["items"].append(extras)
    seed.append({"item_id": extras["id"], "unit_id": extras["id"] + "#1", "transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 52.1], [0, 0, 0, 1]]})
    result = {"units": "mm", "placements": seed, "method": "Explicit rigid group construction; independent final mesh validation."}
    certificate = validate_mesh_layout(problem, result)
    for name, value in (("input", problem), ("layout", result), ("validation", certificate)):
        (output / f"{name}.json").write_text(json.dumps(value, indent=2))
    print(certificate["valid"], len(seed), certificate["errors"], flush=True)


if __name__ == "__main__":
    main()
