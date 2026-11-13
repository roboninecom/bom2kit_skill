"""Generate regular support-checked packaging, retaining operational tradeoffs."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


def supervise(arguments,output,seconds):
    """Hard wall-clock stop for this invocation and its owned child processes."""
    import math
    import os
    import subprocess
    from time import perf_counter
    if not math.isfinite(seconds) or seconds<=0:raise ValueError('Positive finite wall limit required')
    started=perf_counter()
    child=subprocess.Popen([sys.executable,'-u',str(Path(__file__).resolve()),*arguments,'--_supervised'],
                           stdin=subprocess.DEVNULL,stdout=sys.stdout,stderr=sys.stderr,
                           start_new_session=os.name!='nt',
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:return child.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,check=False)
        else:
            import signal
            os.killpg(child.pid,signal.SIGKILL)
        child.wait()
        output.mkdir(parents=True,exist_ok=True)
        record={'status':'wall_limit_reached','wall_limit_seconds':seconds,'elapsed_seconds':perf_counter()-started,
                'partial_trials':[str(p) for p in sorted(output.glob('trial-*/result.json'))],
                'note':'Partial trials require independent replay; timeout is not packing infeasibility.'}
        (output/'wall-limit.json').write_text(json.dumps(record,indent=2),encoding='utf8')
        print(json.dumps(record),flush=True)
        return 124

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from bom2kit.practical_design import design_practical
from bom2kit.report import fingerprint


def main():
    from time import perf_counter
    invocation_started=perf_counter()
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("library","policy","bom"):p.add_argument(name,type=Path)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--cache",type=Path)
    p.add_argument("--time-limit",type=float,default=120)
    p.add_argument("--cartons",type=int,nargs="+",default=[3,4,5,6,7])
    p.add_argument("--types",type=int,nargs="+",default=[2,3,4])
    p.add_argument("--hand-border",type=float,default=8.)
    p.add_argument("--packing-gap",type=float)
    p.add_argument("--finger-radius",type=float,default=4.)
    p.add_argument("--max-replays",type=int,default=12)
    p.add_argument("--cp-sat-python",type=Path)
    p.add_argument("--irregular-solver",type=Path)
    p.add_argument("--irregular-budget",type=float,default=0.)
    p.add_argument("--family-gap",action='append',default=[],metavar='FAMILY=MM')
    p.add_argument('--stack-height-factor',type=float,default=0.,help='Optional bounded flat-interface stacks; zero keeps floor-only control')
    p.add_argument('--refinement-budget',type=float,default=0.,help='Additional joint carton/content refinement seconds')
    p.add_argument('--rectangle-solver',type=Path)
    p.add_argument('--rectangle-budget',type=float,default=0.)
    p.add_argument('--floor-pair-budget',type=float,default=0.,help='Repeated adjacent source-supported pairs, individually handled')
    p.add_argument('--access-lane',type=float,default=0.,help='Envelope gap along Y only, subject to independent grip replay')
    p.add_argument('--common-floor-budget',type=float,default=0.,help='Footprint-first partial-layer beam search seconds')
    p.add_argument('--common-floor-only',action='store_true',help='Evaluate footprint-first search separately')
    p.add_argument('--supported-nesting',action='store_true',help='Individually inserted pairs supported by actual internal horizontal faces')
    p.add_argument('--source-surface-budget',type=float,default=0.,help='Actual-surface 3D proposals with branching support trees')
    p.add_argument('--volumetric-catalog', type=Path, help='Source-bound 3D motif proposals, expanded before full replay')
    p.add_argument('--access-repair-budget',type=float,default=0.,help='Repack cartons rejected by the unchanged finger model, including replay')
    p.add_argument('--wall-limit',type=float,help='Hard complete-invocation limit, including replay and report JSON')
    p.add_argument('--_supervised',action='store_true',help=argparse.SUPPRESS)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if a.wall_limit is not None and not a._supervised:
        raise SystemExit(supervise(sys.argv[1:],a.output,a.wall_limit))
    values={name:json.loads(getattr(a,name).read_bytes()) for name in ("library","policy","bom")}
    files={name:sha256(getattr(a,name).read_bytes()).hexdigest() for name in values}
    if a.volumetric_catalog: files['volumetric_catalog'] = sha256(a.volumetric_catalog.read_bytes()).hexdigest()
    root=Path(__file__).resolve().parents[1]
    def code_hashes():
        files=[*sorted((root/"src/bom2kit").glob("*.py")),Path(__file__).resolve()]
        return {str(f.relative_to(root)):sha256(f.read_bytes()).hexdigest() for f in files}
    before=code_hashes();counter=0
    def save_trial(result,record):
        nonlocal counter
        counter+=1;out=a.output/f"trial-{counter:02}";out.mkdir(exist_ok=True)
        (out/"result.json").write_text(json.dumps(result,indent=2),encoding="utf8")
        (out/"record.json").write_text(json.dumps(record,indent=2),encoding="utf8")
        print(json.dumps(record),flush=True)
    family_gaps={}
    for declaration in a.family_gap:
        family,value=declaration.rsplit('=',1);family_gaps[family]=float(value)
    run=design_practical(values["library"],values["policy"],values["bom"],cache=a.cache,time_limit=a.time_limit,
        carton_counts=a.cartons,type_caps=a.types,hand_border=a.hand_border,packing_gap=a.packing_gap,
        finger_radius=a.finger_radius,max_replays=a.max_replays,callback=save_trial,cp_sat_python=a.cp_sat_python,
        irregular_executable=a.irregular_solver,irregular_budget=a.irregular_budget,family_gaps=family_gaps,
        stack_height_factor=a.stack_height_factor,
        refinement_budget=a.refinement_budget,
        rectangle_executable=a.rectangle_solver,rectangle_budget=a.rectangle_budget,
        floor_pair_budget=a.floor_pair_budget,
        access_lane_mm=a.access_lane,
        common_floor_budget=a.common_floor_budget,common_floor_only=a.common_floor_only,
        supported_nesting=a.supported_nesting,
        source_surface_budget=a.source_surface_budget,
        access_repair_budget=a.access_repair_budget,
        volumetric_catalog=json.loads(a.volumetric_catalog.read_bytes()) if a.volumetric_catalog else None,
        progress=lambda record:print(json.dumps(record),flush=True))
    results=run.pop("results");plans=run.pop('assembly_plans')
    run["input_files_sha256"]=files
    run["engine_provenance"]={"initial_sha256":before,"unchanged_during_run":before==code_hashes()}
    run["parameters"]={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()}
    run["frontier"]=[]
    for index,(result,plan) in enumerate(zip(results,plans,strict=True),1):
        directory=a.output/f"frontier-{index:02}";directory.mkdir(exist_ok=True)
        if plan['result_fingerprint']!=fingerprint(result):raise ValueError('In-run assembly plan no longer matches the result')
        result["input_files_sha256"]=files;result["run_provenance"]=run["engine_provenance"]
        plan['result_fingerprint']=fingerprint(result)
        (directory/"result.json").write_text(json.dumps(result,indent=2),encoding="utf8")
        (directory/"assembly-plan.json").write_text(json.dumps(plan,indent=2),encoding="utf8")
        run["frontier"].append({"path":str(directory),**result["practical"]["metrics"]})
    run['design_seconds']=run['seconds']
    run['seconds']=perf_counter()-invocation_started
    run['timing_scope']='Invocation through frontier assembly-plan replay and artifact preparation; excludes interpreter startup and final file write'
    (a.output/"run.json").write_text(json.dumps(run,indent=2),encoding="utf8")
    print(json.dumps({k:v for k,v in run.items() if k in ("status","seconds","frontier")}),flush=True)


if __name__=="__main__":main()
