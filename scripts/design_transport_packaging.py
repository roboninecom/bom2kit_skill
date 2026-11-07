"""Design compatible modules and a foam-lined carton without spacers or references."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from bom2kit.logistics_design import design_logistics


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library",type=Path)
    parser.add_argument("policy",type=Path)
    parser.add_argument("bom",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--time-limit",type=float,default=120,help="Proposal budget; final verification is additional")
    parser.add_argument("--packing-solver",type=Path)
    parser.add_argument("--rectangle-solver",type=Path,help="Optional PackingSolver rectangle executable for floor-supported proposals")
    parser.add_argument("--cp-sat-python",type=Path,help="Optional separate Python interpreter with OR-Tools installed")
    parser.add_argument("--nesting-budget",type=float,default=0,help="Additional compatible CAD nesting search budget")
    parser.add_argument("--nesting-workers",type=int,choices=range(1,9),default=1,help="Parallel disjoint CAD pair proposal streams")
    parser.add_argument("--nesting-pitch",type=float,default=4,help="Voxel proposal pitch in mm; original triangle clearance is always rechecked")
    parser.add_argument("--nesting-objective",choices=("volume","balanced"),default="volume",help="Pair volume or geometry-derived aspect penalty; complete shipping volume is still the final objective")
    parser.add_argument("--heightfield-budget",type=float,default=0,help="Additional whole-family CAD insertion search budget; requires --portfolio")
    parser.add_argument("--shared-footprint-budget",type=float,default=0,help="Common carton footprint search; portfolio caps each trial at half its budget")
    parser.add_argument("--polish-budget",type=float,default=0,help="Additional supported placement search on the selected in-run grouping")
    parser.add_argument("--split-largest-family",action="store_true",help="Try two cartons for the largest compatible family within policy caps")
    parser.add_argument("--largest-family-cartons",type=int,default=1,help="Geometry-based subdivision of the largest family, within policy caps")
    parser.add_argument("--partition-strategy",choices=("volume","packing"),default="volume",help="Select compatible carton membership using volume order or actual partial packings")
    parser.add_argument("--balanced-cartons",type=int,default=0,help="Allocate a total carton budget across compatible families by geometric volume")
    parser.add_argument("--portfolio",action="store_true",help="Automatically keep the best checked fresh baseline, grouping and subdivision trial")
    args=parser.parse_args()
    values={};hashes={}
    for name in ("library","policy","bom"):
        raw=getattr(args,name).read_bytes();values[name]=json.loads(raw);hashes[name]=sha256(raw).hexdigest()
    args.output.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1]
    def code_hashes():
        files=list((root/"src"/"bom2kit").glob("*.py"))+[Path(__file__).resolve()]
        return {str(path.relative_to(root)):sha256(path.read_bytes()).hexdigest() for path in sorted(files)}
    initial_code=code_hashes()
    if args.portfolio:
        if args.split_largest_family or args.largest_family_cartons!=1 or args.partition_strategy!="volume" or args.balanced_cartons:
            parser.error("Portfolio selects its own subdivision trials; omit explicit split options")
        from bom2kit.logistics_portfolio import design_portfolio
        result,plan=design_portfolio(values["library"],values["policy"],values["bom"],args.output,
                                    time_limit=args.time_limit,nesting_seconds=args.nesting_budget,heightfield_seconds=args.heightfield_budget,
                                    executable=args.packing_solver,nesting_workers=args.nesting_workers,rectangle_executable=args.rectangle_solver,
                                    shared_footprint_seconds=args.shared_footprint_budget,nesting_pitch_mm=args.nesting_pitch,nesting_objective=args.nesting_objective,
                                    polish_seconds=args.polish_budget,cp_sat_python=args.cp_sat_python)
    else:
        if args.heightfield_budget:parser.error("Whole-family heightfield discovery requires --portfolio")
        result,plan=design_logistics(values["library"],values["policy"],values["bom"],time_limit=args.time_limit,
                                   executable=args.packing_solver,nesting_seconds=args.nesting_budget,work_directory=args.output,
                                   split_largest_family=args.split_largest_family,largest_family_cartons=args.largest_family_cartons,
                                   partition_strategy=args.partition_strategy,balanced_cartons=args.balanced_cartons,nesting_workers=args.nesting_workers,
                                   rectangle_executable=args.rectangle_solver,shared_footprint_seconds=args.shared_footprint_budget,nesting_pitch_mm=args.nesting_pitch,nesting_objective=args.nesting_objective,
                                   module_improvement_seconds=args.polish_budget,cp_sat_python=args.cp_sat_python)
    result["input_files_sha256"]=hashes
    final_code=code_hashes()
    result["run_provenance"]={"python":sys.version,"engine_files_sha256":initial_code,
                              "engine_files_unchanged_during_run":initial_code==final_code,
                              "parameters":{"time_limit":args.time_limit,"nesting_budget":args.nesting_budget,
                                            "nesting_workers":args.nesting_workers,
                                            "nesting_pitch_mm":args.nesting_pitch,
                                            "nesting_objective":args.nesting_objective,
                                            "heightfield_budget":args.heightfield_budget,
                                            "shared_footprint_budget":args.shared_footprint_budget,
                                            "polish_budget":args.polish_budget,
                                            "split_largest_family":args.split_largest_family,
                                            "largest_family_cartons":args.largest_family_cartons,
                                            "partition_strategy":args.partition_strategy,
                                            "balanced_cartons":args.balanced_cartons,
                                            "portfolio":args.portfolio,
                                            "rectangle_solver":str(args.rectangle_solver) if args.rectangle_solver else None,
                                            "cp_sat_python":str(args.cp_sat_python) if args.cp_sat_python else None,
                                            "packing_solver":str(args.packing_solver) if args.packing_solver else None}}
    # Assembly plan is bound to the complete final result including input hashes.
    from bom2kit.report import fingerprint
    plan["result_fingerprint"]=fingerprint(result)
    (args.output/"result.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    (args.output/"assembly-plan.json").write_text(json.dumps(plan,indent=2),encoding="utf8")
    print(json.dumps({"external_mm":result["envelope_design"]["candidate"]["external_mm"],
                      "cartons":result["logistics"]["carton_count"],"types":result["logistics"]["carton_types"],
                      "seconds":result["search"]["total_seconds"],"physical_qualification":False}))


if __name__=="__main__":
    main()
