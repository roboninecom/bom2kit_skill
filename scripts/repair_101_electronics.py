"""Try a local rigid repair around the camera packet in the SO101 experiment."""
import itertools
import json
from pathlib import Path
import numpy as np
import trimesh
from bom2kit.mesh_validation import validate_mesh_layout
from bom2kit.mesh_search import solve_mesh_kit

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / "packaging-results/so-arm-101/regrouped-complete"
    problem = json.loads((source / "input.json").read_text())
    layout = json.loads((source / "checkpoint.json").read_text())
    items = {i["id"]: i for i in problem["items"]}
    meshes = {}
    manager = trimesh.collision.CollisionManager()
    for pose in layout["placements"]:
        d = json.loads(Path(items[pose["item_id"]]["mesh"]["path"]).read_text())
        mesh = trimesh.Trimesh(d["vertices_mm"], d["triangles"], process=False)
        mesh.apply_transform(pose["transform"])
        meshes[pose["unit_id"]] = mesh
        manager.add_object(pose["unit_id"], mesh)
    camera = items["camera_protected_packet"]
    dims = np.array(camera["dimensions_mm"])
    cavity = np.array(problem["container"]["inner_mm"])
    candidates = []
    for axes in ((0,1,2), (0,2,1), (2,0,1)):
        rotation = np.eye(3)[list(axes)]
        if np.linalg.det(rotation) < 0:
            rotation[0] *= -1
        size = dims[list(axes)]
        spans = [sorted(set(np.arange(0, end, 20).tolist() + [float(end)])) for end in cavity-size]
        for xyz in itertools.product(*spans):
            transform = np.eye(4)
            transform[:3,:3] = rotation
            transform[:3,3] = np.array(xyz) + size/2
            mesh = trimesh.creation.box(dims, transform=transform)
            collision, names = manager.in_collision_single(mesh, return_names=True)
            if len(names) > 4:
                continue
            # AABB separation >= clearance is a sufficient clearance condition;
            # near but nonintersecting candidates receive independent validation.
            candidates.append((len(names), sum(meshes[n].volume for n in names), xyz, transform, names))
    candidates.sort(key=lambda c: (c[0], c[1]))
    print("camera_candidates", len(candidates), flush=True)
    tried = set()
    subset_managers = {}
    for candidate in candidates:
        _, _, xyz, transform, removed = candidate
        signature = tuple(sorted(removed))
        if signature in tried:
            continue
        if signature not in subset_managers:
            subset_manager = trimesh.collision.CollisionManager()
            for name, mesh in meshes.items():
                if name not in removed:
                    subset_manager.add_object(name, mesh)
            subset_managers[signature] = subset_manager
        candidate_mesh = trimesh.creation.box(dims, transform=transform)
        if subset_managers[signature].min_distance_single(candidate_mesh) < .1:
            continue
        seed = [p for p in layout["placements"] if p["unit_id"] not in removed]
        seed.append({"item_id": camera["id"], "unit_id": camera["id"] + "#1", "transform": transform.tolist()})
        selected = {p["item_id"] for p in seed}
        partial = {**problem, "items": [i for i in problem["items"] if i["id"] in selected]}
        if not validate_mesh_layout(partial, {"units": "mm", "placements": seed})["valid"]:
            continue
        tried.add(signature)
        out = ROOT / "packaging-results/so-arm-101" / f"repair-camera-{len(tried)}"
        out.mkdir(parents=True, exist_ok=True)
        (out / "input.json").write_text(json.dumps(problem, indent=2))
        (out / "repair.json").write_text(json.dumps({"removed_unit_ids": sorted(removed), "camera_corner_mm": xyz}, indent=2))
        print("repair", len(tried), sorted(removed), flush=True)
        result = solve_mesh_kit(problem, time_limit=150, beam_width=4, pitch_mm=2,
                               seed_placements=seed, checkpoint_dir=out,
                               progress=lambda v: print(json.dumps(v), flush=True))
        if result["validation"]["valid"] or len(tried) >= 3:
            print(result["status"], flush=True)
            return


if __name__ == "__main__":
    main()
