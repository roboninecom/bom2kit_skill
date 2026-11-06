"""Search all 26 SO101 robot printed pieces in a merged inner carton."""
from hashlib import sha256
import json
from pathlib import Path
import argparse
import numpy as np
import trimesh
from bom2kit.mesh_geometry import load_instance_mesh
from bom2kit.mesh_search import solve_mesh_kit


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def run(seconds=600):
    root = Path(__file__).resolve().parents[1]
    source = root / "packaging-inputs/so-arm-101/style/Black and white Robonine style/STL"
    out = root / "packaging-results/so-arm-101/regrouped"
    follower = source / "STL/SO-ARM101_Follower_Robo9.stl"
    leader = source / "printing_files/SO-ARM101_Leader_Robo9.3mf"
    names_f = ["rotation_pitch", "base_holder", "upper_arm", "base", "board_plate",
               "wrist_holder", "moving_jaw", "wrist_follower", "under_arm", "camera_mount",
               "side_holder", "wrist_roll_pitch"]
    names_l = ["upper_arm", "under_arm", "base_holder", "base", "wrist_holder",
               "side_holder", "rotation_pitch", "wrist_roll_pitch", "board_plate",
               "handle", "wrist_roll", "trigger"]
    entries = []
    for index, mesh in enumerate(trimesh.load(follower, force="mesh").split(only_watertight=False)):
        entries.append(("F_" + names_f[index], mesh, follower, {"component_index": index}))
    for index, name in enumerate(names_l):
        selector = f"build-{index+1}/leaf-{index+1}"
        data = load_instance_mesh(leader, selector)
        mesh = trimesh.Trimesh(data["vertices_mm"], data["triangles"], process=False)
        entries.append(("L_" + name, mesh, leader, {"instance_id": selector}))
    for color in ("black-logo_white-base", "white-logo_black-base"):
        path = source / "printing_files" / (color + ".3mf")
        data = load_instance_mesh(path, "build-1/leaf-1")
        mesh = trimesh.Trimesh(data["vertices_mm"], data["triangles"], process=False)
        entries.append((color, mesh, path, {"instance_id": "build-1/leaf-1"}))
    items, manifest = [], []
    for name, mesh, path, selector in entries:
        if not mesh.is_volume or np.any(mesh.area_faces <= 0):
            raise ValueError(f"Invalid source: {name}")
        target = out / "meshes" / (name + ".json")
        write(target, {"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist()})
        basis, extents = trimesh.bounds.oriented_bounds(mesh)
        items.append({"id": name, "quantity": 1,
                      "orientation_hint": basis[:3,:3].tolist(),
                      "mesh": {"path": str(target), "sha256": sha256(target.read_bytes()).hexdigest()}})
        manifest.append({"id": name, "source": str(path), "source_sha256": sha256(path.read_bytes()).hexdigest(),
                         "selector": selector, "name_mapping": "Inferred morphology; all source components retained once",
                         "obb_extents_mm": extents.tolist()})
    problem = {"units": "mm", "container": {"inner_mm": [265,243,72.2]}, "clearance_mm": .1,
               "items": items, "scope": "26 printed robot pieces only; electronics must be added before merged carton acceptance"}
    problem["height_assumption"] = "Merged carton external height75.2mm; 64mm top layer leaves0.8mm booklet allowance in140mm cavity. Bases have72.00004mm minimum OBB."
    write(out / "input.json", problem)
    write(out / "source-manifest.json", manifest)
    sizes = {entry["id"]: np.prod(entry["obb_extents_mm"]) for entry in manifest}
    ordered = sorted(items, key=lambda item: (not item["id"].endswith("_base"), -sizes[item["id"]]))
    result = solve_mesh_kit(problem, time_limit=seconds, beam_width=8, pitch_mm=2,
                            order=[item["id"] + "#1" for item in ordered], voxel_overlap_cells=500,
                            positions_per_rotation=16, checkpoint_dir=out,
                            progress=lambda state: print(json.dumps(state), flush=True))
    write(out / "result.json", result)
    print(result["status"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=600)
    run(parser.parse_args().seconds)
