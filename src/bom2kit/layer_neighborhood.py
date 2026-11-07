"""Bounded membership and orientation improvement of a generated layer stack."""
from copy import deepcopy
import math
import random
from time import perf_counter

from .models import normalize, number
from .strip_packing import pack_strip


def improve_layer_membership(candidate, *, increment=1, time_limit=30, seed=0, max_iterations=10000):
    """Improve an internal incumbent; never supply an engineer reference here.

    Source dimensions, rotations, protection and walls stay fixed. Only complete,
    independently checked stacks can replace the incumbent. Equal-height moves
    explore alternative assignments; a separate best state prevents regression.
    """
    from .layered_design import validate_layered

    started = perf_counter()
    increment = number(increment, "increment", True)
    time_limit = number(time_limit, "time_limit", True)
    problem = candidate["input"]
    if not validate_layered(problem, candidate["layout"])["valid"]:
        raise ValueError("A valid generated layer incumbent is required")
    layers = candidate["layout"]["layers"]
    result = {"candidate":deepcopy(candidate), "iterations":0, "accepted_moves":0,
              "improvements":0, "seed":seed, "elapsed_seconds":0}
    if len({tuple(l["inner_mm"][:2]) for l in layers}) != 1 or len({tuple(l["position_mm"][:2]) for l in layers}) != 1:
        result["elapsed_seconds"] = perf_counter()-started
        return result
    data = normalize(problem)
    units = {u["unit_id"]:u for u in data["units"]}
    thickness = problem["inner_wall_mm"]
    width,depth = layers[0]["inner_mm"][:2]
    gap = data["gap"]
    rng = random.Random(seed)
    state = []
    for layer in layers:
        poses = [{**p,"position_mm":[p["position_mm"][k]-layer["position_mm"][k]-thickness for k in range(3)]}
                 for p in candidate["layout"]["placements"] if p["layer_id"] == layer["id"]]
        state.append({"placements":poses,"usable_mm":[max(p["position_mm"][k]+p["dimensions_mm"][k] for p in poses) for k in range(3)]})

    def closed_height(packed):
        return math.ceil((packed["usable_mm"][2]+2*thickness-1e-8)/increment)*increment

    def total_height(stack):
        return sum(closed_height(p) for p in stack)

    def membership(packed):
        return frozenset(p["unit_id"] for p in packed["placements"])

    cache = {membership(p):p for p in state}

    def repack(ids, cap):
        if not ids:
            return {"placements":[],"usable_mm":[0,0,0]}
        old = cache.get(frozenset(ids))
        best = old if old and old["usable_mm"][2] <= cap+1e-8 else None
        members = [units[uid] for uid in sorted(ids)]
        lower = sum(math.prod(u["dimensions"]) for u in members)/(width*depth)
        heights = sorted({s[2] for u in members for _,s in u["orientations"] if lower-1e-8 <= s[2] <= cap+1e-8})
        # Try attainable low heights first; volume alone never certifies fit.
        for height in heights:
            if best and height >= best["usable_mm"][2]-1e-8:
                break
            if perf_counter()-started >= time_limit:
                break
            for mode,order in (("height_fill","area"),("bottom_left","area"),("short_side","area"),
                               ("height_fill","compact"),("short_side","compact"),("height_fill","volume"),
                               ("short_side","best_fit"),("area","best_fit"),
                               ("height_fill","input"),("short_side","input")):
                ordered = list(members)
                if order == "input":
                    ordered.sort(key=lambda u:-math.prod(u["dimensions"])*rng.uniform(.4,1.6))
                packed = pack_strip(ordered,width,height,gap,depth=depth,placement_score=mode,item_order=order)
                if packed is not None:
                    best = packed
                    break
            if best and best["usable_mm"][2] <= height+1e-8:
                break
        if best:
            cache[frozenset(ids)] = best
        return best

    def freeze(stack):
        return stack_candidate(candidate,stack,width,depth,increment)

    initial = freeze(state)
    if initial["validation"]["valid"] and initial["volume_mm3"] < result["candidate"]["volume_mm3"]:
        result["candidate"] = initial
        result["improvements"] += 1
    best_state = state
    visited = set()
    for iteration in range(max_iterations):
        if len(state)<2 or perf_counter()-started >= time_limit:
            break
        result["iterations"] += 1
        source,dest = rng.sample(range(len(state)),2)
        left,right = membership(state[source]),membership(state[dest])
        source_poses = state[source]["placements"]
        if iteration % 4 == 0:
            tallest = max(p["dimensions_mm"][2] for p in source_poses)
            moved = {p["unit_id"] for p in source_poses if p["dimensions_mm"][2] >= tallest-1e-8}
        else:
            moved = {rng.choice(sorted(left))}
        swapped = {rng.choice(sorted(right))} if iteration % 3 == 0 else set()
        new_left,new_right = (left-moved)|swapped,(right-swapped)|moved
        key = (frozenset(new_left),frozenset(new_right))
        if key in visited:
            continue
        visited.add(key)
        combined = closed_height(state[source])+closed_height(state[dest])
        # Height-neutral moves may lead to a later reduction, but never enlarge
        # the current stack. Remove empty layers instead of keeping empty boxes.
        packed_left = repack(new_left,state[source]["usable_mm"][2])
        if packed_left is None:
            continue
        left_height = closed_height(packed_left) if new_left else 0
        packed_right = repack(new_right,combined-left_height-2*thickness)
        if packed_right is None or left_height+closed_height(packed_right)>combined+1e-8:
            continue
        proposal = [packed_left if i==source else packed_right if i==dest else p for i,p in enumerate(state)]
        proposal = [p for p in proposal if p["placements"]]
        state = proposal
        result["accepted_moves"] += 1
        if total_height(state)<total_height(best_state)-1e-8:
            frozen = freeze(state)
            if frozen["validation"]["valid"] and frozen["volume_mm3"] < result["candidate"]["volume_mm3"]:
                result["candidate"] = frozen
                result["improvements"] += 1
                best_state = state
        if iteration % 200 == 199:
            state = best_state
    result["elapsed_seconds"] = perf_counter()-started
    return result


