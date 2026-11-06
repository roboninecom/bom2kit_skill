"""Run independent pair discovery and original-geometry group packing."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bom2kit.mesh_groups import discover_pairs
from bom2kit.group_design import design_grouped_library
from bom2kit.mesh_envelope_design import design_mesh_envelopes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pair-budget", type=float, default=60)
    parser.add_argument("--pair-seconds", type=float, default=8)
    parser.add_argument("--max-pairs", type=int, default=8)
    parser.add_argument("--carton-budget", type=float, default=10)
    parser.add_argument("--group-configurations", type=int, default=4,
                        help="Maximum complete carton evaluations: all alternatives, then individual alternatives")
    args = parser.parse_args()
    if args.group_configurations < 1:
        parser.error("--group-configurations must be positive")
    library = json.loads(args.library.read_text(encoding="utf-8-sig"))
    policy = json.loads(args.policy.read_text(encoding="utf-8-sig"))
    started = perf_counter()
    args.output.mkdir(parents=True, exist_ok=True)
    status = args.output / "run.json"
    status.write_text(json.dumps({"status": "running"}))
    baseline = design_mesh_envelopes(library, policy, time_limit=args.carton_budget)
    (args.output / "baseline.json").write_text(json.dumps(baseline, allow_nan=False))
    portfolio = discover_pairs(library, args.output / "pair-candidates",
                               clearance_mm=max(policy["clearance_mm"], 2 * policy["item_padding_mm"]),
                               time_limit=args.pair_budget, pair_seconds=args.pair_seconds, max_pairs=args.max_pairs)
    choices = []
    if baseline["status"] == "validated_mesh_envelope_baseline":
        box = baseline["envelope_design"]["candidate"]
        choices.append((box["volume_mm3"], "baseline.json", box["external_mm"]))
    configurations = [portfolio["alternatives"]]
    if len(portfolio["alternatives"]) > 1:
        configurations += [[alternative] for alternative in portfolio["alternatives"]]
    evaluations = []
    for index, alternatives in enumerate(configurations[:args.group_configurations]):
        if not alternatives:
            continue
        directory = f"packing-{index}"
        result = design_grouped_library(library, {**portfolio, "alternatives": alternatives}, policy,
                                       args.output / directory, time_limit=args.carton_budget)
        record = {"directory": directory, "status": result["status"],
                  "members": [alternative["members"] for alternative in alternatives]}
        if result["status"] == "validated_grouped_geometry":
            box = result["envelope_candidate"]["envelope_design"]["candidate"]
            choices.append((box["volume_mm3"], directory + "/result.json", box["external_mm"]))
            record["external_volume_l"] = box["volume_mm3"] / 1e6
        evaluations.append(record)
    selected = min(choices) if choices else None
    summary = {"status": "validated_geometry_candidate" if selected else "no_verified_candidate",
               "selected_result": selected[1] if selected else None,
               "pair_alternatives": len(portfolio["alternatives"]),
               "group_evaluations": evaluations,
               "total_seconds": perf_counter() - started,
               "scope": library.get("scope", "Declared library only")}
    if selected:
        summary["external_mm"] = selected[2]
    status.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))
    return 0 if selected else 1


if __name__ == "__main__":
    raise SystemExit(main())
