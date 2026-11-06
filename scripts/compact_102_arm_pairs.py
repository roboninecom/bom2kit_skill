"""Search rigid relative poses of the two validated current upper-arm pairs."""
from copy import deepcopy
import itertools
import json
from pathlib import Path
import numpy as np
import trimesh
from bom2kit.mesh_validation import validate_mesh_layout

root = Path(__file__).resolve().parents[1]
source = root / "packaging-results/so-arm-102/current-four-arm-top"
problem = json.loads((source / "input.json").read_text())
layout = json.loads((source / "layout.json").read_text())
items = {item["id"]: item for item in problem["items"]}
meshes = []
for pose in layout["placements"][:2]:
    data = json.loads(Path(items[pose["item_id"]]["mesh"]["path"]).read_text())
    mesh = trimesh.Trimesh(data["vertices_mm"], data["triangles"], process=False)
    mesh.apply_transform(pose["transform"])
    meshes.append(mesh)
pair = trimesh.util.concatenate(meshes)
fixed = trimesh.collision.CollisionManager()
fixed.add_object("fixed", pair)
moving = trimesh.collision.CollisionManager()
moving.add_object("moving", pair)
size = np.array([204, 140.8, 64.2])
found = None
checks = 0
for signs in itertools.product((1, -1), repeat=3):
    if np.prod(signs) < 0:
        continue
    rotation = np.diag(signs)
    vertices = pair.vertices @ rotation.T
    offset = -vertices.min(axis=0)
    for y, z, x in itertools.product(np.arange(59, 62.31, .3), np.arange(0, 8.11, .5), (0, .4, .8)):
        transform = np.eye(4)
        transform[:3, :3] = rotation
        transform[:3, 3] = offset + [x, y, z]
        if np.any(vertices.max(axis=0) + transform[:3, 3] > size + 1e-8):
            continue
        checks += 1
        moving.set_transform("moving", transform)
        if fixed.in_collision_other(moving) or fixed.min_distance_other(moving) < .1:
            continue
        poses = deepcopy(layout["placements"][:2])
        for pose in layout["placements"][:2]:
            new = deepcopy(pose)
            new["unit_id"] = new["unit_id"].replace("#1", "#2")
            new["transform"] = (transform @ np.array(pose["transform"])).tolist()
            poses.append(new)
        candidate_problem = deepcopy(problem)
        candidate_problem["container"]["inner_mm"] = size.tolist()
        candidate = {"units": "mm", "placements": poses}
        validation = validate_mesh_layout(candidate_problem, candidate)
        if validation["valid"]:
            found = candidate_problem, candidate, validation
            break
    if found:
        break
output = root / "packaging-results/so-arm-102/upper-arms-compact"
output.mkdir(exist_ok=True)
if found:
    for name, data in zip(("input", "layout", "validation"), found):
        (output / f"{name}.json").write_text(json.dumps(data, indent=2))
print(json.dumps({"found": found is not None, "checks": checks}), flush=True)
