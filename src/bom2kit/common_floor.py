"""Footprint-first family cartons with individual stable-floor operations.

Source-derived footprints precede allocation. A bounded beam packs partial
floors at several stable heights, then a one-dimensional DP rounds carton
heights upward to a limited number of purchasing sizes. No reference geometry
or source-specific recipe is consumed.
"""
from collections import defaultdict
from copy import deepcopy
from itertools import product
import math
from time import perf_counter

from .strip_packing import pack_strip


def quantize_heights(heights, maximum_types):
    """Minimum sum of upward-rounded heights using at most K distinct values."""
    ordered = sorted(enumerate(heights), key=lambda pair: pair[1])
    n = len(ordered)
    states = {(0, 0): (0, [])}
    for k in range(1, min(maximum_types, n) + 1):
        for end in range(k, n + 1):
            alternatives = []
            for start in range(k - 1, end):
                if (k - 1, start) not in states:
                    continue
                cost, groups = states[k - 1, start]
                alternatives.append((cost + (end-start)*ordered[end-1][1], groups + [(start, end)]))
            states[k, end] = min(alternatives, key=lambda entry: entry[0])
    _, groups = min((states[k, n] for k in range(1, min(maximum_types, n)+1)), key=lambda entry: entry[0])
    result = [0]*n
    for start, end in groups:
        for index in range(start, end):
            result[ordered[index][0]] = ordered[end-1][1]
    return result


def _layer_options(pending, options, footprint, padding, wall, gap, border, access_lane):
    import numpy as np
    width, depth = [v-2*(wall+border) for v in footprint]
    if min(width, depth) <= 0:
        return []
    extra = max(0., access_lane-gap)
    heights = sorted({round(p['dimensions_mm'][2], 6) for i in pending for p in options[i['id']]})
    # Preserve all distinct source heights when small; bound round-part facets.
    if len(heights) > 18:
        heights = sorted({heights[round(i*(len(heights)-1)/17)] for i in range(18)})
    patterns = []
    seen = set()
    for height in heights:
        units = []; choices = {}
        for item in pending:
            permitted = [(j, p) for j, p in enumerate(options[item['id']]) if p['dimensions_mm'][2] <= height+1e-5]
            if not permitted:
                continue
            index, pose = min(permitted, key=lambda pair: math.prod(pair[1]['dimensions_mm'][:2]))
            dims = [v+2*padding for v in pose['dimensions_mm']]
            choices[item['id']] = (index, pose, dims)
            for uid in item['packing_unit_ids']:
                units.append({'item_id': item['id'], 'unit_id': uid, 'dimensions': dims,
                              'orientations': [((0,1,2),(dims[0],dims[1]+extra,dims[2])),
                                               ((1,0,2),(dims[1],dims[0]+extra,dims[2]))]})
        if not units:
            continue
        for mode,order in (('short_side','area'),('area','area'),('short_side','height')):
            ordered_units=(sorted(units,key=lambda u:(-u['dimensions'][2],-math.prod(u['dimensions'][:2]),u['unit_id']))
                           if order=='height' else units)
            packed = pack_strip(ordered_units, width, height+2*padding+1e-5, gap, depth=depth+extra,
                                allow_partial=True, placement_score=mode,item_order='input' if order=='height' else order)
            if not packed or not packed['placements']:
                continue
            signature = tuple(sorted(p['unit_id'] for p in packed['placements']))
            actual_height = max(choices[p['item_id']][2][2] for p in packed['placements'])
            key = (signature, round(actual_height, 5))
            if key in seen:
                continue
            seen.add(key); placements = []
            for p in packed['placements']:
                index, pose, dims = choices[p['item_id']]
                transform = np.asarray(pose['transform']).copy()
                transform[:3,3] += padding
                size = dims.copy()
                if p['rotation'][0] == 1:
                    yaw = np.eye(4); yaw[:2,:2] = [[0,-1],[1,0]]; yaw[0,3] = dims[1]
                    transform = yaw @ transform; size = [dims[1],dims[0],dims[2]]
                position = np.asarray(p['position_mm']) + [border,border,0]
                transform[:3,3] += position
                placements.append({'item_id':p['item_id'],'unit_id':p['unit_id'],
                                   'transform':transform.tolist(),'stable_option':index,
                                   'envelope_position_mm':position.tolist(),'envelope_dimensions_mm':size})
            patterns.append({'external_mm':[*footprint,math.ceil(actual_height+2*wall-1e-8)],
                             'placements':placements,'method':'common_footprint_stable_floor',
                             'preassemblies':0,'protective_separators':[], 'access_lane_mm':access_lane})
    return patterns


