"""Constructive maximal-free-rectangle strip packing with bounded part height."""
import math


def placement_modes(score):
    """Expand the mixed layer policy into concrete placement heuristics."""
    return ("bottom_left", "height_fill") if score == "portfolio" else (score,)


def pack_strip(units, width, height, gap=0, depth=None, allow_partial=False, priority_unit=None,
               placement_score="bottom_left", item_order="area", initial_placements=()):
    """Place envelope units on the floor, selecting individual orientations.

    Free rectangles may overlap one another, but each is empty. All rectangles
    overlapping a placement are split. No support or artificial filler is needed.
    """
    if placement_score not in ("bottom_left","short_side","area","height_fill"):
        raise ValueError("Unknown rectangle placement score")
    if item_order not in ("area","volume","input","compact","best_fit"):
        raise ValueError("Unknown item order")
    available = []
    for unit in units:
        choices = [(r, s) for r, s in unit["orientations"] if s[0] <= width + 1e-8 and s[2] <= height + 1e-8]
        if not choices:
            if allow_partial:
                continue
            return None
        available.append((unit, choices))
    if depth is not None and not allow_partial:
        # Necessary floor-area bound over permitted orientations. This cannot
        # reject a feasible rectangle packing, and avoids expensive failed fits.
        minimum_area = 0.0
        for _,choices in available:
            areas = [s[0]*s[1] for _,s in choices if s[1] <= depth+1e-8]
            if not areas:
                return None
            minimum_area += min(areas)
        if minimum_area > width*depth*(1+1e-10):
            return None
    if item_order != "input":
        available.sort(key=lambda entry: (entry[0]["unit_id"] != priority_unit,
                                         -(min(s[0]*s[1] for _,s in entry[1]) if item_order == "compact" else
                                           max(math.prod(s) if item_order == "volume" else s[0]*s[1] for _, s in entry[1])),
                                         -max(max(s[:2]) for _, s in entry[1]), entry[0]["unit_id"]))
    length = sum(max(s[1] for _, s in choices) + gap for _, choices in available)
    if depth is not None:
        length = depth
    free = [(0.0, 0.0, width + gap, length + gap)]
    placements, used_x, used_y, used_z = [], 0., 0., 0.
    by_id = {u["unit_id"]:u for u in units}
    initial_ids = set()
    for pose in initial_placements:
        uid = pose["unit_id"]
        if uid not in by_id or uid in initial_ids or pose["item_id"] != by_id[uid]["item_id"]:
            raise ValueError("Invalid initial strip membership")
        size = tuple(pose["dimensions_mm"])
        if (tuple(pose["rotation"]),size) not in by_id[uid]["orientations"]:
            raise ValueError("Invalid initial strip orientation")
        x,y,z = pose["position_mm"]
        if abs(z)>1e-8 or min(x,y)<0 or x+size[0]>width+1e-8 or y+size[1]>length+1e-8 or size[2]>height+1e-8:
            return None
        if any(all(pose["position_mm"][k] < other["position_mm"][k]+other["dimensions_mm"][k]+gap-1e-8 and
                   other["position_mm"][k] < pose["position_mm"][k]+size[k]+gap-1e-8 for k in (0,1)) for other in placements):
            return None
        placements.append(dict(pose))
        initial_ids.add(uid)
        used_x,used_y,used_z = max(used_x,x+size[0]),max(used_y,y+size[1]),max(used_z,size[2])
        free = subtract_rectangle(free,x,y,size[0]+gap,size[1]+gap)
    pending = [(u,choices) for u,choices in available if u["unit_id"] not in initial_ids]
    while pending:
        selected_index = 0
        if item_order == "best_fit":
            selected = []
            for index,(candidate,choices) in enumerate(pending):
                for x,y,w,h in free:
                    for rotation,size in choices:
                        dx,dy = size[0]+gap,size[1]+gap
                        if dx<=w+1e-8 and dy<=h+1e-8:
                            short,long = min(w-dx,h-dy),max(w-dx,h-dy)
                            score = (w*h-dx*dy,short) if placement_score == "area" else (short,long)
                            selected.append(((candidate["unit_id"] != priority_unit,*score,-size[0]*size[1],index),index))
            if not selected:
                if allow_partial:
                    break
                return None
            selected_index = min(selected)[1]
        unit,choices = pending.pop(selected_index)
        options = []
        for x, y, w, h in free:
            for rotation, size in choices:
                dx, dy = size[0] + gap, size[1] + gap
                if dx <= w + 1e-8 and dy <= h + 1e-8:
                    short,long = min(w-dx,h-dy),max(w-dx,h-dy)
                    if placement_score == "height_fill":
                        score = (-size[2],max(used_y,y+size[1]),short,y,x,size)
                    elif placement_score == "short_side":
                        score = (short,long,max(used_y,y+size[1]),y,x,size)
                    elif placement_score == "area":
                        score = (w*h-dx*dy,short,max(used_y,y+size[1]),y,x,size)
                    else:
                        score = (max(used_y,y+size[1]),short,y,x,size)
                    options.append((score,x,y,rotation,size))
        if not options:
            if allow_partial:
                continue
            return None
        _, x, y, rotation, size = min(options)
        placements.append({"item_id": unit["item_id"], "unit_id": unit["unit_id"],
                           "position_mm": [x, y, 0], "dimensions_mm": list(size), "rotation": list(rotation)})
        used_x, used_y, used_z = max(used_x, x+size[0]), max(used_y, y+size[1]), max(used_z, size[2])
        free = subtract_rectangle(free,x,y,size[0]+gap,size[1]+gap)
    return {"placements": placements, "usable_mm": [used_x, used_y, used_z]}


def subtract_rectangle(free, x, y, dx, dy):
    right, top = x+dx, y+dy
    split = []
    for a, b, w, h in free:
        if right <= a + 1e-8 or x >= a+w-1e-8 or top <= b+1e-8 or y >= b+h-1e-8:
            split.append((a,b,w,h))
            continue
        if x > a + 1e-8: split.append((a,b,x-a,h))
        if right < a+w-1e-8: split.append((right,b,a+w-right,h))
        if y > b+1e-8: split.append((a,b,w,y-b))
        if top < b+h-1e-8: split.append((a,top,w,b+h-top))
    unique = list(dict.fromkeys(split))
    return [r for i,r in enumerate(unique) if not any(
        j != i and r[0] >= s[0]-1e-8 and r[1] >= s[1]-1e-8 and
        r[0]+r[2] <= s[0]+s[2]+1e-8 and r[1]+r[3] <= s[1]+s[3]+1e-8
        for j,s in enumerate(unique))]
