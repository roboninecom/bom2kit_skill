"""Constructive maximal-free-rectangle strip packing with bounded part height."""
import math


def pack_strip(units, width, height, gap=0, depth=None, allow_partial=False, priority_unit=None,
               placement_score="bottom_left", item_order="area"):
    """Place envelope units on the floor, selecting individual orientations.

    Free rectangles may overlap one another, but each is empty. All rectangles
    overlapping a placement are split. No support or artificial filler is needed.
    """
    if placement_score not in ("bottom_left","short_side","area"):
        raise ValueError("Unknown rectangle placement score")
    if item_order not in ("area","volume"):
        raise ValueError("Unknown item order")
    available = []
    for unit in units:
        choices = [(r, s) for r, s in unit["orientations"] if s[0] <= width + 1e-8 and s[2] <= height + 1e-8]
        if not choices:
            if allow_partial:
                continue
            return None
        available.append((unit, choices))
    available.sort(key=lambda entry: (entry[0]["unit_id"] != priority_unit,
                                     -max(math.prod(s) if item_order == "volume" else s[0]*s[1] for _, s in entry[1]),
                                     -max(max(s[:2]) for _, s in entry[1]), entry[0]["unit_id"]))
    length = sum(max(s[1] for _, s in choices) + gap for _, choices in available)
    if depth is not None:
        length = depth
    free = [(0.0, 0.0, width + gap, length + gap)]
    placements, used_x, used_y, used_z = [], 0., 0., 0.
    for unit, choices in available:
        options = []
        for x, y, w, h in free:
            for rotation, size in choices:
                dx, dy = size[0] + gap, size[1] + gap
                if dx <= w + 1e-8 and dy <= h + 1e-8:
                    short,long = min(w-dx,h-dy),max(w-dx,h-dy)
                    if placement_score == "short_side":
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
        right, top = x + size[0] + gap, y + size[1] + gap
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
        free = [r for i,r in enumerate(unique) if not any(
            j != i and r[0] >= s[0]-1e-8 and r[1] >= s[1]-1e-8 and
            r[0]+r[2] <= s[0]+s[2]+1e-8 and r[1]+r[3] <= s[1]+s[3]+1e-8
            for j,s in enumerate(unique))]
    return {"placements": placements, "usable_mm": [used_x, used_y, used_z]}
