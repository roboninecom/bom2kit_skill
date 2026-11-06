"""Provisional 101 BOX1 geometry search; component-to-SKU mapping is inferred."""

from pathlib import Path
from hashlib import sha256
import json
import sys
import time

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_geometry import load_instance_mesh
from bom2kit.mesh_packing import solve_mesh_pair
from bom2kit.mesh_validation import validate_mesh_layout
from experiment_box7 import pack, write


def run(output, seconds=30):
    started = time.perf_counter()
    style = ROOT / "packaging-inputs/so-arm-101/style/Black and white Robonine style"
    follower = next((style / "STL/STL").glob("SO-ARM101_Follower_Robo9.*"))
    leader = next(style.rglob("SO-ARM101_Leader_Robo9.3mf"))
    follower_parts = list(trimesh.load_mesh(follower).split(only_watertight=False))
    definitions = [("F_base_holder", 1), ("F_upper_arm", 2), ("F_board_plate", 4), ("F_wrist_holder", 5),
                   ("F_under_arm", 8), ("F_side_holder", 10),
                   ("L_upper_arm", 0), ("L_under_arm", 1), ("L_base_holder", 2),
                   ("L_wrist_holder", 4), ("L_side_holder", 5), ("L_board_plate", 8), ("L_wrist_roll", 10)]
    items, manifest, transforms, envelopes = [], [], {}, {}
    for item_id, index in definitions:
        if item_id.startswith("F_"):
            source, mesh = follower, follower_parts[index]
            selector = {"disconnected_component_index": index}
        else:
            source = leader
            instance = f"build-{index + 1}/leaf-{index + 1}"
            geometry = load_instance_mesh(source, instance)
            mesh = trimesh.Trimesh(vertices=geometry["vertices_mm"], faces=geometry["triangles"], process=False)
            selector = {"instance_id": instance}
        if not mesh.is_volume or np.any(mesh.area_faces <= 0):
            raise ValueError(f"Invalid source geometry: {item_id}")
        path = output / "meshes" / f"{item_id}.json"
        write(path, {"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist()})
        digest = sha256(path.read_bytes()).hexdigest()
        items.append({"id": item_id, "quantity": 1, "mesh": {"path": str(path.resolve()), "sha256": digest}})
        obb, extents = trimesh.bounds.oriented_bounds(mesh)
        rotation = np.eye(4)
        rotation[:3,:3] = [[0,0,1],[0,1,0],[-1,0,0]]
        transform = rotation @ obb
        transformed = trimesh.transform_points(mesh.vertices, transform)
        transform[:3,3] -= transformed.min(axis=0)
        transformed = trimesh.transform_points(mesh.vertices, transform)
        dimensions = np.ptp(transformed, axis=0)
        normalized = output / "meshes" / f"{item_id}-obb.json"
        write(normalized, {"units": "mm", "vertices_mm": transformed.tolist(), "triangles": mesh.faces.tolist()})
        transforms[item_id] = transform
        envelopes[item_id] = dimensions
        manifest.append({"id": item_id, "source": str(source), "source_sha256": sha256(source.read_bytes()).hexdigest(),
                         "selector": selector, "mapping": "Inferred by morphology and matching component volumes; SKU identity not independently certified",
                         "original_mesh_sha256": digest, "obb_transform": transform.tolist(), "envelope_mm": dimensions.tolist()})
    problem = {"units": "mm", "container": {"inner_mm": [243,101,72]}, "clearance_mm": .1, "items": items,
               "dimension_provenance": "User-confirmed external 246 x 104 x 75 mm; wall 1.5 mm",
               "identity_status": "Provisional component-to-SKU mapping; geometry check only"}
    write(output / "input.json", problem)
    write(output / "source-manifest.json", manifest)
    units = [{"item_id": item["id"], "unit_id": item["id"] + "#1", "size": envelopes[item["id"]].tolist(), "low": [0,0,0]}
             for item in items]
    groups = {}
    for name, maximum in (("upper_arm", [150,72,44]), ("under_arm", [140,70,44])):
        pair_items = []
        for side in ("F", "L"):
            item_id = f"{side}_{name}"
            path = output / "meshes" / f"{item_id}-obb.json"
            pair_items.append({"id": item_id, "mesh": {"path": str(path.resolve()), "sha256": sha256(path.read_bytes()).hexdigest()}})
        pair_problem = {"units": "mm", "container": {"inner_mm": maximum}, "clearance_mm": .1, "items": pair_items}
        result = solve_mesh_pair(pair_problem, time_limit=seconds, pitch_mm=2, candidates_per_rotation=30)
        write(output / f"{name}-pair-input.json", pair_problem)
        write(output / f"{name}-pair-layout.json", result)
        if result["status"] == "validated_static_layout":
            groups[name] = result
            units = [unit for unit in units if unit["item_id"] not in (f"F_{name}", f"L_{name}")]
            units.append({"item_id": name, "unit_id": name + "#1", "size": result["envelope_mm"], "low": [0,0,0]})
    positions, statistics = pack(units, [243,101,72], seconds)
    write(output / "search.json", statistics)
    if positions is None:
        result = {"status": "no_complete_layout", "statistics": statistics,
                  "groups": {key: group["envelope_mm"] for key,group in groups.items()},
                  "elapsed_seconds": time.perf_counter() - started}
        write(output / "result.json", result)
        return result
    placements = []
    for placed in positions:
        rotation = np.eye(3)[list(placed["axes"])]
        if np.linalg.det(rotation) < 0:
            rotation[0] *= -1
        corners = np.array([[x,y,z] for x in (0,placed["size"][0]) for y in (0,placed["size"][1]) for z in (0,placed["size"][2])])
        transform = np.eye(4)
        transform[:3,:3] = rotation
        transform[:3,3] = placed["position"] + .055 - (corners @ rotation.T).min(axis=0)
        if placed["item_id"] in groups:
            for entry in groups[placed["item_id"]]["placements"]:
                placements.append({"item_id": entry["item_id"], "unit_id": entry["unit_id"],
                                   "transform": (transform @ np.array(entry["transform"]) @ transforms[entry["item_id"]]).tolist()})
        else:
            placements.append({"item_id": placed["item_id"], "unit_id": placed["unit_id"],
                               "transform": (transform @ transforms[placed["item_id"]]).tolist()})
    layout = {"units": "mm", "placements": placements}
    validation = validate_mesh_layout(problem, layout)
    write(output / "layout.json", layout)
    write(output / "validation.json", validation)
    result = {"valid": validation["valid"], "errors": validation["errors"], "expected_units": 13,
              "placed_units": validation["placed_units"], "identity_verified": False,
              "elapsed_seconds": time.perf_counter() - started}
    write(output / "result.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(run(ROOT / "packaging-results/so-arm-101/box1-mesh-experiment"), indent=2))
