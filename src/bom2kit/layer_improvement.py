"""Alternate membership and footprint improvement within a shared soft budget."""
from copy import deepcopy
from time import perf_counter

from .layer_neighborhood import improve_layer_membership, stack_candidate
from .layer_repair import repair_layer_stack
from .models import normalize, number, vector


def improve_generated_layers(candidate, time_limit=60, increment=1, seed=0, max_external_mm=None):
    started = perf_counter()
    time_limit = number(time_limit,"time_limit",True)
    increment = number(increment,"increment",True)
    maximum = vector(max_external_mm,"maximum",True) if max_external_mm is not None else None
    best,stages = deepcopy(candidate),[]

    def retain(proposal):
        nonlocal best
        if maximum and any(a>b+1e-8 for a,b in zip(proposal["external_mm"],maximum)):
            return
        if proposal["validation"]["valid"] and proposal["volume_mm3"] < best["volume_mm3"]:
            best = proposal

    # Membership changes can unlock a footprint reduction and vice versa.
    for cycle in range(2):
        remaining = time_limit-(perf_counter()-started)
        if remaining <= 0:
            break
        moved = improve_layer_membership(best,increment=increment,time_limit=remaining*(.55 if cycle==0 else .75),
                                         seed=seed+cycle,max_iterations=100000)
        retain(moved["candidate"])
        stages.append({"stage":"membership","cycle":cycle,**{k:v for k,v in moved.items() if k!="candidate"}})
        while perf_counter()-started < time_limit:
            before = best["volume_mm3"]
            tick = perf_counter()
            repairs = repair_layer_stack(normalize(best["input"])["units"],best,
                                         best["input"].get("gap_mm",0),best["input"]["inner_wall_mm"],increment,
                                         time_limit-(perf_counter()-started))
            for proposal in repairs:
                retain(stack_candidate(best,proposal["layers"],proposal["width_mm"],proposal["depth_mm"],increment))
            stages.append({"stage":"footprint","cycle":cycle,"proposals":len(repairs),"seconds":perf_counter()-tick})
            if best["volume_mm3"] >= before:
                break
    return {"candidate":best,"stages":stages,"elapsed_seconds":perf_counter()-started,
            "reference_used":False,"optimality_proven":False}