def stack_candidate(candidate, stack, width, depth, increment=1):
    """Build and independently validate a closed stack from generated strips."""
    from .layered_design import validate_layered
    data = normalize(candidate["input"])
    thickness = candidate["input"]["inner_wall_mm"]
    proposed = deepcopy(candidate)
    poses,new_layers,z = [],[],data["protection"][2]
    for index,packed in enumerate(stack,1):
        lid = "layer-"+str(index)
        height = math.ceil((packed["usable_mm"][2]+2*thickness-1e-8)/increment)*increment-2*thickness
        position = [data["protection"][0],data["protection"][1],z]
        new_layers.append({"id":lid,"inner_mm":[width,depth,height],"wall_mm":thickness,"position_mm":position})
        poses.extend({**p,"layer_id":lid,"position_mm":[p["position_mm"][k]+position[k]+thickness for k in range(3)]} for p in packed["placements"])
        z += height+2*thickness
    cavity = [width+2*thickness,depth+2*thickness,z-data["protection"][2]]
    external = [math.ceil((cavity[k]+2*(data["wall"][k]+data["protection"][k])+(data["reserved_top"] if k==2 else 0)-1e-8)/increment)*increment for k in range(3)]
    proposed["input"]["container"]["inner_mm"] = [external[k]-2*data["wall"][k] for k in range(3)]
    proposed["layout"] = {"placements":poses,"layers":new_layers,"status":"feasible"}
    proposed["validation"] = validate_layered(proposed["input"],proposed["layout"])
    proposed["external_mm"],proposed["volume_mm3"] = external,math.prod(external)
    proposed["packaging_bom"] = [{"id":l["id"],"quantity":1,"type":"closed_rectangular_inner_carton",
                                 "inner_mm":l["inner_mm"],"external_mm":[d+2*thickness for d in l["inner_mm"]],
                                 "wall_mm":thickness,"manufacturing_status":"Dimension specification; production dieline and strength qualification pending"} for l in new_layers]
    return proposed
