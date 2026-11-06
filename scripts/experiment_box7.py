"""Conservative envelope experiment for all 31 declared SO-ARM102 BOX7 parts.

No scaling, envelope shrinking, or cavity nesting is used. This experiment does
not establish assembly identity, support, insertion paths, or production release.
"""

import argparse
from hashlib import sha256
from itertools import permutations
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_validation import validate_mesh_layout


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def prepare(output, aruco_3mf=False):
    stls = ROOT / "packaging-inputs/so-arm-102/repository-main/models/stl"
    style = ROOT / "packaging-inputs/so-arm-101/style/Black and white Robonine style"
    definitions = [("wrist_holder", "090 Wrist", 2), ("gear_rack", "030 Gear", 2),
                   ("gear", "040 Gear", 1), ("base_washer", "030 Base washer", 2),
                   ("gripper_washer", "050 Washer", 2), ("leader_washer", "SO102 Washer", 1),
                   ("nail", "100 Nail", 2), ("cable_snap", "130 Cable", 2)]
    entries, preprocessing = [], {}
    for item_id, token, count in definitions:
        path = next(p for p in stls.rglob("*") if p.is_file() and token in p.name)
        mesh = trimesh.load_mesh(path)
        preprocessing[item_id] = {"loaded_vertices_sha256": sha256(mesh.vertices.tobytes()).hexdigest(),
                                  "removed_face_indices_in_loaded_mesh": []}
        process = "STL vertices welded by trimesh default loader; no scaling"
        if not mesh.is_volume:
            components = list(mesh.split(only_watertight=False))
            bad = [component for component in components if not component.is_volume]
            if any(float(component.area) != 0 for component in bad):
                raise ValueError(f"Non-volume source with nonzero-area invalid component: {path}")
            preprocessing[item_id]["removed_face_indices_in_loaded_mesh"] = np.where(mesh.area_faces == 0)[0].tolist()
            mesh = trimesh.util.concatenate([component for component in components if component.is_volume])
            process += "; excluded isolated exactly-zero-area triangle component, preserved all solid geometry"
        entries.append((item_id, count, mesh, path, process))
    figures = next(style.rglob("cube_cylinder_nut_cone.STL"))
    components = list(trimesh.load_mesh(figures).split())
    # Identify by geometry and volume, not STL component ordinal.
    nut = next(m for m in components if m.extents[2] < 20)
    tall = sorted([m for m in components if m.extents[2] >= 20], key=lambda m: m.volume)
    for item_id, count, mesh in [("hex_nut_figure", 3, nut), ("cone", 1, tall[0]),
                                 ("cylinder", 3, tall[1]), ("cube", 3, tall[2])]:
        entries.append((item_id, count, mesh, figures, "Selected disconnected watertight figure by extents and volume; source vertices unchanged"))
    if aruco_3mf:
        from bom2kit.mesh_geometry import load_instance_mesh
        aruco = next(style.rglob("aruco_cube&tags_ids_0-5-2.3mf"))
        geometry = load_instance_mesh(aruco, "build-1/leaf-1")
        aruco_mesh = trimesh.Trimesh(vertices=geometry["vertices_mm"], faces=geometry["triangles"], process=False)
        aruco_origin = "Current printing_files -2 3MF, build-1/leaf-1; selected one of the alternatives allowed by SO102_Printing_and_Packing.pdf page 6"
    else:
        aruco = next(style.rglob("aruco_cube&tags_ids 0-5.STL"))
        aruco_mesh = trimesh.load_mesh(aruco)
        aruco_origin = "Deprecated STL source"
    components = list(aruco_mesh.split())
    core = next(m for m in components if min(m.extents) > 30)
    entries.append(("ArUco_core", 1, core, aruco, aruco_origin + "; selected disconnected core, no alteration"))
    panels = sorted([m for m in components if m.extents[0] > 39 and m.extents[1] > 39 and m.extents[2] < 5],
                    key=lambda m: tuple(m.bounds[0]))
    for index, panel in enumerate(panels):
        relief = [m for m in components if m.extents[2] < .1 and
                  np.all(m.bounds[0][:2] >= panel.bounds[0][:2] - 1e-5) and
                  np.all(m.bounds[1][:2] <= panel.bounds[1][:2] + 1e-5)]
        combined = trimesh.util.concatenate([panel, *relief])
        entries.append((f"ArUco_panel_{index}", 1, combined, aruco,
                        aruco_origin + "; panel plus its original marker relief retained as one unit"))
    items, envelopes, manifest = [], {}, []
    for item_id, count, mesh, source, process in entries:
        if not mesh.is_volume or np.any(mesh.area_faces <= 0):
            raise ValueError(f"Prepared mesh invalid: {item_id}")
        geometry = {"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist()}
        path = output / "meshes" / f"{item_id}.json"
        write(path, geometry)
        digest = sha256(path.read_bytes()).hexdigest()
        items.append({"id": item_id, "quantity": count, "mesh": {"path": str(path.resolve()), "sha256": digest}})
        envelopes[item_id] = {"low": mesh.bounds[0].tolist(), "size": mesh.extents.tolist()}
        manifest.append({"id": item_id, "quantity": count, "source": str(source),
                         "source_sha256": sha256(source.read_bytes()).hexdigest(), "processing": process,
                         "mesh_sha256": digest, "aabb_mm": mesh.extents.tolist(), "solid_volume_mm3": float(mesh.volume),
                         "retained_vertices_sha256": sha256(mesh.vertices.tobytes()).hexdigest(),
                         "retained_coordinates_file": str(path.resolve()), **preprocessing.get(item_id, {})})
    if sum(item["quantity"] for item in items) != 31 or len(panels) != 6:
        raise ValueError("BOX7 manifest is incomplete")
    return items, envelopes, manifest


def pack(units, dimensions, seconds=30):
    """Randomized maximal-empty-cuboid packing of unchanged padded envelopes."""
    started = time.perf_counter()
    rng = random.Random(1027)
    attempt, best_count = 0, 0
    best = None
    while time.perf_counter() - started < seconds:
        attempt += 1
        order = sorted(units, key=lambda u: -np.prod(u["size"]) * rng.uniform(.65, 1.4))
        free = [(np.zeros(3), np.array(dimensions, dtype=float))]
        placed = []
        for unit in order:
            options = []
            for number, (low, extent) in enumerate(free):
                for axes in permutations(range(3)):
                    size = np.array(unit["size"])[list(axes)] + .11
                    if np.all(size <= extent + 1e-8):
                        residual = extent - size
                        # Vary scoring to escape a single greedy layout family.
                        score = (float(np.min(residual)), float(np.prod(extent) - np.prod(size)), low[2]) if attempt % 2 else (low[2], float(np.prod(extent) - np.prod(size)), float(np.min(residual)))
                        options.append((score, number, axes, size))
            if not options:
                break
            options.sort(key=lambda value: value[0])
            _, chosen, axes, size = options[rng.randrange(min(len(options), 1 if attempt % 3 else 3))]
            position = free[chosen][0].copy()
            placed.append({**unit, "position": position, "axes": axes, "padded": size})
            high = position + size
            replacement = []
            for low, extent in free:
                end = low + extent
                if np.any(position >= end - 1e-8) or np.any(high <= low + 1e-8):
                    replacement.append((low, extent))
                    continue
                for axis in range(3):
                    if position[axis] > low[axis] + 1e-8:
                        remaining = extent.copy(); remaining[axis] = position[axis] - low[axis]
                        replacement.append((low.copy(), remaining))
                    if high[axis] < end[axis] - 1e-8:
                        new_low = low.copy(); new_low[axis] = high[axis]
                        remaining = extent.copy(); remaining[axis] = end[axis] - high[axis]
                        replacement.append((new_low, remaining))
            # Prune contained cuboids; retained cuboids may overlap one another,
            # but each is empty relative to every already placed envelope.
            free = []
            for i, (low, extent) in enumerate(replacement):
                if any(j != i and np.all(low >= other_low - 1e-8) and
                       np.all(low + extent <= other_low + other_extent + 1e-8) and
                       (j < i or np.any(extent < other_extent - 1e-8))
                       for j, (other_low, other_extent) in enumerate(replacement)):
                    continue
                free.append((low, extent))
        if len(placed) > best_count:
            best_count, best = len(placed), placed
        if len(placed) == len(units):
            return placed, {"attempts": attempt, "elapsed_seconds": time.perf_counter() - started, "placed_groups": len(placed)}
    return None, {"attempts": attempt, "elapsed_seconds": time.perf_counter() - started, "best_partial_groups": best_count,
                  "expected_groups": len(units), "status": "search_exhausted_not_infeasibility_proof"}


def run(output, seconds=30, nominal=False, nest_wrists=False, pair_max_length=115, aruco_3mf=False, bag_height=None):
    started = time.perf_counter()
    items, envelopes, manifest = prepare(output, aruco_3mf)
    dimensions = [196, 78, 64] if nominal else [193, 75, 61]
    if bag_height is not None:
        if nominal or not np.isfinite(bag_height) or bag_height <= 0:
            raise ValueError("A positive finite bag height requires the conservative footprint")
        dimensions = [193, 75, bag_height]
    units = [{"item_id": item["id"], "unit_id": f"{item['id']}#{i + 1}", **envelopes[item["id"]]}
             for item in items for i in range(item["quantity"])]
    problem = {"units": "mm", "container": {"inner_mm": dimensions}, "items": items, "clearance_mm": .1,
               "assumption": "Nominal external box envelope treated as cavity; this is not the confirmed interior" if nominal else "User-confirmed 196 x 78 x 64 mm external box with 1.5 mm walls; interior 193 x 75 x 61 mm",
               "dimension_provenance": {"kind": "user_confirmed", "external_mm": [196, 78, 64], "wall_mm": 1.5,
                                        "inner_mm": [193, 75, 61]},
               "limitations": ["ArUco -2 3MF chosen from the alternatives allowed by SO102_Printing_and_Packing.pdf page 6; packed unassembled" if aruco_3mf else "Source ArUco geometry is in Deprecated; current identity requires confirmation",
                               "STL units are assumed mm from engineering context", "Static mesh fit only; no physical support or insertion qualification"]}
    write(output / "input.json", problem)
    if bag_height is not None:
        problem["assumption"] = "Original rigid BOX7 carton replaced by an upper-layer bag; declared cavity height is a design allocation, not the original carton interior."
        problem["dimension_provenance"] = {"kind": "explicit_bag_allocation", "inner_mm": dimensions, "original_external_mm": [196, 78, 64]}
        write(output / "input.json", problem)
    write(output / "source-manifest.json", manifest)
    pair = None
    if nest_wrists:
        from bom2kit.mesh_packing import solve_mesh_pair
        source = output / "meshes/wrist_holder.json"
        geometry = json.loads(source.read_text())
        pre_transform = np.eye(4)
        pre_transform[:3, :3] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
        geometry["vertices_mm"] = (np.array(geometry["vertices_mm"]) @ pre_transform[:3, :3].T).tolist()
        rotated = output / "meshes/wrist_rotated.json"
        write(rotated, geometry)
        pair_problem = {"units": "mm", "container": {"inner_mm": [pair_max_length, dimensions[1], dimensions[2]]},
                        "clearance_mm": .1, "items": [{"id": "wrist_holder", "quantity": 2,
                        "mesh": {"path": str(rotated.resolve()), "sha256": sha256(rotated.read_bytes()).hexdigest()}}]}
        pair = solve_mesh_pair(pair_problem, time_limit=seconds, pitch_mm=1.5, candidates_per_rotation=35)
        write(output / "wrist-pair-input.json", pair_problem)
        write(output / "wrist-pair-layout.json", pair)
        if pair["status"] != "validated_static_layout":
            return {"status": "wrist_pair_search_exhausted", "search": pair["search"]}
        units = [unit for unit in units if unit["item_id"] != "wrist_holder"]
        units.append({"item_id": "wrist_pair", "unit_id": "wrist_pair#1", "low": [0, 0, 0], "size": pair["envelope_mm"]})
    positions, stats = pack(units, dimensions, seconds)
    write(output / "search.json", stats)
    if positions is None:
        return stats
    placements = []
    for placed in positions:
        rotation = np.eye(3)[list(placed["axes"])]
        if np.linalg.det(rotation) < 0:
            rotation[0] *= -1
        original_low = np.array(placed["low"])
        original_high = original_low + placed["size"]
        corners = np.array([[x,y,z] for x in (original_low[0],original_high[0]) for y in (original_low[1],original_high[1]) for z in (original_low[2],original_high[2])])
        rotated_low = (corners @ rotation.T).min(axis=0)
        transform = np.eye(4); transform[:3,:3] = rotation
        transform[:3,3] = placed["position"] + .055 - rotated_low
        if placed["item_id"] == "wrist_pair":
            for part in pair["placements"]:
                placements.append({"item_id": part["item_id"], "unit_id": part["unit_id"],
                                   "transform": (transform @ np.array(part["transform"]) @ pre_transform).tolist()})
        else:
            placements.append({"item_id": placed["item_id"], "unit_id": placed["unit_id"], "transform": transform.tolist()})
    layout = {"units": "mm", "placements": placements}
    write(output / "layout.json", layout)
    validation = validate_mesh_layout(problem, layout)
    write(output / "validation.json", validation)
    result = {**stats, "valid": validation["valid"], "errors": validation["errors"], "scope": "Static mesh only",
              "placed_units": validation["placed_units"], "expected_units": validation["expected_units"],
              "cavity_mm": dimensions, "pair_clearance_mm": .1,
              "total_elapsed_seconds": time.perf_counter() - started,
              "assumption": problem["assumption"], "production_validated": False}
    if pair:
        result["wrist_pair_envelope_mm"] = pair["envelope_mm"]
        result["wrist_pair_seconds"] = pair["search"]["total_elapsed_seconds_including_validation"]
    write(output / "result.json", result)
    return result


def export_101_subset(source, output):
    """Reuse unchanged figure poses; independently validate all 17 expected units."""
    source, output = Path(source), Path(output)
    original_problem = json.loads((source / "input.json").read_text())
    original_layout = json.loads((source / "layout.json").read_text())
    figures = {"cube": 3, "cylinder": 3, "hex_nut_figure": 3, "cone": 1, "ArUco_core": 1,
               **{f"ArUco_panel_{index}": 1 for index in range(6)}}
    items = [item for item in original_problem["items"] if item["id"] in figures]
    if {item["id"]: item.get("quantity", 1) for item in items} != figures:
        raise ValueError("The 17-piece figure manifest is incomplete or has changed")
    for item in items:
        original_path = Path(item["mesh"]["path"])
        destination = output / "meshes" / original_path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        original_bytes = original_path.read_bytes()
        if sha256(original_bytes).hexdigest() != item["mesh"]["sha256"]:
            raise ValueError("Source certificate mesh hash changed")
        destination.write_bytes(original_bytes)
        item["mesh"]["path"] = str(destination.resolve())
    problem = {**original_problem, "items": items, "model": "SO-ARM101 BOX7",
               "pose_provenance": "Unchanged 17-figure subset of validated 102 BOX7 poses, independently revalidated",
               "limitations": original_problem["limitations"] +
                    ["Figure geometry is from 101 style assets; exact selected ArUco variant and hashes are recorded in source-manifest.json"]}
    layout = {"units": "mm", "placements": [p for p in original_layout["placements"] if p["item_id"] in figures]}
    manifest = [record for record in json.loads((source / "source-manifest.json").read_text()) if record["id"] in figures]
    for record in manifest:
        record["retained_coordinates_file"] = next(item["mesh"]["path"] for item in items if item["id"] == record["id"])
    validation = validate_mesh_layout(problem, layout)
    write(output / "input.json", problem)
    write(output / "layout.json", layout)
    write(output / "validation.json", validation)
    write(output / "source-manifest.json", manifest)
    result = {"valid": validation["valid"], "errors": validation["errors"],
              "placed_units": validation["placed_units"], "expected_units": validation["expected_units"],
              "cavity_mm": problem["container"]["inner_mm"], "pair_clearance_mm": problem["clearance_mm"],
              "scope": "Static mesh subset reuse only", "production_validated": False,
              "dimension_provenance": problem.get("dimension_provenance"), "assumption": problem["assumption"],
              "pose_source_input_sha256": sha256((source / "input.json").read_bytes()).hexdigest(),
              "pose_source_layout_sha256": sha256((source / "layout.json").read_bytes()).hexdigest()}
    write(output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--nominal", action="store_true")
    parser.add_argument("--nest-wrists", action="store_true")
    parser.add_argument("--pair-max-length", type=float, default=115)
    parser.add_argument("--export-101-from", type=Path)
    parser.add_argument("--aruco-3mf", action="store_true")
    parser.add_argument("--bag-height", type=float, help="Explicit alternative bag allocation height; retains193x75mm footprint")
    parser.add_argument("--output", type=Path, default=ROOT / "packaging-results/box7-experiment")
    args = parser.parse_args()
    if args.export_101_from:
        result = export_101_subset(args.export_101_from, args.output)
    else:
        result = run(args.output, args.seconds, args.nominal, args.nest_wrists, args.pair_max_length, args.aruco_3mf, args.bag_height)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result.get("valid") else 1)
