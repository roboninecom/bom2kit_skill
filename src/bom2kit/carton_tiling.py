"""Slicing layouts whose leaves expand into a complete carton block, no fillers."""
from copy import deepcopy
from itertools import product
import math
from time import perf_counter


def carton_size_key(dimensions):
    """A horizontal quarter-turn does not create another carton SKU."""
    return (*sorted(dimensions[:2]),dimensions[2])


def tile_modules(modules, *, time_limit=20, frontier=64, wall=7, foam=15,
                 reserve=.8, max_types=6, increment=1):
    """Select module patterns and tile by enlarging closed carton dimensions.

    XY joins expand children to common cross-sections; Z joins do the same for
    footprint. Thus all leaves partition the root, with no spacer objects.
    This bounded slicing DP is a heuristic, not global geometric optimization.
    """
    started = perf_counter()
    count = len(modules)
    if not 1 <= count <= 8 or frontier < 1 or increment <= 0:
        raise ValueError("One to eight modules, positive frontier and increment required")
    states = {}
    for index, module in enumerate(modules):
        states[1 << index] = [{"size": list(p["external_mm"]), "module": index,
                                "pattern": j} for j, p in enumerate(module["patterns"])]

    def reduce(pool):
        unique = {}
        for candidate in pool:
            dims = tuple(candidate["size"])
            unique.setdefault(dims, candidate)
        ordered = sorted(unique.values(), key=lambda c: (math.prod(c["size"]), max(c["size"])))
        # A very flat minimum-volume block can lose once six-face foam is
        # included. Preserve both interior volume and shipping-volume choices.
        selected = ordered[:max(1, frontier//4)]
        protected=sorted(ordered,key=lambda c:math.prod(v+2*(wall+foam) for v in c["size"]))
        for c in protected[:max(1,frontier//4)]:
            if c not in selected:selected.append(c)
        for axis in range(3):
            for c in sorted(ordered, key=lambda c: (c["size"][axis], math.prod(c["size"])))[:max(1, frontier//6)]:
                if c not in selected:
                    selected.append(c)
        for c in ordered:
            if len(selected) >= frontier:
                break
            if c not in selected:
                selected.append(c)
        return selected

    for size in range(2, count+1):
        for mask in range(1, 1 << count):
            if mask.bit_count() != size:
                continue
            proposals = []
            first = mask & -mask
            sub = (mask-1) & mask
            while sub:
                other = mask ^ sub
                if sub & first and other and sub in states and other in states:
                    for left, right in product(states[sub], states[other]):
                        for axis in range(3):
                            dims = [max(a,b) for a,b in zip(left["size"],right["size"])]
                            dims[axis] = left["size"][axis]+right["size"][axis]
                            proposals.append({"size": dims, "axis": axis, "children": [left,right]})
                sub = (sub-1) & mask
            if proposals:
                states[mask] = reduce(proposals)
            if perf_counter()-started > time_limit:
                # Still construct one complete fallback from the leaves; a time
                # limit cannot turn a partial partition into an accepted plan.
                root = states[1][0]
                for j in range(1,count):
                    leaf=states[1<<j][0]
                    root={"size":[max(root["size"][0],leaf["size"][0]),
                                  max(root["size"][1],leaf["size"][1]),root["size"][2]+leaf["size"][2]],
                          "axis":2,"children":[root,leaf]}
                states.setdefault((1<<count)-1, [root])
                break
        if perf_counter()-started > time_limit:
            break

    def expand(node, origin, dimensions, leaves):
        if "module" in node:
            leaves.append({"module":node["module"],"pattern":node["pattern"],
                           "position_mm":list(origin),"external_mm":list(dimensions)})
            return
        axis=node["axis"];left,right=node["children"]
        # Allocate slack to the first child; cross-dimensions are filled by both.
        cut=dimensions[axis]-right["size"][axis]
        a=list(dimensions);b=list(dimensions);b_origin=list(origin)
        a[axis]=cut;b[axis]=dimensions[axis]-cut;b_origin[axis]+=cut
        expand(left,origin,a,leaves);expand(right,b_origin,b,leaves)

    candidates=[]
    for root in states.get((1<<count)-1,[]):
        dims=[math.ceil(v/increment-1e-9)*increment for v in root["size"]]
        leaves=[];expand(root,[foam]*3,dims,leaves)
        distinct=len({carton_size_key(l["external_mm"]) for l in leaves})
        if distinct > max_types:
            continue
        external=[math.ceil((v+2*(wall+foam)+(reserve if k==2 else 0))/increment-1e-9)*increment
                  for k,v in enumerate(dims)]
        candidates.append({"leaves":leaves,"block_mm":dims,"external_mm":external,
                           "volume_mm3":math.prod(external),"distinct_carton_sizes":distinct})
    candidates.sort(key=lambda c:(c["volume_mm3"],c["distinct_carton_sizes"]))
    return {"candidate":candidates[0] if candidates else None,"alternatives":candidates[:12],
            "elapsed_seconds":perf_counter()-started,"reference_used":False,"spacers":0}
