"""Place declared hardware envelopes around current printed lower-group meshes."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_search import solve_mesh_kit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--output", type=Path, default=ROOT / "packaging-results/so-arm-102/lower-hardware-search")
    parser.add_argument("--skip", nargs="*", default=[], help="Explicitly assign listed hardware IDs elsewhere")
    parser.add_argument("--seed-layout", type=Path, help="Reuse existing independently revalidated placements")
    parser.add_argument("--base", type=Path, default=ROOT / "packaging-results/so-arm-102/lower-30-with-psus")
    parser.add_argument("--catalogue", type=Path, default=ROOT / "packaging-inputs/benchmarks/purchased-assumptions/102-hardware-flexible.json")
    parser.add_argument("--small-first", action="store_true")
    args = parser.parse_args()
    source = args.base
    problem = json.loads((source / "input.json").read_text())
    seed = json.loads((source / "layout.json").read_text())["placements"]
    if args.seed_layout:
        seed = json.loads(args.seed_layout.read_text())["placements"]
    catalogue_path = args.catalogue
    catalogue = json.loads(catalogue_path.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    known = {item["id"] for item in problem["items"]}
    additions = []
    for item in catalogue["items"]:
        if item["id"] in known or item["id"] in args.skip or item["id"] == "clamp_closed_proxy" or item["id"].endswith("_protected_sleeve"):
            continue
        mesh = trimesh.creation.box(extents=item["dimensions_mm"])
        mesh.apply_translation(-mesh.bounds[0])
        path = args.output / f"{item['id']}.json"
        path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(),
                                    "triangles": mesh.faces.tolist(), "assumption_source": item}, indent=2))
        additions.append({**item, "mesh": {"path": str(path.resolve()), "sha256": sha256(path.read_bytes()).hexdigest()}})
    problem["items"] += additions
    problem["scope"] = "Lower group actual printed parts plus declared bearing and hardware proxies. Only manifest quantities are included; skipped catalogue items and unallocated servo quantities require separate packing evidence."
    problem["additional_hardware_assigned_elsewhere"] = args.skip
    problem["purchased_manifest_sha256"] = sha256(catalogue_path.read_bytes()).hexdigest()
    additions.sort(key=lambda item: item["dimensions_mm"][0] * item["dimensions_mm"][1] * item["dimensions_mm"][2], reverse=not args.small_first)
    seeded = {pose["unit_id"] for pose in seed}
    order = [pose["unit_id"] for pose in seed] + [uid for item in additions for n in range(item["quantity"])
                                                 if (uid := f"{item['id']}#{n + 1}") not in seeded]
    result = solve_mesh_kit(problem, time_limit=args.seconds, beam_width=4, pitch_mm=2,
                            positions_per_rotation=12, voxel_overlap_cells=100, order=order,
                            seed_placements=seed, checkpoint_dir=args.output,
                            progress=lambda record: print(record, flush=True))
    print(result["status"], len(result["placements"]), result["search"], flush=True)
    return 0 if result["validation"]["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
