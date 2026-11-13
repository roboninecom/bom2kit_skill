"""Search practical semantic packing concepts and independently replay the frontier."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from bom2kit.concept_planner import design_concepts
from bom2kit.report import fingerprint


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("library", "policy", "bom"):
        p.add_argument(name, type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cache", type=Path)
    p.add_argument("--annotations", type=Path)
    p.add_argument("--time-limit", type=float, default=180.)
    p.add_argument("--wall-limit", type=float, default=900.)
    p.add_argument("--beam-width", type=int, default=12)
    p.add_argument("--cartons", type=int, nargs="+", default=[3, 4, 5, 6, 7])
    p.add_argument("--types", type=int, nargs="+", default=[3, 4, 7])
    p.add_argument("--motifs", nargs="+", default=["rows"])
    p.add_argument("--grouping", nargs="+", default=["type"])
    p.add_argument("--placement-style",choices=['zones','cohesive','portfolio'],default='cohesive')
    p.add_argument("--max-replays", type=int, default=6)
    p.add_argument("--hand-border", type=float, default=7.2)
    p.add_argument("--access-lane", type=float, default=6.4)
    p.add_argument("--finger-radius", type=float, default=4.)
    p.add_argument("--repair-budget",type=float,default=60.)
    p.add_argument("--refinement-budget",type=float,default=45.)
    p.add_argument("--surface-budget",type=float,default=0.)
    p.add_argument("--preserve-contact-faces",action='store_true',help='Keep different stable support faces even when bounding dimensions match')
    p.add_argument('--volumetric-catalog', type=Path, help='Source-bound 3D motif proposals; full replay remains mandatory')
    p.add_argument('--volumetric-refinement-budget', type=float, default=0., help='Try catalog motifs inside generated row-based carton architectures')
    p.add_argument("--minimum-sheet-side",type=float,default=10.,help='Declared minimum manually handled contact-sheet width/depth, mm')
    p.add_argument('--irregular-solver',type=Path)
    p.add_argument('--irregular-budget',type=float,default=0.)
    p.add_argument('--assignment-budget',type=float,default=45.,help='Regenerate only moved/swapped semantic groups and retile the complete carton block')
    p.add_argument("--_supervised", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args()
    if not a._supervised:
        import os
        import subprocess
        import math
        if not math.isfinite(a.wall_limit) or a.wall_limit <= 0:
            raise ValueError("Positive finite wall limit required")
        started = perf_counter()
        process = subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve()), *sys.argv[1:], "--_supervised"],
                                   stdin=subprocess.DEVNULL, start_new_session=os.name != "nt",
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            raise SystemExit(process.wait(timeout=a.wall_limit))
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
            else:
                import signal
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(); a.output.mkdir(parents=True, exist_ok=True)
            (a.output/"wall-limit.json").write_text(json.dumps({"status": "wall_limit_reached", "seconds": perf_counter()-started,
                "note": "Partial trials require independent replay; timeout is not infeasibility."}, indent=2))
            raise SystemExit(124)
    started = perf_counter(); a.output.mkdir(parents=True, exist_ok=True)
    values = {name: json.loads(getattr(a, name).read_bytes()) for name in ("library", "policy", "bom")}
    files = {name: sha256(getattr(a, name).read_bytes()).hexdigest() for name in values}
    if a.annotations:
        files['annotations']=sha256(a.annotations.read_bytes()).hexdigest()
    if a.irregular_solver:files['irregular_solver']=sha256(a.irregular_solver.read_bytes()).hexdigest()
    if a.volumetric_catalog:files['volumetric_catalog']=sha256(a.volumetric_catalog.read_bytes()).hexdigest()
    root = Path(__file__).resolve().parents[1]
    def hashes():
        return {str(f.relative_to(root)): sha256(f.read_bytes()).hexdigest() for f in [*sorted((root/"src/bom2kit").glob("*.py")), Path(__file__).resolve()]}
    before = hashes(); counter = 0; proposal_counter=0
    def save_proposal(proposal):
        from copy import deepcopy
        nonlocal proposal_counter
        proposal_counter+=1;compact=deepcopy(proposal)
        for leaf in compact['tiled']['leaves']:
            module=compact['modules'][leaf['module']]
            module['patterns']=[module['patterns'][leaf['pattern']]];leaf['pattern']=0
        (a.output/f'proposal-{proposal_counter:02}.json').write_text(json.dumps(compact,indent=2),encoding='utf8')
    def progress(record):
        brief={k:v for k,v in record.items() if k not in ('access','support','organization','original_rejection','surface_refinement','assignment_refinement','irregular_refinement')}
        for stage in ('assignment_refinement','irregular_refinement'):
            if stage in record:brief[stage+'_seconds']=record[stage]['seconds']
        if 'surface_refinement' in record:
            brief['surface_refinement_seconds']=record['surface_refinement']['seconds']
        if 'support' in record:brief['support_errors']=record['support'].get('errors',[])
        if 'access' in record:brief['access_failures']=record['access'].get('failures',[])
        print(json.dumps(brief),flush=True)
    def save_trial(result, record):
        nonlocal counter
        counter += 1; directory = a.output/f"trial-{counter:02}"; directory.mkdir(exist_ok=True)
        (directory/"result.json").write_text(json.dumps(result, indent=2), encoding="utf8")
        (directory/"record.json").write_text(json.dumps(record, indent=2), encoding="utf8")
    run = design_concepts(**values, cache=a.cache,
                          annotations=json.loads(a.annotations.read_bytes()) if a.annotations else None,
                          seconds=a.time_limit, beam_width=a.beam_width, carton_counts=a.cartons, type_caps=a.types,
                          motif_modes=a.motifs, grouping_modes=a.grouping, max_replays=a.max_replays,
                          hand_border=a.hand_border, finger_radius=a.finger_radius,
                          access_lane=a.access_lane,
                          placement_style=a.placement_style,
                          repair_budget=a.repair_budget,
                          refinement_budget=a.refinement_budget,
                          surface_budget=a.surface_budget,
                          preserve_contact_faces=a.preserve_contact_faces,
                          minimum_sheet_side=a.minimum_sheet_side,
                          irregular_executable=a.irregular_solver,irregular_budget=a.irregular_budget,
                          assignment_budget=a.assignment_budget,
                          volumetric_catalog=json.loads(a.volumetric_catalog.read_bytes()) if a.volumetric_catalog else None,
                          volumetric_refinement_budget=a.volumetric_refinement_budget,
                          progress=progress, callback=save_trial,proposal_callback=save_proposal)
    results = run.pop("results"); plans = run.pop("assembly_plans"); properties = run.pop("properties")
    (a.output/"part-properties.json").write_text(json.dumps(properties, indent=2), encoding="utf8")
    run["input_files_sha256"] = files
    run["engine_provenance"] = {"initial_sha256": before, "unchanged_during_run": before == hashes()}
    run["parameters"] = {k: str(v) if isinstance(v, Path) else v for k, v in vars(a).items()}
    run["frontier"] = []
    for index, (result, plan) in enumerate(zip(results, plans, strict=True), 1):
        if plan["result_fingerprint"] != fingerprint(result):
            raise ValueError("Assembly plan no longer matches result")
        directory = a.output/f"frontier-{index:02}"; directory.mkdir(exist_ok=True)
        (directory/"result.json").write_text(json.dumps(result, indent=2), encoding="utf8")
        (directory/"assembly-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf8")
        run["frontier"].append({"path": str(directory), **result["practical"]["metrics"], "organization": result["concept"]["organization"]})
    run["seconds"] = perf_counter()-started
    (a.output/"run.json").write_text(json.dumps(run, indent=2), encoding="utf8")
    print(json.dumps({k: run[k] for k in ("status", "seconds", "frontier")}), flush=True)


if __name__ == "__main__":
    main()
