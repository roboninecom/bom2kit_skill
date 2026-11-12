"""Repeatable single-floor carton patterns from support-checked CAD poses."""
from collections import defaultdict
from copy import deepcopy
import math
from time import perf_counter

from .strip_packing import pack_strip


def compact_access_rows(placements, units, gap, access_lane, *, reach_depth=8.1):
    """Compact differing-height neighbors while preserving equal-height lanes.

    Taller parts can be removed before shorter neighbors. This is only a
    proposal: the full source-and-finger trajectory checker decides acceptance.
    Keep X positions and row ordering, solving their directed Y constraints.
    """
    by_id={u['unit_id']:u for u in units}
    compacted=[]
    for pose in sorted(placements,key=lambda p:(p['position_mm'][1],p['position_mm'][0],p['unit_id'])):
        current=deepcopy(pose);dims=by_id[pose['unit_id']]['dimensions']
        size=[dims[k] for k in pose['rotation']]
        y=0.;x=current['position_mm'][0]
        for previous,previous_size in compacted:
            px,py,_=previous['position_mm']
            # Near-disjoint X intervals still need Y separation when their
            # horizontal gap is smaller than the unchanged required clearance.
            if x+size[0]+gap<=px+1e-8 or px+previous_size[0]+gap<=x+1e-8:
                continue
            separation=gap if abs(size[2]-previous_size[2])>=reach_depth else max(gap,access_lane)
            y=max(y,py+previous_size[1]+separation)
        current['position_mm'][1]=y
        compacted.append((current,size))
    return [pose for pose,_ in compacted]