def family_floors(items, options, footprint, policy, *, maximum_cartons=5, gap=.2,
                  border=9, access_lane=6.4, beam_width=8, seconds=5):
    """Keep alternative complete family allocations for several carton counts."""
    started = perf_counter(); wall = policy['carton']['inner_wall_mm']; padding = policy['item_padding_mm']
    initial = [{**deepcopy(i), 'packing_unit_ids':[f"{i['id']}#{k+1}" for k in range(i['quantity'])]} for i in items]
    unit_volume = {i['id']:min(math.prod(v+2*padding for v in p['dimensions_mm']) for p in options[i['id']]) for i in items}
    cavity_area = math.prod(v-2*(wall+border) for v in footprint)
    beam = [(0., [], initial)]; completed = []
    cache = {}
    for count in range(1, maximum_cartons+1):
        next_states = []
        for used_height, layers, pending in beam:
            key = tuple((i['id'],tuple(i['packing_unit_ids'])) for i in pending)
            if key not in cache:
                cache[key] = _layer_options(pending,options,footprint,padding,wall,gap,border,access_lane)
            for pattern in cache[key]:
                placed = {p['unit_id'] for p in pattern['placements']}
                remaining = []
                for item in pending:
                    ids = [uid for uid in item['packing_unit_ids'] if uid not in placed]
                    if ids:
                        remaining.append({**item,'quantity':len(ids),'packing_unit_ids':ids})
                state = (used_height+pattern['external_mm'][2], layers+[pattern], remaining)
                if remaining:
                    residual = sum(unit_volume[i['id']]*len(i['packing_unit_ids']) for i in remaining)/cavity_area
                    next_states.append((state[0]+residual,state))
                else:
                    completed.append(state)
        unique = {}
        for score, state in sorted(next_states, key=lambda entry:entry[0]):
            signature = tuple((i['id'],tuple(i['packing_unit_ids'])) for i in state[2])
            unique.setdefault(signature,state)
        pool=list(unique.values());beam=pool[:max(1,beam_width//2)]
        # Height-only ranking can keep peeling tiny low parts and never finish
        # within the carton cap. Preserve aggressive coverage alternatives too.
        for ranking in (lambda s:sum(unit_volume[i['id']]*len(i['packing_unit_ids']) for i in s[2]),
                        lambda s:sum(len(i['packing_unit_ids']) for i in s[2])):
            for state in sorted(pool,key=lambda s:(ranking(s),s[0]))[:max(1,beam_width//4)]:
                if state not in beam:beam.append(state)
        for state in pool:
            if len(beam)>=beam_width:break
            if state not in beam:beam.append(state)
        if not beam or (completed and perf_counter()-started>seconds):
            break
    # More cartons can reduce total height; retain that tradeoff for joint selection.
    return [min((s for s in completed if len(s[1])==n),key=lambda s:s[0])
            for n in sorted({len(s[1]) for s in completed})]


def propose_common_floors(library, options, policy, *, seconds=120, carton_counts=(3,4,5,6,7),
                          type_caps=(2,3,4), gap=.2, border=9, access_lane=6.4, progress=None):
    """Generate complete reference-free proposals; independent replay is external."""
    started=perf_counter(); families=defaultdict(list)
    from .carton_tiling import tile_modules
    for item in library['items']:
        families[policy['families'][item['id']]].append(item)
    spec=policy['carton']; padding=policy['item_padding_mm']
    volume=sum(min(math.prod(v+2*padding for v in p['dimensions_mm']) for p in options[i['id']])*i['quantity'] for i in library['items'])
    edge=volume**(1/3)
    footprints=[]
    for scale in (1.,1.15,.85,1.3,1.5):
        for ratio in (1.,1.25,1.5):
            footprints.append(tuple(math.ceil(v/5)*5 for v in (edge*scale/math.sqrt(ratio),edge*scale*math.sqrt(ratio))))
    proposals=[];diagnostics=[]
    for footprint in dict.fromkeys(footprints):
        if proposals and perf_counter()-started>=seconds:
            break
        alternatives=[]
        for family,items in sorted(families.items()):
            results=family_floors(items,options,footprint,policy,maximum_cartons=max(carton_counts)-len(families)+1,
                                 gap=gap,border=border,access_lane=access_lane,seconds=max(.1,(seconds-(perf_counter()-started))/6))
            alternatives.append((family,items,results))
            if not results:
                break
        before=len(proposals)
        if len(alternatives)==len(families) and all(a[2] for a in alternatives):
            combinations=list(product(*(a[2] for a in alternatives)))
            combinations.sort(key=lambda entries:sum(entry[0] for entry in entries))
            for combination_index,combination in enumerate(combinations):
                modules=[]
                for (family,items,_),(_,patterns,_) in zip(alternatives,combination):
                    for pattern in patterns:
                        ids={p['unit_id'] for p in pattern['placements']};subset=[]
                        for item in items:
                            members=[f"{item['id']}#{k+1}" for k in range(item['quantity']) if f"{item['id']}#{k+1}" in ids]
                            if members:subset.append({**item,'quantity':len(members),'packing_unit_ids':members})
                        crop=deepcopy(pattern)
                        crop['external_mm'][:2]=[math.ceil(max(p['envelope_position_mm'][k]+p['envelope_dimensions_mm'][k]
                            for p in pattern['placements'])+border+2*spec['inner_wall_mm']-1e-8) for k in (0,1)]
                        modules.append({'family':family,'items':subset,'patterns':[pattern,crop]})
                if len(modules) not in carton_counts:
                    continue
                for cap in type_caps:
                    heights=quantize_heights([m['patterns'][0]['external_mm'][2] for m in modules],cap)
                    z=spec['protection_mm'];leaves=[]
                    for index,h in enumerate(heights):
                        leaves.append({'module':index,'pattern':0,'position_mm':[spec['protection_mm']]*2+[z],
                                       'external_mm':[*footprint,h]});z+=h
                    block=[*footprint,sum(heights)]
                    external=[math.ceil(v+2*(spec['wall_mm']+spec['protection_mm'])+(spec['reserved_top_mm'] if k==2 else 0)) for k,v in enumerate(block)]
                    tiled={'leaves':leaves,'block_mm':block,'external_mm':external,'volume_mm3':math.prod(external),
                           'distinct_carton_sizes':len(set(heights)),'construction':'common_footprint_source_floor_beam'}
                    proposals.append((math.prod(external),modules,tiled,cap))
                    # A partial last floor need not occupy the full shared
                    # footprint. Rejoin cropped cartons into a closed block,
                    # allowing side-by-side boxes as well as a full-height stack.
                    if combination_index<3:
                        joined=tile_modules(modules,time_limit=.25,wall=spec['wall_mm'],foam=spec['protection_mm'],
                            reserve=spec['reserved_top_mm'],max_types=cap,increment=spec['dimension_increment_mm'])['candidate']
                        if joined:proposals.append((joined['volume_mm3'],modules,joined,cap))
        record={'footprint_mm':footprint,'complete_proposals':len(proposals)-before,'seconds':perf_counter()-started,
                'best_l':min((p[0]/1e6 for p in proposals),default=None)}
        diagnostics.append(record)
        if progress:progress({'stage':'common_footprint',**record})
    return proposals,diagnostics
