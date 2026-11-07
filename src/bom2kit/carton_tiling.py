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
    if not 1 <= count <= 8 or frontier < 1 or increment <= 0 or max_types<1:
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
        if max_types>=count:
            # Componentwise smaller subtrees can replace larger ones in every
            # future slicing join. This dominance rule is safe when the type
            # cap cannot constrain the number of leaves. A prefix-min tree
            # finds the 3D skyline without a quadratic comparison loop.
            coordinates=sorted({c["size"][1] for c in unique.values()})
            indices={v:i+1 for i,v in enumerate(coordinates)}
            prefix=[math.inf]*(len(coordinates)+1);skyline=[]
            for candidate in sorted(unique.values(),key=lambda c:tuple(c["size"])):
                _,y,z=candidate["size"];i=indices[y];best=math.inf
                while i:
                    best=min(best,prefix[i]);i-=i&-i
                if best<=z:continue
                skyline.append(candidate);i=indices[y]
                while i<len(prefix):
                    prefix[i]=min(prefix[i],z);i+=i&-i
            unique={tuple(c["size"]):c for c in skyline}
            if count<=3:return skyline
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

    # Prune each leaf before the expensive subset products. A smaller pattern
    # can always be expanded to a dominated leaf's dimensions, even with a
    # carton-type cap, so this particular dominance rule is safe for leaves.
    for mask,pool in list(states.items()):
        ordered=sorted(pool,key=lambda p:tuple(p["size"]))
        skyline=[]
        for candidate in ordered:
            if not any(all(a<=b for a,b in zip(p["size"],candidate["size"])) for p in skyline):skyline.append(candidate)
        states[mask]=skyline
    # Build useful complete layouts before bounded subset search. Previously a
    # timeout before the final mask fell back to a tall stack of unrelated
    # minimum-volume patterns, losing all work on external proportions.
    complete=[]
    orders=[list(range(count)),sorted(range(count),key=lambda i:-min(math.prod(p["size"]) for p in states[1<<i]))]
    for order in orders:
        beam=states[1<<order[0]]
        for index in order[1:]:
            pool=[]
            for left,right in product(beam,states[1<<index]):
                for axis in range(3):
                    dims=[max(a,b) for a,b in zip(left["size"],right["size"])];dims[axis]=left["size"][axis]+right["size"][axis]
                    pool.append({"size":dims,"axis":axis,"children":[left,right]})
            unique={}
            for p in sorted(pool,key=lambda p:math.prod(v+2*(wall+foam) for v in p["size"])):unique.setdefault(tuple(p["size"]),p)
            beam=list(unique.values())[:32]
        complete.extend(beam)
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
    for root in [*complete,*states.get((1<<count)-1,[])]:
        dims=[math.ceil(v/increment-1e-9)*increment for v in root["size"]]
        leaves=[];expand(root,[foam]*3,dims,leaves)
        distinct=len({carton_size_key(l["external_mm"]) for l in leaves})
        if distinct > max_types:
            continue
        external=[math.ceil((v+2*(wall+foam)+(reserve if k==2 else 0))/increment-1e-9)*increment
                  for k,v in enumerate(dims)]
        candidates.append({"leaves":leaves,"block_mm":dims,"external_mm":external,
                           "volume_mm3":math.prod(external),"distinct_carton_sizes":distinct})
    # A procurement-friendly fallback and competing construction: all cartons
    # use one common size and form an exact integer grid. Select each module's
    # best fitting pattern independently for a candidate cell footprint.
    widths=sorted({p["external_mm"][0] for m in modules for p in m["patterns"]})
    depths=sorted({p["external_mm"][1] for m in modules for p in m["patterns"]})
    def sampled(values):
        return values if len(values)<=28 else [values[round(i*(len(values)-1)/27)] for i in range(28)]
    for width,depth in product(sampled(widths),sampled(depths)):
        selected=[]
        for module in modules:
            fits=[(p["external_mm"][2],index) for index,p in enumerate(module["patterns"])
                  if p["external_mm"][0]<=width and p["external_mm"][1]<=depth]
            if not fits:break
            selected.append(min(fits))
        if len(selected)!=count:continue
        height=max(h for h,_ in selected)
        cell=[math.ceil(v/increment-1e-9)*increment for v in (width,depth,height)]
        for nx in range(1,count+1):
            if count%nx:continue
            for ny in range(1,count//nx+1):
                if count%(nx*ny):continue
                nz=count//(nx*ny);dims=[cell[0]*nx,cell[1]*ny,cell[2]*nz]
                external=[math.ceil((v+2*(wall+foam)+(reserve if k==2 else 0))/increment-1e-9)*increment for k,v in enumerate(dims)]
                leaves=[]
                for index,(_,pattern) in enumerate(selected):
                    position=[index%nx*cell[0]+foam,(index//nx)%ny*cell[1]+foam,index//(nx*ny)*cell[2]+foam]
                    leaves.append({"module":index,"pattern":pattern,"position_mm":position,"external_mm":cell.copy()})
                candidates.append({"leaves":leaves,"block_mm":dims,"external_mm":external,
                                   "volume_mm3":math.prod(external),"distinct_carton_sizes":1,"construction":"uniform_carton_grid"})
    candidates.sort(key=lambda c:(c["volume_mm3"],c["distinct_carton_sizes"]))
    return {"candidate":candidates[0] if candidates else None,"alternatives":candidates[:12],
            "elapsed_seconds":perf_counter()-started,"reference_used":False,"spacers":0}
