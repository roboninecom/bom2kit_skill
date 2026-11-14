"""Select source-unit motifs jointly with carton footprint and height.

The catalog contains proposals, never preassembled products. Every placement
and contact sheet is expanded before the independent full-kit replay.
"""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import math
from time import perf_counter


@lru_cache(maxsize=512)
def _envelope(path, digest, frame_values):
    import numpy as np
    from .practical_geometry import load_mesh
    mesh = load_mesh({'mesh': {'path': path, 'sha256': digest}})
    mesh.apply_transform(np.asarray(frame_values).reshape(4, 4))
    return mesh.bounds[0], mesh.extents


def materialize(recipe, items, unit_ids, padding, wall):
    import numpy as np
    from .practical_geometry import load_mesh
    if len(unit_ids) != len(recipe['item_ids']) or len(set(unit_ids)) != len(unit_ids):
        raise ValueError('A motif must retain distinct original unit identities')
    placements = []
    for iid, uid, frame, digest in zip(recipe['item_ids'], unit_ids, recipe['transforms'],
                                      recipe['source_hashes'], strict=True):
        item = items[iid]
        if item['mesh']['sha256'] != digest:
            raise ValueError('Catalog source hash differs from current library')
        low, size = _envelope(item['mesh']['path'], digest, tuple(np.asarray(frame).ravel()))
        placements.append({'item_id': iid, 'unit_id': uid, 'transform': deepcopy(frame),
                           'envelope_position_mm': (low-padding).tolist(),
                           'envelope_dimensions_mm': (size+2*padding).tolist()})
    sheets = []
    for source in recipe.get('sheets', []):
        sheet = deepcopy(source)
        sheet['lower_unit_id'] = unit_ids[sheet.pop('lower_index')]
        sheet['upper_unit_id'] = unit_ids[sheet.pop('upper_index')]
        sheets.append(sheet)
    return {'external_mm': [d+2*wall for d in recipe['dimensions_mm']],
            'placements': placements, 'protective_separators': sheets,
            'source_contact_slots': bool(sheets), 'source_clearance_slots': True,
            'preassemblies': 0, 'method': 'volumetric_'+recipe['kind'],
            'motif_operations': [{'action': 'place_source_units_individually',
                                  'unit_ids': unit_ids, 'recipe_id': recipe['id'],
                                  'instruction': 'Insert each original part in the independently checked sequence.',
                                  'materials': 'Listed contact sheets' if sheets else []}]}


def cover_variants(items, recipes, *, maximum=8, options=None, padding=1.):
    """Bounded exact-coverage beam; keep volume and footprint alternatives.

    These are search costs, not claims about the final shipping volume.
    Singleton choices ensure every unit remains available to a floor fallback.
    """
    by_id = {i['id']: i for i in items}
    ids = tuple(sorted(by_id))
    available = tuple(by_id[i]['quantity'] for i in ids)
    suitable = []
    for recipe in recipes:
        counts = Counter(recipe['item_ids'])
        if set(counts) <= set(ids) and all(counts[i] <= by_id[i]['quantity'] for i in counts):
            suitable.append((recipe, tuple(counts[i] for i in ids)))
    if not suitable:
        return []
    results = []
    # Different height budgets let a taller compact motif compete with flat ones.
    heights = sorted({round(r['dimensions_mm'][2], 5) for r, _ in suitable})
    if options:
        heights = sorted(set(heights) | {round(p['dimensions_mm'][2]+2*padding, 5)
                                        for iid in ids for p in options[iid]})
        minimum_shared = max(min(p['dimensions_mm'][2]+2*padding for p in options[iid]) for iid in ids)
        heights = [h for h in heights if h >= minimum_shared-1e-5]
    if len(heights) > 16:
        # Preserve the first useful stack heights. Uniform sampling across tall
        # six-part columns used to drop ordinary two-part stacks altogether.
        heights = sorted(set(heights[:8] + [heights[round(k*(len(heights)-1)/7)] for k in range(8)]))
    for height in heights:
        single_areas = {}
        if options:
            for iid in ids:
                eligible = [math.prod(d+2*padding for d in p['dimensions_mm'][:2])
                            for p in options[iid] if p['dimensions_mm'][2]+2*padding <= height+1e-5]
                if not eligible: break
                single_areas[iid] = min(eligible)
            if len(single_areas) != len(ids): continue
        allowed = [(r, c) for r, c in suitable if r['dimensions_mm'][2] <= height+1e-5]
        touching = {index: [(r, c) for r, c in allowed if c[index]] for index in range(len(ids))}
        states = [(available, [], 0.)]
        finished = []
        while states:
            next_states = []
            for remaining, selected, score in states:
                if not any(remaining):
                    if selected: finished.append((score, selected))
                    continue
                index = next(k for k, n in enumerate(remaining) if n)
                # Leave one item for the ordinary placement path.
                rest = list(remaining); rest[index] -= 1
                next_states.append((tuple(rest), selected, score))
                for recipe, counts in touching[index]:
                    if any(a>b for a,b in zip(counts,remaining)):
                        continue
                    rest = tuple(b-a for a,b in zip(counts,remaining))
                    footprint = math.prod(recipe['dimensions_mm'][:2])
                    if single_areas:
                        # Compare at a shared carton height. Isolated pair
                        # volume penalizes useful stacks beside taller parts.
                        saving = sum(single_areas[i] for i in recipe['item_ids'])-footprint
                    else:
                        saving = recipe.get('best_separate_envelope_mm3', recipe.get('selection_reference_mm3', math.prod(recipe['dimensions_mm']))) - math.prod(recipe['dimensions_mm'])
                    next_states.append((rest, selected+[recipe], score-saving))
            unique = {}
            for state in sorted(next_states, key=lambda s: s[2]):
                signature = (state[0], tuple(sorted(r['id'] for r in state[1])))
                unique.setdefault(signature, state)
            states = list(unique.values())[:maximum]
        for score, selected in sorted(finished, key=lambda s: s[0])[:2]:
            area = max(1., sum(single_areas[i]*by_id[i]['quantity'] for i in ids)+score) if single_areas else sum(math.prod(r['dimensions_mm'][:2]) for r in selected)
            results.append((area*height, area, height, selected))
    unique = {}
    for row in sorted(results, key=lambda r: r[0]):
        unique.setdefault(tuple(sorted(r['id'] for r in row[3])), row)
    ordered = list(unique.values()); selected = []
    for key in (lambda r: r[0], lambda r: r[1], lambda r: r[2]):
        if ordered:
            best = min(ordered, key=key)
            if best not in selected: selected.append(best)
    selected.extend(r for r in ordered if r not in selected)
    return [r[3] for r in selected[:maximum]]


