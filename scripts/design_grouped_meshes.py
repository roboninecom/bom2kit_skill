"""Run independent pair discovery and original-geometry group packing."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bom2kit.mesh_groups import discover_pairs
from bom2kit.group_design import design_grouped_library
from bom2kit.mesh_envelope_design import design_mesh_envelopes
from bom2kit.bom import reconcile_bom
from bom2kit.nested_groups import extend_groups
from bom2kit.group_portfolio import group_configurations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bom", type=Path, help="Independent expected SKU counts, checked before and after packing")
    parser.add_argument("--pair-budget", type=float, default=60)
    parser.add_argument("--pair-seconds", type=float, default=8)
    parser.add_argument("--max-pairs", type=int, default=8)
    parser.add_argument("--cavity-proposals", action="store_true",
                        help="Experimental dense-part/hollow-part proposal queue in initial pair search")
    parser.add_argument("--cavity-budget", type=float, default=0,
                        help="Optional additional voxel-void discovery budget in seconds")
    parser.add_argument("--nesting-rounds", type=int, default=0,
                        help="Optional group/part or group/group extension rounds, each using the pair budget")
    parser.add_argument("--carton-budget", type=float, default=10)
    parser.add_argument("--improvement-budget", type=float, default=0,
                        help="Optional final in-run layer improvement budget; requires --bom")
    parser.add_argument("--group-configurations", type=int, default=4,
                        help="Maximum distinct grouping evaluations: greedy, leave-one-out neighbors, anchors and singles")
    args = parser.parse_args()
    if args.group_configurations < 1 or args.nesting_rounds < 0:
        parser.error("--group-configurations must be positive and --nesting-rounds nonnegative")
    if not math.isfinite(args.cavity_budget) or args.cavity_budget < 0:
        parser.error("--cavity-budget must be finite and nonnegative")
    if not math.isfinite(args.improvement_budget) or args.improvement_budget < 0:
        parser.error("--improvement-budget must be finite and nonnegative")
    if args.improvement_budget and not args.bom:
        parser.error("--improvement-budget requires --bom for original-part assembly replay")
    input_files, parsed = {}, {}
    for name,path in (("library",args.library),("policy",args.policy),("bom",args.bom)):
        if path:
            raw = path.read_bytes()
            input_files[name] = {"path":str(path.resolve()),"sha256":sha256(raw).hexdigest()}
            parsed[name] = json.loads(raw.decode("utf-8-sig"))
    library, policy, expected_bom = parsed["library"], parsed["policy"], parsed.get("bom")
    if expected_bom is not None and not reconcile_bom(expected_bom, library)["complete"]:
        raise ValueError("Source library does not cover the expected BOM")
    started = perf_counter()
    stage_timings = []
    args.output.mkdir(parents=True, exist_ok=True)
    status = args.output / "run.json"
    status.write_text(json.dumps({"status": "running"}))
    stage_started = perf_counter()
    baseline = design_mesh_envelopes(library, policy, time_limit=args.carton_budget)
    baseline["source_library_sha256"] = sha256(json.dumps(library,sort_keys=True).encode()).hexdigest()
    stage_timings.append({"stage":"baseline","seconds":perf_counter()-stage_started})
    (args.output / "baseline.json").write_text(json.dumps(baseline, allow_nan=False))
    stage_started = perf_counter()
    portfolio = discover_pairs(library, args.output / "pair-candidates",
                               clearance_mm=max(policy["clearance_mm"], 2 * policy["item_padding_mm"]),
                               time_limit=args.pair_budget, pair_seconds=args.pair_seconds, max_pairs=args.max_pairs,
                               cavity_proposals=args.cavity_proposals)
    stage_timings.append({"stage":"pair_discovery","seconds":perf_counter()-stage_started})
    if args.cavity_budget:
        from bom2kit.cavity_groups import discover_cavities
        stage_started = perf_counter()
        cavities = discover_cavities(library,args.output/"cavity-candidates",
                                     clearance_mm=max(policy["clearance_mm"],2*policy["item_padding_mm"]),
                                     time_limit=args.cavity_budget)
        portfolio["alternatives"].extend(cavities["alternatives"])
        stage_timings.append({"stage":"cavity_discovery","seconds":perf_counter()-stage_started})
    for round_index in range(args.nesting_rounds):
        stage_started = perf_counter()
        extensions = extend_groups(library,portfolio,args.output/f"nested-{round_index}",
                                   time_limit=args.pair_budget,pair_seconds=args.pair_seconds,max_pairs=args.max_pairs)
        stage_timings.append({"stage":f"nesting_{round_index}","seconds":perf_counter()-stage_started})
        if not extensions["alternatives"]:
            break
        portfolio = {**portfolio,"alternatives":portfolio["alternatives"]+extensions["alternatives"]}
    if args.cavity_budget and portfolio["alternatives"]:
        stage_started = perf_counter()
        extensions = extend_groups(library,portfolio,args.output/"nested-cavities",
                                   time_limit=args.cavity_budget,max_pairs=args.max_pairs,cavities=True)
        portfolio["alternatives"].extend(extensions["alternatives"])
        stage_timings.append({"stage":"cavity_extension","seconds":perf_counter()-stage_started})
    choices = []
    best_result = None
    if baseline["status"] == "validated_mesh_envelope_baseline":
        box = baseline["envelope_design"]["candidate"]
        choices.append((box["volume_mm3"], "baseline.json", box["external_mm"]))
        best_result = baseline
    configurations = group_configurations(library,portfolio["alternatives"],args.group_configurations)
    evaluations = []
    for index, alternatives in enumerate(configurations[:args.group_configurations]):
        if not alternatives:
            continue
        directory = f"packing-{index}"
        stage_started = perf_counter()
        result = design_grouped_library(library, {**portfolio, "alternatives": alternatives}, policy,
                                       args.output / directory, time_limit=args.carton_budget,
                                       incumbent_volume_mm3=min(choice[0] for choice in choices) if choices else None,
                                       incumbent_result=best_result)
        stage_timings.append({"stage":directory,"seconds":perf_counter()-stage_started})
        record = {"directory": directory, "status": result["status"],
                  "members": [alternative["members"] for alternative in alternatives]}
        if result["status"] == "validated_grouped_geometry":
            box = result["envelope_candidate"]["envelope_design"]["candidate"]
            choices.append((box["volume_mm3"], directory + "/result.json", box["external_mm"]))
            best_result = result
            record["external_volume_l"] = box["volume_mm3"] / 1e6
        evaluations.append(record)
    if args.improvement_budget and best_result:
        from bom2kit.layer_improvement import improve_generated_layers
        from bom2kit.repacking import apply_layer_candidate
        original = best_result.get("envelope_candidate",best_result)["envelope_design"]["candidate"]
        if original["layout"].get("layers"):
            stage_started = perf_counter()
            improvement = improve_generated_layers(original,time_limit=args.improvement_budget,
                                                   increment=policy["carton"].get("dimension_increment_mm",1),
                                                   max_external_mm=policy["carton"].get("max_external_mm"))
            stage_timings.append({"stage":"layer_improvement_search","seconds":perf_counter()-stage_started})
            (args.output/"layer-improvement.json").write_text(json.dumps(improvement,allow_nan=False))
            if improvement["candidate"]["volume_mm3"] < original["volume_mm3"]:
                stage_started = perf_counter()
                validated = apply_layer_candidate(best_result,improvement["candidate"],expected_bom)
                stage_timings.append({"stage":"layer_improvement_validation","seconds":perf_counter()-stage_started})
                (args.output/"improved-result.json").write_text(json.dumps(validated["result"],allow_nan=False))
                (args.output/"assembly-plan.json").write_text(json.dumps(validated["assembly_plan"],allow_nan=False))
                box = improvement["candidate"]
                choices.append((box["volume_mm3"],"improved-result.json",box["external_mm"]))
    selected = min(choices) if choices else None
    summary = {"status": "validated_geometry_candidate" if selected else "no_verified_candidate",
               "selected_result": selected[1] if selected else None,
               "pair_alternatives": len(portfolio["alternatives"]),
               "group_evaluations": evaluations,
               "stage_timings":stage_timings,
               "timing_scope":"Wall time from prepared library; each stage includes its geometry checks. Source import is excluded.",
               "input_files":input_files,
               "parameters":{key:value for key,value in vars(args).items() if not isinstance(value,Path)},
               "total_seconds": perf_counter() - started,
               "scope": library.get("scope", "Declared library only")}
    if selected:
        summary["external_mm"] = selected[2]
        if expected_bom is not None:
            selected_result = json.loads((args.output / selected[1]).read_text())
            coverage = reconcile_bom(expected_bom, selected_result["input"])
            (args.output / "coverage.json").write_text(json.dumps(coverage, indent=2))
            summary["declared_bom_complete"] = coverage["complete"]
            if not coverage["complete"]:
                summary["status"] = "bom_validation_failed"
    status.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))
    return 0 if summary["status"] == "validated_geometry_candidate" else 1


if __name__ == "__main__":
    raise SystemExit(main())
