"""Retain the best fully checked design across fresh compatible grouping trials."""
import json
import math
from pathlib import Path
from time import perf_counter

from .compatible_nesting import discover_compatible_units,compose_compatible_units
from .group_portfolio import group_configurations
from .logistics_design import design_logistics
from .report import fingerprint


def design_portfolio(library,policy,bom,output,*,time_limit=180,nesting_seconds=140,heightfield_seconds=0,nesting_workers=1,executable=None,rectangle_executable=None):
    if not math.isfinite(time_limit) or time_limit<=0 or not math.isfinite(nesting_seconds) or nesting_seconds<0 or not math.isfinite(heightfield_seconds) or heightfield_seconds<0:
        raise ValueError("Finite positive proposal budget and nonnegative nesting budget required")
    from .bom import reconcile_bom
    if not reconcile_bom(bom,library)["complete"]:raise ValueError("Incomplete source BOM")
    started=perf_counter();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    trials=[];best=None;proposal_used=0;pattern_cache={}
    def attempt(name,budget,prepared=None,split=1,partition="volume"):
        nonlocal best,proposal_used
        stage=perf_counter();directory=output/name;directory.mkdir(parents=True,exist_ok=True)
        try:
            result,plan=design_logistics(library,policy,bom,time_limit=budget,executable=executable,
                                         work_directory=directory,_prepared_nesting=prepared,largest_family_cartons=split,
                                         _pattern_cache=pattern_cache,partition_strategy=partition,rectangle_executable=rectangle_executable)
            volume=result["envelope_design"]["candidate"]["volume_mm3"]
            (directory/"result.json").write_text(json.dumps(result,indent=2),encoding="utf8")
            (directory/"assembly-plan.json").write_text(json.dumps(plan,indent=2),encoding="utf8")
            trials.append({"name":name,"status":"validated","volume_mm3":volume,"seconds":perf_counter()-stage})
            if best is None or volume<best[0]:best=(volume,result,plan,name)
        except ValueError as error:
            trials.append({"name":name,"status":"rejected","reason":str(error),"seconds":perf_counter()-stage})
        proposal_used+=perf_counter()-stage
    attempt("baseline",max(5,min(35,time_limit*.25)))
    nesting=None
    if nesting_seconds>0 or heightfield_seconds>0:
        candidates=[];discovery_search=[];discovery_seconds=0
        if nesting_seconds>0:
            nesting=discover_compatible_units(library,policy,output/"discovery",nesting_seconds,workers=nesting_workers)
            candidates.extend(nesting["alternatives"]);discovery_search.extend(nesting["search"])
            discovery_seconds+=nesting["elapsed_seconds"]
        if heightfield_seconds>0:
            from .heightfield_nesting import discover_heightfield_groups
            heightfield=discover_heightfield_groups(library,policy,output/"heightfield",heightfield_seconds)
            candidates.extend(heightfield["alternatives"]);discovery_seconds+=heightfield["seconds"]
            discovery_search.append({"method":"whole_family_heightfield","attempts":heightfield["attempts"],"seconds":heightfield["seconds"]})
        nesting=compose_compatible_units(library,policy,candidates,output/"discovery-combined",discovery_search,discovery_seconds)
        pools=group_configurations(library,[a for _,a in nesting["alternatives"]],3,optimize=True)
        for index,pool in enumerate(pools):
            remaining=time_limit-proposal_used
            if remaining<5:break
            candidates=[(policy["families"][a["members"][0]],a) for a in pool]
            prepared=compose_compatible_units(library,policy,candidates,output/f"grouping-{index}",
                                              nesting["search"],nesting["elapsed_seconds"])
            attempt(f"nested-{index}",max(5,remaining/(len(pools)-index+3)),prepared)
    if time_limit-proposal_used>=5 and len(set(policy["families"].values()))<policy["max_inner_cartons"]:
        splits=[("split-family",2,"volume"),("packing-split-2",2,"packing")]
        if len(set(policy["families"].values()))+2<=policy["max_inner_cartons"]:
            splits.append(("packing-split-3",3,"packing"))
        for index,(label,count,strategy) in enumerate(splits):
            remaining=time_limit-proposal_used
            if remaining<5:break
            attempt(label,remaining/(len(splits)-index),nesting,split=count,partition=strategy)
    if best is None:raise ValueError(f"No portfolio candidate passed: {trials}")
    _,result,plan,name=best
    result["search"]["selected_trial_seconds"]=result["search"]["total_seconds"]
    result["search"]["portfolio"]={"trials":trials,"selected":name,"reference_used":False,
                                   "discovery_seconds":nesting["elapsed_seconds"] if nesting else 0}
    result["search"]["total_seconds"]=perf_counter()-started
    result["search"]["timing_scope"]="Complete fresh portfolio including discovery, rejected trials and final checks; source import excluded"
    plan["result_fingerprint"]=fingerprint(result)
    return result,plan