def volumetric_patterns(items, options, policy, *, seconds=2., hand_border=7.2,
                        access_lane=6.4, target_footprints=(), rectangle_executable=None,
                        rectangle_budget=0., rectangle_diagnostics=None):
    from .concept_patterns import repeated_rows, compose_zones, diverse_patterns
    catalog = policy.get('_volumetric_catalog')
    if not catalog:
        return []
    padding = policy['item_padding_mm']; spec = policy['carton']; wall = spec['inner_wall_mm']
    if catalog['protection'] != {'padding_mm': padding, 'gap_mm': spec['gap_mm']}:
        raise ValueError('Catalog protection differs from current policy')
    by_id = {i['id']: i for i in items}
    selections = cover_variants(items, catalog['recipes'], options=options, padding=padding)
    started = perf_counter(); patterns = []
    for selection_index, selection in enumerate(selections):
        remaining = {i['id']: list(i.get('packing_unit_ids', [f"{i['id']}#{n+1}" for n in range(i['quantity'])])) for i in items}
        zones = []
        for index, recipe in enumerate(selection):
            uids = [remaining[iid].pop(0) for iid in recipe['item_ids']]
            pattern = materialize(recipe, by_id, uids, padding, wall)
            zones.append({'id': f"motif-{index}", 'cohesion_group': tuple(sorted(set(recipe['item_ids']))), 'patterns': [pattern]})
        for iid, uids in remaining.items():
            if not uids: continue
            # Remaining copies remain individually placeable; reserving one
            # rectangle per SKU can consume more space than nesting saves.
            for uid in uids:
                item = {**by_id[iid], 'quantity': 1, 'packing_unit_ids': [uid]}
                zones.append({'id': uid, 'cohesion_group': (iid,),
                              'patterns': repeated_rows(item, options, padding, wall, gap=spec['gap_mm'])})
        patterns.extend(compose_zones(zones, wall, gap=spec['gap_mm'], hand_border=hand_border,
                                     access_lane=access_lane, target_footprints=target_footprints,
                                     directional_access=True,
                                     seconds=max(.05, seconds/max(1, len(selections)))))
        if patterns and selection_index >= min(2, len(selections)-1) and perf_counter()-started > seconds:
            break
    for p in patterns:
        p['method'] = 'volumetric_source_motifs'
        if Counter(q['item_id'] for q in p['placements']) != Counter({i['id']: i['quantity'] for i in items}):
            raise ValueError('Motif selection changed source quantities')
        if len({q['unit_id'] for q in p['placements']}) != len(p['placements']):
            raise ValueError('Motif selection duplicated a source unit')
    patterns = diverse_patterns(patterns, 20)
    if rectangle_executable and rectangle_budget > 0:
        from .motif_rectangle import polish
        tick = perf_counter()
        for pattern in sorted(patterns, key=lambda p: math.prod(p['external_mm']))[:4]:
            remaining = rectangle_budget-(perf_counter()-tick)
            if remaining <= 0: break
            changed, diagnostic = polish(pattern, rectangle_executable, wall=wall, border=hand_border,
                lane=access_lane, gap=spec['gap_mm'], seconds=min(1., remaining),
                increment=spec.get('dimension_increment_mm', 1.))
            if rectangle_diagnostics is not None: rectangle_diagnostics.append(diagnostic)
            if changed and math.prod(changed['external_mm']) < math.prod(pattern['external_mm'])-1e-6:
                patterns.append(changed)
    return diverse_patterns(patterns, 24)
