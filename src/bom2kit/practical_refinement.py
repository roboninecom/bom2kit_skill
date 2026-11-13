"""Feed generated carton dimensions back into contents and shrink the outer block."""
from copy import deepcopy
from time import perf_counter

from .carton_tiling import tile_modules
from .regular_patterns import floor_patterns


def choose_repacked_block(modules, tiled, replacements, spec, cap, *, seconds=.5):
    """Compare original motifs with floor repairs at whole-carton-block scope.

    Fitting inside an expanded leaf is insufficient to replace its source
    pattern: a lower repair can require a wider floor and lose after retiling.
    Keep both proposals and retain the original block if none is smaller.
    """
    selected = {leaf['module']: leaf['pattern'] for leaf in tiled['leaves']}
    alternatives = []
    for index, module in enumerate(modules):
        patterns = [deepcopy(module['patterns'][selected[index]])]
        patterns.extend(deepcopy(replacements.get(index, [])))
        alternatives.append({**deepcopy(module), 'patterns': patterns})
    compact = tile_modules(alternatives, time_limit=seconds, wall=spec['wall_mm'],
        foam=spec['protection_mm'], reserve=spec['reserved_top_mm'], max_types=cap,
        increment=spec['dimension_increment_mm'])['candidate']
    if compact and compact['volume_mm3'] < tiled['volume_mm3']-1e-6:
        return alternatives, compact
    return deepcopy(modules), deepcopy(tiled)


def refine(proposal, options, policy, *, seconds=15, gap=.2, family_gaps=None,
           hand_border=0, stack_height_factor=0,access_lane_mm=0,supported_nesting=False,
           volumetric_catalog=None):
    """Only this invocation's generated footprints are used, never a reference."""
    started=perf_counter();_,modules,tiled,cap=proposal
    modules=deepcopy(modules);tiled=deepcopy(tiled);best=proposal;rounds=[]
    spec=policy['carton'];family_gaps=family_gaps or {}
    for iteration in range(3):
        if perf_counter()-started>=seconds:break
        added=0
        for leaf in tiled['leaves']:
            if perf_counter()-started>=seconds:break
            module=modules[leaf['module']]
            # Try the actual allocated footprint plus a narrower/wider variant
            # of equal area. All resulting dimensions remain proposals.
            w,d=leaf['external_mm'][:2]
            footprints=[(w,d),(d,w)]
            for factor in (.85,1.15):footprints.append((round(w*factor),round(d/factor)))
            try:
                generated=floor_patterns(module['items'],options,policy['item_padding_mm'],spec['inner_wall_mm'],
                    gap=family_gaps.get(module['family'],gap),increment=spec['dimension_increment_mm'],
                    seconds=min(2,max(.1,seconds-(perf_counter()-started))),hand_border=hand_border,
                    target_footprints=footprints,stack_height_factor=stack_height_factor,access_lane_mm=access_lane_mm,supported_nesting=supported_nesting)
                if volumetric_catalog is not None and perf_counter()-started < seconds:
                    from .volumetric_patterns import volumetric_patterns
                    generated['patterns'].extend(volumetric_patterns(module['items'], options,
                        {**policy, '_volumetric_catalog': volumetric_catalog}, seconds=min(1., seconds-(perf_counter()-started)),
                        hand_border=hand_border, access_lane=access_lane_mm, target_footprints=footprints))
                existing={(tuple(p['external_mm']), p['method']) for p in module['patterns']}
                new=[p for p in generated['patterns'] if (tuple(p['external_mm']), p['method']) not in existing]
                module['patterns'].extend(new);added+=len(new)
            except ValueError:
                continue
        if not added:break
        trial=tile_modules(modules,time_limit=min(2,max(.05,seconds-(perf_counter()-started))),
            wall=spec['wall_mm'],foam=spec['protection_mm'],reserve=spec['reserved_top_mm'],
            max_types=cap,increment=spec['dimension_increment_mm'])['candidate']
        rounds.append({'iteration':iteration+1,'patterns_added':added,
                       'volume_l':trial['volume_mm3']/1e6 if trial else None})
        if trial is None or trial['volume_mm3']>=best[0]:break
        tiled=trial;best=(trial['volume_mm3'],deepcopy(modules),deepcopy(trial),cap)
    return best,{'seconds':perf_counter()-started,'rounds':rounds,'reference_used':False}
