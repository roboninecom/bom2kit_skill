"""Bounded alternative layer sequences for one geometry-derived footprint."""
import math
from time import perf_counter
from .strip_packing import pack_strip


def search_sequences(units, width, depth, thickness, gap, increment, heights,
                     time_limit=5, beam_width=4, incumbent_height=float("inf"),placement_score="bottom_left",item_order="area"):
    """Return a shorter complete stack, never an incomplete packing prefix."""
    from .layered_design import remaining_height_bands

    started = perf_counter()
    area = width*depth
    volumes = {u["unit_id"]:math.prod(u["dimensions"]) for u in units}
    beam = [(list(units),[],0.)]
    best, best_height, explored = None, incumbent_height, 0
    while beam and perf_counter()-started < time_limit:
        branches = {}
        for remaining, layers, height_so_far in beam:
            anchor = max(remaining,key=lambda u:volumes[u["unit_id"]])["unit_id"]
            options = {}
            for height in remaining_height_bands(remaining,increment,heights):
                for priority in (anchor,None):
                    if perf_counter()-started >= time_limit:
                        break
                    packed = pack_strip(remaining,width,height,gap,depth=depth,allow_partial=True,priority_unit=priority,
                                        placement_score=placement_score,item_order=item_order)
                    if not packed["placements"]:
                        continue
                    used = frozenset(p["unit_id"] for p in packed["placements"])
                    layer_height = math.ceil((packed["usable_mm"][2]+2*thickness)/increment)*increment
                    options.setdefault((used,layer_height),packed)
            for (used,layer_height),packed in options.items():
                explored += 1
                height = height_so_far+layer_height
                left = [u for u in remaining if u["unit_id"] not in used]
                path = layers+[packed]
                if not left:
                    if height < best_height:
                        best,best_height = path,height
                    continue
                left_volume = sum(volumes[u["unit_id"]] for u in left)
                if height+left_volume/area >= best_height:
                    continue
                key = tuple(u["unit_id"] for u in left)
                # Same remaining units have the same future choices. A taller
                # prefix is dominated even if its old layer coordinates differ.
                if key not in branches or height < branches[key][2]:
                    score = height+left_volume/(area*.8)
                    branches[key] = (left,path,height,score)
        ranked = sorted(branches.values(),key=lambda b:(b[3],b[2],tuple(u["unit_id"] for u in b[0])))
        beam = [b[:3] for b in ranked[:beam_width]]
    return {"layers":best,"height_mm":best_height if best else None,
            "explored_sequences":explored,"elapsed_seconds":perf_counter()-started,
            "optimality_proven":False}
