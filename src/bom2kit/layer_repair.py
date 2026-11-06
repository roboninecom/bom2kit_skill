"""Local repacking of an internally generated layer assignment on the size lattice."""
import math
from time import perf_counter

from .strip_packing import pack_strip


def repair_layer_stack(units, candidate, gap, thickness, increment, time_limit=2):
    """Propose complete one-column stacks; callers independently validate them.

    Preserve layer membership, never old part coordinates. Every layer is freshly
    packed using permitted orientations. Multi-column layouts remain unchanged.
    """
    started = perf_counter()
    layers = candidate["layout"].get("layers",[])
    if not layers or len({tuple(layer["inner_mm"][:2]) for layer in layers}) != 1:
        return []
    if len({tuple(layer["position_mm"][:2]) for layer in layers}) != 1:
        return []
    by_id = {unit["unit_id"]:unit for unit in units}
    memberships = []
    seen = []
    for layer in layers:
        ids = [p["unit_id"] for p in candidate["layout"]["placements"] if p["layer_id"] == layer["id"]]
        if not ids or any(uid not in by_id for uid in ids):
            return []
        memberships.append([by_id[uid] for uid in ids])
        seen.extend(ids)
    if len(seen) != len(by_id) or set(seen) != set(by_id):
        return []
    base_width,base_depth = layers[0]["inner_mm"][:2]
    proposals = []
    offsets = [(0,0),(-1,-1),(-2,-2),(-1,0),(0,-1),(-2,0),(0,-2),
               (1,-1),(-1,1),(1,0),(0,1),(1,1),(2,-2),(-2,2)]
    for dx,dy in offsets:
        if perf_counter()-started >= time_limit:
            break
        width,depth = base_width+dx*increment,base_depth+dy*increment
        if min(width,depth) <= 0:
            continue
        stack = []
        for layer,members in zip(layers,memberships):
            # Volume is a necessary bound only, not a fit certificate.
            lower = sum(math.prod(unit["dimensions"]) for unit in members)/(width*depth)
            ceiling = layer["inner_mm"][2]+2*increment
            heights = sorted({size[2] for unit in members for _,size in unit["orientations"]
                              if lower-1e-8 <= size[2] <= ceiling+1e-8})
            best = None
            for height in heights:
                for mode in ("bottom_left","height_fill","short_side"):
                    if perf_counter()-started >= time_limit:
                        break
                    packed = pack_strip(members,width,height,gap,depth=depth,placement_score=mode)
                    if packed is not None:
                        if best is None or packed["usable_mm"][2] < best["usable_mm"][2]:
                            best = packed
                if best is not None or perf_counter()-started >= time_limit:
                    break
            if best is None:
                break
            stack.append(best)
        if len(stack) == len(layers):
            proposals.append({"width_mm":width,"depth_mm":depth,"layers":stack,
                              "height_mm":sum(math.ceil((p["usable_mm"][2]+2*thickness)/increment)*increment for p in stack)})
    return proposals