def floor_patterns(items, options, padding, wall, *, gap=.2, increment=1., seconds=10,
                   hand_border=0., target_footprints=(), stack_height_factor=0.,rectangle_executable=None,rectangle_budget=0.,floor_pair_budget=0.,access_lane_mm=0.,supported_nesting=False,
                   access_units=(),unit_access_margin=0.,semantic_labels=None,stack_overhang_fraction=.25,
                   semantic_order='group'):
    """Keep identical source SKUs in one stable orientation per pattern.

    Every original unit is placed independently on a specified floor liner.
    There are no floating shelves or rigid compound handling assumptions.
    """
    import numpy as np
    access_units=set(access_units)
    if semantic_order not in ('group','area'):raise ValueError('Unknown semantic placement order')
    if access_units and (stack_height_factor or floor_pair_budget or supported_nesting):
        raise ValueError('Individual access margins require regular individual floor units')
    if not math.isfinite(unit_access_margin) or unit_access_margin<0:raise ValueError('Invalid individual access margin')
    started = perf_counter()
    heights = sorted({p["dimensions_mm"][2] for item in items for p in options[item["id"]]})
    patterns = [];rectangle_used=0.;rectangle_diagnostics=[];pair_used=0.;supported_diagnostics=[]
    # Low-height and compact-envelope alternatives compete, independently of a reference.
    configurations = []
    for height in heights:
        choices = {}
        for item in items:
            possible = [(i, p) for i, p in enumerate(options[item["id"]]) if p["dimensions_mm"][2] <= height+1e-7]
            if not possible:
                break
            choices[item["id"]] = min(possible, key=lambda ip: (math.prod(ip[1]["dimensions_mm"][:2]), -ip[1]["contact"]["center_margin_mm"]))
        if len(choices) == len(items):
            key = tuple((iid, value[0]) for iid, value in sorted(choices.items()))
            if key not in [key for key, _ in configurations]:
                configurations.append((key, choices))
    def estimate(entry):
        choices = entry[1]
        area = sum(math.prod(v+2*padding for v in choices[i["id"]][1]["dimensions_mm"][:2])*i["quantity"] for i in items)
        height = max(p[1]["dimensions_mm"][2] for p in choices.values())+2*padding
        return (math.sqrt(area)+2*wall)**2*(height+2*wall)
    configurations.sort(key=(lambda entry:(max(p[1]['dimensions_mm'][2] for p in entry[1].values()),estimate(entry)))
                        if target_footprints else estimate)
    if configurations and not target_footprints:
        # Do not let the first isolated-volume winner consume the entire
        # budget. A taller, narrower floor can reduce six-face shipping volume
        # dramatically even when its own carton volume is slightly greater.
        seeds=[configurations[0],
               min(configurations,key=lambda entry:sum(math.prod(v+2*padding for v in entry[1][i['id']][1]['dimensions_mm'][:2])*i['quantity'] for i in items)),
               min(configurations,key=lambda entry:max(v[1]['dimensions_mm'][2] for v in entry[1].values()))]
        ordered=[]
        for entry in [*seeds,*configurations]:
            if entry not in ordered:ordered.append(entry)
        configurations=ordered
    for configuration_index,(_, choices) in enumerate(configurations):
        if patterns and configuration_index>=min(3,len(configurations)) and perf_counter()-started > seconds:
            break
        units = []
        for item in items:
            _, option = choices[item["id"]]
            dims = [v+2*padding for v in option["dimensions_mm"]]
            for copy in range(item["quantity"]):
                uid=item.get('packing_unit_ids',[f"{item['id']}#{k+1}" for k in range(item['quantity'])])[copy]
                units.append({"item_id": item["id"], "unit_id": uid,
                              "dimensions": dims, "orientations": [((0, 1, 2), tuple(dims)), ((1, 0, 2), (dims[1], dims[0], dims[2]))]})
                if semantic_labels:
                    units[-1]['cohesion_group']=semantic_labels[item['id']]
        area = sum(math.prod(u["dimensions"][:2]) for u in units)
        height = max(u["dimensions"][2] for u in units)
        expansions={u['unit_id']:{'members':[{'unit':u,'offset_mm':[0.,0.,0.]}],'separators':[]} for u in units}
        floor_pairs=[];supported_pairs=[]
        if supported_nesting:
            from .regular_cavity_pairs import make_supported_pairs
            units,expansions,supported_pairs,diagnostic=make_supported_pairs(units,choices,{i['id']:i for i in items},padding,gap,
                height*(stack_height_factor or 1.5),seconds=max(.5,min(3,seconds)))
            supported_diagnostics.append(diagnostic)
            height=max(u['dimensions'][2] for u in units);area=sum(math.prod(u['dimensions'][:2]) for u in units)
        elif stack_height_factor:
            from .regular_stacks import make_flat_columns
            units,expansions=make_flat_columns(units,choices,{i['id']:i for i in items},padding,height*stack_height_factor,
                                               max_overhang_fraction=stack_overhang_fraction)
            height=max(u['dimensions'][2] for u in units)
            area=sum(math.prod(u['dimensions'][:2]) for u in units)
        if floor_pair_budget>pair_used:
            from .regular_floor_pairs import make_floor_pairs
            pair_start=perf_counter()
            units,expansions,floor_pairs=make_floor_pairs(units,choices,{i['id']:i for i in items},padding,gap,
                                                        seconds=floor_pair_budget-pair_used,all_options=options)
            pair_used+=perf_counter()-pair_start
            height=max(u['dimensions'][2] for u in units);area=sum(math.prod(u['dimensions'][:2]) for u in units)
        by_unit={u['unit_id']:u for u in units}
        if semantic_labels:
            for unit in units:
                labels=tuple(sorted({semantic_labels[m['unit']['item_id']] for m in expansions[unit['unit_id']]['members']}))
                unit['cohesion_group']=labels
            order={label:index for index,label in enumerate(dict.fromkeys(semantic_labels[i['id']] for i in items))}
            units.sort(key=lambda u:(min(order[label] for label in u['cohesion_group']),-math.prod(u['dimensions'][:2])))
        lane_extra=max(0.,access_lane_mm-gap)
        margins={u['unit_id']:unit_access_margin if u['unit_id'] in access_units else 0. for u in units}
        packing_units=[{**u,'dimensions':[u['dimensions'][0],u['dimensions'][1]+lane_extra+2*margins[u['unit_id']],u['dimensions'][2]],
                        'orientations':[(r,(s[0],s[1]+lane_extra+2*margins[u['unit_id']],s[2])) for r,s in u['orientations']]} for u in units]
        widths = sorted({max(min(u["dimensions"][:2]) for u in units),
                         *(math.ceil(math.sqrt(area)*f/increment)*increment for f in (.6,.75,.9,1,1.15,1.35,1.6,2.))})
        widths.sort(key=lambda w:abs(math.log(w/math.sqrt(area))))
        targets = [(w-2*(wall+hand_border), d-2*(wall+hand_border)) for w,d in target_footprints]
        if not target_footprints:
            targets += [(w, None) for w in widths]
        for target_index,(width, depth) in enumerate(targets):
            if width <= 0 or (depth is not None and depth <= 0):
                continue
            for mode in (("cohesive",) if semantic_labels else ("short_side", "area", "bottom_left")):
                p = pack_strip(packing_units, width, height, gap, depth=None if depth is None else depth+lane_extra,
                               placement_score=mode, item_order="input" if semantic_labels and semantic_order=='group' else "area")
                if p is None:
                    continue
                if rectangle_executable and mode=='short_side' and rectangle_used<rectangle_budget:
                    from .packing_solver_adapter import pack_floor
                    trial=pack_floor(packing_units,p['placements'],width,executable=rectangle_executable,
                                     time_limit=min(.8,rectangle_budget-rectangle_used),gap=gap)
                    rectangle_used+=trial['elapsed_seconds']
                    rectangle_diagnostics.append({k:v for k,v in trial.items() if k not in ('placements','validation')})
                    if trial['status']=='validated_envelopes' and trial['usable_mm'][1]<p['usable_mm'][1]-1e-7:
                        p=trial
                if access_lane_mm and not stack_height_factor and not floor_pairs and not supported_pairs and not access_units:
                    p['placements']=compact_access_rows(p['placements'],units,gap,access_lane_mm)
                # A stable pose is chosen per SKU, and only horizontal quarter-turns vary.
                placements = [];separators=[]
                for q in p["placements"]:
                    yaw = np.eye(4)
                    if q["rotation"][0] == 1:
                        yaw[:2,:2] = [[0,-1],[1,0]]
                        yaw[0,3] = by_unit[q['unit_id']]['dimensions'][1]
                    shift=np.asarray(q['position_mm'])+[hand_border,hand_border+margins[q['unit_id']],0.]
                    def box_pose(origin,size):
                        low=np.asarray(origin);dimensions=list(size)
                        if q['rotation'][0]==1:
                            low=np.array([by_unit[q['unit_id']]['dimensions'][1]-origin[1]-size[1],origin[0],origin[2]])
                            dimensions=[size[1],size[0],size[2]]
                        return (low+shift).tolist(),dimensions
                    for member in expansions[q['unit_id']]['members']:
                        unit=member['unit'];option_index,option=choices[unit['item_id']]
                        local=np.asarray(member.get('transform_override',option['transform'])).copy();local[:3,3]+=np.asarray(member['offset_mm'])+padding
                        transform=yaw@local;transform[:3,3]+=shift
                        envelope_position,envelope_size=box_pose(member['offset_mm'],unit['dimensions'])
                        placements.append({'item_id':unit['item_id'],'unit_id':unit['unit_id'],
                                           'transform':transform.tolist(),'stable_option':member.get('stable_option_override',option_index),
                                           'envelope_position_mm':envelope_position,'envelope_dimensions_mm':envelope_size})
                    for sheet in expansions[q['unit_id']]['separators']:
                        origin,size=box_pose(sheet['origin_mm'],sheet['dimensions_mm'])
                        separators.append({**sheet,'origin_mm':origin,'dimensions_mm':size})
                used = [max(q["envelope_position_mm"][k]+q["envelope_dimensions_mm"][k] for q in placements) for k in range(3)]
                if access_units:
                    used[1]=max(q['envelope_position_mm'][1]+q['envelope_dimensions_mm'][1]+
                                (unit_access_margin if q['unit_id'] in access_units else 0.) for q in placements)
                used[:2] = [v+hand_border for v in used[:2]]
                external = [math.ceil((v+2*wall)/increment-1e-9)*increment for v in used]
                if depth is not None:
                    external[:2] = [width+2*(wall+hand_border),depth+2*(wall+hand_border)]
                patterns.append({"external_mm": external, "placements": placements,
                                 "method": "regular_flat_interface_stacks" if separators else "stable_single_floor", "preassemblies": 0,
                                 "protective_separators":separators,
                                 'individual_floor_pairs':floor_pairs,'source_clearance_slots':bool(floor_pairs),
                                 'supported_pairs':supported_pairs,'source_contact_slots':bool(supported_pairs),
                                 'access_lane_mm':access_lane_mm,
                                 'individual_access_units':sorted(access_units),
                                 'individual_access_margin_mm':unit_access_margin,
                                 "stable_sku_orientations": {iid: index for iid,(index,_) in choices.items()}})
            if patterns and target_index>=3 and perf_counter()-started > seconds:
                break
    if not patterns:
        raise ValueError("No complete stable-floor pattern")
    # Preserve height bands for joint carton tiling, not just isolated volume winners.
    unique = {}
    for p in sorted(patterns, key=lambda p: math.prod(p["external_mm"])):
        unique.setdefault(tuple(p["external_mm"]), p)
    ordered = list(unique.values())
    chosen = ordered[:12]
    for height in sorted({p["external_mm"][2] for p in ordered}):
        for p in [p for p in ordered if p["external_mm"][2] == height][:2]:
            if p not in chosen:
                chosen.append(p)
    return {"patterns": chosen, "elapsed_seconds": perf_counter()-started,
            'rectangle_seconds':rectangle_used,'rectangle_diagnostics':rectangle_diagnostics,'floor_pair_seconds':pair_used,
            'supported_pair_diagnostics':supported_diagnostics}


