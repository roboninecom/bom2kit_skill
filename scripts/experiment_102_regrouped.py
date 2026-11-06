"""Search merged 102 printed groups from previously prepared source manifests.

This experiment excludes electronics and cannot certify the complete kit.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_search import solve_mesh_kit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--beam-width", type=int, default=8)
    parser.add_argument("--pitch", type=float, default=2)
    parser.add_argument("--voxel-overlap-cells", type=int, default=0)
    parser.add_argument("--alternate-arms", action="store_true")
    parser.add_argument("--servo-strip", action="store_true",
                        help="Seed the independently checked servo pair in a far-edge strip")
    parser.add_argument("--seed-file", type=Path,
                        help="Resume an independently revalidated partial layout")
    parser.add_argument("--exclude-upper-arms", action="store_true",
                        help="Reserve the four upper arms for the independently validated top group")
    parser.add_argument("--output", type=Path, default=ROOT / "packaging-results/so-arm-102/merged-124-seeded")
    args = parser.parse_args()
    source = ROOT / "packaging-results/evidence-audit/box1-experiment"
    problem = json.loads((source / "problem-with-bearing-proxies.json").read_text())
    arms = json.loads((ROOT / "packaging-results/so-arm-102/current-box2-beam-alternating/problem.json").read_text())
    problem["items"] += arms["items"]
    if args.exclude_upper_arms:
        problem["items"] = [item for item in problem["items"] if item["id"] not in ("left", "right")]
    problem["container"]["inner_mm"] = [277, 243, 72]
    problem["clearance_mm"] = .1
    for item in problem["items"]:
        if item["id"] in ("left", "right"):
            item.pop("orientation_hint", None)
    problem["scope"] = "Exploratory merged BOX1+BOX2: 30 printed pieces and 2 bearing assumption envelopes. Electronics absent; not complete kit."
    if args.exclude_upper_arms:
        problem["scope"] = "Exploratory lower printed group: 26 printed pieces and 2 bearing assumption envelopes; four upper arms reserved in separate validated top group. Purchased electronics absent; not complete kit."
    seed_path = args.seed_file or source / "manual-reference-seed.json"
    seed = json.loads(seed_path.read_text())["placements"]
    if args.servo_strip:
        reference = ROOT / "packaging-results/so-arm-102/current-box2-beam-reference-seed/layout.json"
        for pose in json.loads(reference.read_text())["placements"]:
            if pose["item_id"] == "servo":
                pose["transform"][1][3] += 145
                seed.append(pose)
    priority = ["servo", "left", "right", "bottom", "RB9.01.062.012 Main frame (D6.1)", "RB9.01.062.075 Camera holder"]
    items = {item["id"]: item for item in problem["items"]}
    priority = [iid for iid in priority if iid in items]
    order = [f"{iid}#{n + 1}" for iid in priority + [iid for iid in items if iid not in priority]
             for n in range(items[iid]["quantity"])]
    if args.alternate_arms and not args.exclude_upper_arms:
        offset = order.index("left#1")
        order[offset:offset + 4] = ["left#1", "right#1", "left#2", "right#2"]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "seed.json").write_text(json.dumps(seed, indent=2))
    result = solve_mesh_kit(problem, time_limit=args.seconds, beam_width=args.beam_width,
                            pitch_mm=args.pitch, positions_per_rotation=8, order=order,
                            seed_placements=seed, checkpoint_dir=args.output,
                            voxel_overlap_cells=args.voxel_overlap_cells,
                            progress=lambda record: print(record, flush=True))
    print(result["status"], len(result["placements"]), result["search"], flush=True)
    return 0 if result["validation"]["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
