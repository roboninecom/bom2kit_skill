"""Search rigid wrist translations with continuous straight-line assembly evidence."""
from copy import deepcopy
import itertools
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_motion import check_vertical_sequence
from bom2kit.mesh_validation import validate_mesh_layout


def main():
    source = ROOT / "packaging-results/box7-nested-experiment"
    output = ROOT / "packaging-results/so-arm-102/box7-wrist-repair"
    output.mkdir(parents=True, exist_ok=True)
    problem = json.loads((source / "input.json").read_text())
    problem["container"]["inner_mm"] = [193, 75, 64.1]
    problem["packing_state_change"] = "Upper shared bag replaces original rigid BOX7 carton; height may use the existing64.2mm upper layer, including0.05mm film per face."
    layout = json.loads((source / "layout.json").read_text())
    items = {i["id"]: i for i in problem["items"]}
    meshes = {}
    for item in items.values():
        data = json.loads(Path(item["mesh"]["path"]).read_text())
        meshes[item["id"]] = trimesh.Trimesh(data["vertices_mm"], data["triangles"], process=False)
    fixed = trimesh.collision.CollisionManager()
    pair_fixed = trimesh.collision.CollisionManager()
    moving_pose = next(p for p in layout["placements"] if p["unit_id"] == "wrist_holder#2")
    original = np.asarray(moving_pose["transform"])
    for pose in layout["placements"]:
        if pose["unit_id"] == moving_pose["unit_id"]:
            continue
        mesh = meshes[pose["item_id"]].copy()
        mesh.apply_transform(pose["transform"])
        fixed.add_object(pose["unit_id"], mesh)
        if pose["unit_id"] == "wrist_holder#1":
            pair_fixed.add_object("first", mesh)
            first_mesh = mesh
    moving = trimesh.collision.CollisionManager()
    moving.add_object("second", meshes["wrist_holder"])
    directions = [np.asarray(d, dtype=float) for d in ((0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0))]
    directions += [np.asarray(d, dtype=float) / np.linalg.norm(d) for d in itertools.product((-1, 0, 1), repeat=3) if sum(bool(v) for v in d) > 1]
    first_pose = next(p for p in layout["placements"] if p["unit_id"] == "wrist_holder#1")
    first_rotation = np.asarray(first_pose["transform"])[:3, :3]
    candidates = []
    for signs in ((1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)):
        rotation = np.diag(signs) @ first_rotation
        oriented = meshes["wrist_holder"].vertices @ rotation.T
        low = oriented.min(0)
        for z, y, x in itertools.product(np.arange(.055, 30.4, 1.5), np.arange(.055, 12.4, 1.5), np.arange(.055, 117, 3)):
            transform = np.eye(4)
            transform[:3, :3] = rotation
            transform[:3, 3] = np.asarray([x, y, z]) - low
            candidates.append((transform, {"axis_signs": signs, "minimum_mm": [x, y, z]}))
    started, clear_candidates = perf_counter(), 0
    for transform, delta in candidates:
        if perf_counter() - started > 300:
            break
        vertices = trimesh.transform_points(meshes["wrist_holder"].vertices, transform)
        if np.any(vertices.min(0) < 0) or np.any(vertices.max(0) > problem["container"]["inner_mm"]):
            continue
        moving.set_transform("second", transform)
        if fixed.in_collision_other(moving) or fixed.min_distance_other(moving) < .1 - 1e-8:
            continue
        clear_candidates += 1
        print("clear candidate", delta, flush=True)
        for direction in directions:
            moved, passed = 0., False
            moving.set_transform("second", transform)
            for _ in range(2500):
                if moved > 200:
                    passed = True
                    break
                distance = pair_fixed.min_distance_other(moving)
                if distance < 1e-6:
                    break
                moved += min(distance * .49, 201 - moved)
                t = transform.copy()
                t[:3, 3] += direction * moved
                moving.set_transform("second", t)
            if not passed:
                continue
            candidate = deepcopy(layout)
            next(p for p in candidate["placements"] if p["unit_id"] == moving_pose["unit_id"])["transform"] = transform.tolist()
            validation = validate_mesh_layout(problem, candidate)
            if not validation["valid"]:
                continue
            rotation = trimesh.geometry.align_vectors(direction, [0, 0, 1])
            pair_poses, pair_vertices = [], []
            for pose in candidate["placements"]:
                if pose["item_id"] != "wrist_holder":
                    continue
                t = rotation @ np.asarray(pose["transform"])
                pair_poses.append({**pose, "transform": t.tolist()})
                pair_vertices.append(trimesh.transform_points(meshes["wrist_holder"].vertices, t))
            points = np.concatenate(pair_vertices)
            low, high = points.min(0), points.max(0)
            for pose in pair_poses:
                t = np.asarray(pose["transform"])
                t[:3, 3] -= low
                pose["transform"] = t.tolist()
            subset = {"units": "mm", "container": {"inner_mm": (high-low+.01).tolist()}, "clearance_mm": .1, "items": [items["wrist_holder"]]}
            subset_layout = {"units": "mm", "placements": pair_poses}
            certificate = check_vertical_sequence(subset, subset_layout, time_limit=60)
            if not certificate["valid"]:
                print("independent path unresolved", delta, direction.tolist(), flush=True)
                continue
            for name, data in (("input", problem), ("layout", candidate), ("validation", validation), ("pair-input", subset), ("pair-layout", subset_layout), ("pair-motion", certificate), ("repair", {"candidate": delta, "original_removal_direction": direction.tolist(), "rotation": rotation.tolist(), "rotated_minimum": low.tolist()})):
                (output / f"{name}.json").write_text(json.dumps(data, indent=2))
            print("SUCCESS", delta, direction.tolist(), flush=True)
            return
    print("EXHAUSTED", clear_candidates, perf_counter()-started, flush=True)


if __name__ == "__main__":
    main()