def partition_by_height(items, options, count, strategy="height"):
    """Partition whole SKUs to keep repeated components together, without recipes."""
    if not 1 <= count <= len(items):
        raise ValueError("Invalid family partition count")
    if strategy not in ('height','cost','footprint_cost','area','copies'):
        raise ValueError('Unknown family partition strategy')
    if strategy == 'copies':
        # Repeated kits can share carton patterns without trapping every copy of
        # a long component in one large carton. Source identities remain unique.
        groups=[[] for _ in range(count)];weights=[0.]*count
        ranked=sorted(items,key=lambda i:(-i['quantity'],-min(math.prod(p['dimensions_mm']) for p in options[i['id']]),i['id']))
        for item in ranked:
            assignments=defaultdict(list)
            ids=item.get('packing_unit_ids',[f"{item['id']}#{k+1}" for k in range(item['quantity'])])
            unit_weight=min(math.prod(p['dimensions_mm']) for p in options[item['id']])
            for index,uid in enumerate(ids):
                group=(index%count) if item['quantity']>=count else min(range(count),key=lambda g:(weights[g],g))
                assignments[group].append(uid);weights[group]+=unit_weight
            for group,uids in assignments.items():
                groups[group].append({**deepcopy(item),'quantity':len(uids),'packing_unit_ids':uids})
        if any(not g for g in groups):raise ValueError('Empty repeated-kit partition')
        return groups
    ranked = sorted(items, key=lambda i: (min(p["dimensions_mm"][2] for p in options[i["id"]]), i["id"]))
    if strategy=='footprint_cost':
        # A plate can share a tall layer in its narrow stable pose. Ordering only
        # by each SKU's lowest pose hides this useful family partition.
        ranked.sort(key=lambda i:(min(options[i['id']],key=lambda p:(math.prod(p['dimensions_mm'][:2]),p['dimensions_mm'][2]))['dimensions_mm'][2],i['id']))
    if strategy in ('cost','footprint_cost'):
        # Dynamic programming on source-derived height order. Volume-balanced
        # cuts mix broad flat parts with a few tall items and waste whole layers.
        costs={}
        def layer_cost(a,b):
            if (a,b) in costs:return costs[a,b]
            group=ranked[a:b];best=math.inf
            for height in sorted({p['dimensions_mm'][2] for i in group for p in options[i['id']]}):
                total=0.
                for item in group:
                    permitted=[math.prod(p['dimensions_mm'][:2]) for p in options[item['id']] if p['dimensions_mm'][2]<=height+1e-7]
                    if not permitted:break
                    total+=min(permitted)*item['quantity']
                else:best=min(best,total*height)
            costs[a,b]=best;return best
        states={(0,0):(0.,[])}
        for k in range(1,count+1):
            for end in range(k,len(ranked)+1):
                candidates=[(states[k-1,start][0]+layer_cost(start,end),states[k-1,start][1]+[(start,end)])
                            for start in range(k-1,end) if (k-1,start) in states]
                states[k,end]=min(candidates,key=lambda value:value[0])
        return [deepcopy(ranked[a:b]) for a,b in states[count,len(ranked)][1]]
    if strategy == "area":
        ranked.sort(key=lambda i: min(math.prod(p["dimensions_mm"][:2]) for p in options[i["id"]]))
    weights = [min(math.prod(p["dimensions_mm"]) for p in options[i["id"]])*i["quantity"] for i in ranked]
    prefix = [0.]
    for v in weights:
        prefix.append(prefix[-1]+v)
    cuts = [0]
    for k in range(1,count):
        candidates = range(cuts[-1]+1,len(ranked)-(count-k)+1)
        cut = min(candidates,key=lambda n: abs(prefix[n]-prefix[-1]*k/count))
        cuts.append(cut)
    cuts.append(len(ranked))
    return [deepcopy(ranked[a:b]) for a,b in zip(cuts,cuts[1:])]
