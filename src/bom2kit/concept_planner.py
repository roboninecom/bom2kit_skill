"""Bounded concept-first search over semantic groups and executable motifs."""
from collections import Counter, defaultdict
from copy import deepcopy
import math
from time import perf_counter

from .assembly_plan import build_assembly_plan
from .carton_tiling import tile_modules
from .concept_patterns import compose_zones, group_patterns, cohesive_carton_patterns, diverse_patterns, manual_pattern_screen
from .packing_states import declared_state
from .part_properties import describe_parts, semantic_groups, adaptive_groups, replicated_groups, coalesce_items, organization_metrics
from .practical_design import build_candidate
from .practical_geometry import stable_pose_options
from .report import fingerprint
from .retention_screen import screen_retention
from .bom import reconcile_bom


def concept_partitions(groups, pattern_sets, *, beam_width=12, max_cartons=7, profile="balanced"):
    """Most-constrained-first beam search, retaining different carton counts.

    Geometry costs are ranking estimates, not feasibility bounds. No reference
    volume, grouping, carton size or coordinate is consumed here.
    """
    if profile not in ("compact", "balanced", "organized") or beam_width < 1:
        raise ValueError("Invalid concept profile or beam width")
    def group_estimate(index):
        patterns = pattern_sets[index]
        return min(math.prod(p["external_mm"]) for p in patterns)
    estimates = [group_estimate(i) for i in range(len(groups))]
    scale = max(sum(estimates), 1.)
    family_counts=Counter(g['family'] for g in groups)
    maximum_mixing=max(1.,sum(n*(n-1)/2 for n in family_counts.values()))
    order = sorted(range(len(groups)), key=lambda i: (-min(max(p["external_mm"]) for p in pattern_sets[i]),
                                                     len(pattern_sets[i]), -estimates[i], groups[i]["id"]))
    score_cache={};module_costs={}
    def score(state):
        if state in score_cache:return score_cache[state]
        volume = 0.; mixing = 0
        for members in state:
            if members in module_costs:
                volume+=module_costs[members];mixing+=len(members)*(len(members)-1)/2
                continue
            heights = sorted({p["external_mm"][2] for i in members for p in pattern_sets[i]})
            values = []
            for height in heights:
                areas = []
                for i in members:
                    fit = [math.prod(p["external_mm"][:2]) for p in pattern_sets[i] if p["external_mm"][2] <= height+1e-7]
                    if not fit:
                        break
                    areas.append(min(fit))
                if len(areas) == len(members):
                    values.append(sum(areas)*height)
            module_costs[members]=min(values);volume += module_costs[members]
            mixing += len(members)*(len(members)-1)/2
        penalty = {"compact": .008, "balanced": .045, "organized": .18}[profile]
        # Keep cohabitation a bounded preference. Raw pair counts grow
        # quadratically with semantic granularity and otherwise swamp volume.
        score_cache[state]=volume/scale + penalty*mixing/maximum_mixing + .015*len(state)
        return score_cache[state]
    states = [()]; visited = 0
    for index in order:
        proposals = {}
        for state in states:
            choices = [i for i, members in enumerate(state) if groups[members[0]]["family"] == groups[index]["family"]]
            if len(state) < max_cartons:
                choices.append(len(state))
            for choice in choices:
                new = list(state)
                if choice == len(state):
                    new.append((index,))
                else:
                    new[choice] = tuple(sorted([*new[choice], index]))
                canonical = tuple(sorted(new)); proposals[canonical] = score(canonical); visited += 1
        ranked = sorted(proposals, key=lambda s: (proposals[s], s))
        states = []
        # Preserve an organized many-carton option instead of letting an early
        # compact score remove that architecture before all groups arrive.
        for count in sorted({len(s) for s in ranked}):
            states.extend([s for s in ranked if len(s) == count][:1])
        for state in ranked:
            if len(states) >= beam_width:
                break
            if state not in states:
                states.append(state)
    # Reconsider early assignments after all groups are known. Moving/swapping
    # whole semantic groups preserves identities and hard compatibility.
    local_started=perf_counter();repairs=[];improved=[]
    for initial in sorted(states,key=score):
        current=initial
        for _ in range(2):
            if perf_counter()-local_started>.5:break
            best=current
            for a,members in enumerate(current):
                if perf_counter()-local_started>.5:break
                for b,other in enumerate(current):
                    if a==b or groups[members[0]]['family']!=groups[other[0]]['family']:continue
                    for member in members:
                        proposals=[]
                        if len(members)>1:
                            candidate=list(current);candidate[a]=tuple(i for i in members if i!=member)
                            candidate[b]=tuple(sorted((*other,member)));proposals.append(tuple(sorted(candidate)))
                        if a<b:
                            for exchanged in other:
                                candidate=list(current)
                                candidate[a]=tuple(sorted([i for i in members if i!=member]+[exchanged]))
                                candidate[b]=tuple(sorted([i for i in other if i!=exchanged]+[member]))
                                proposals.append(tuple(sorted(candidate)))
                        for candidate in proposals:
                            if score(candidate)<score(best)-1e-10:best=candidate
            if best==current:break
            current=best
        if current!=initial:repairs.append({'before_estimate':score(initial),'after_estimate':score(current),'cartons':len(current)})
        if current not in improved:improved.append(current)
    states=list(dict.fromkeys([*improved,*states]))
    return {"states": sorted(states, key=score), "visited": visited,
            "group_order": [groups[i]["id"] for i in order], "profile": profile,
            "maximum_compatible_group_pairs":maximum_mixing,
            "semantic_reassignments":repairs,"reassignment_seconds":perf_counter()-local_started,
            "scores": [score(s) for s in sorted(states, key=score)]}


def _concept_frontier(results):
    def values(r):
        m = r["practical"]["metrics"]; o = r["concept"]["organization"]
        return (m["external_volume_l"], m["cartons"], m["carton_types"],
                o["mixed_group_pairs"], o["additional_spatial_fragments"],
                m["source_and_contact_sheet_placements"], m["additional_sku_orientations"])
    return [r for i, r in enumerate(results) if not any(i != j and all(a <= b for a, b in zip(values(other), values(r)))
            and any(a < b for a, b in zip(values(other), values(r))) for j, other in enumerate(results))]


def failed_cartons(proposal, result=None, error=None):
    """Map an observed validation failure to the affected source carton only."""
    import ast
    ids=set()
    if result is not None:
        for failure in result['practical']['hand_access'].get('failures',[]):
            if failure.get('carton_id'):ids.add(failure['carton_id'])
        for part in result['practical']['support'].get('parts',[]):
            if part.get('valid') is False:
                uid=part.get('unit_id')
                ids.update(m['id'] for m in result['logistics']['modules'] if uid in m['unit_ids'])
        # Some support failures abort before individual records are emitted.
        for message in result['practical']['support'].get('errors',[]):
            ids.update(m['id'] for m in result['logistics']['modules'] if any(message.startswith(uid+':') for uid in m['unit_ids']))
    if error and str(error).startswith('Regular carton hierarchy failed: '):
        try:
            certificate=ast.literal_eval(str(error).split(': ',1)[1])
            ids.update(f'module-{i}' for i,c in enumerate(certificate.get('inner',[]),1) if not c['valid'])
        except (ValueError,SyntaxError,KeyError):
            pass
    leaves=sorted(proposal['tiled']['leaves'],key=lambda l:(l['position_mm'][2],l['position_mm'][0]))
    return {leaf['module'] for i,leaf in enumerate(leaves,1) if f'module-{i}' in ids}


def repair_concept(proposal, failed, options, policy, *, hand_border, finger_radius,rejected=None,individual=False):
    """Keep unaffected arrangements; regenerate only failed groups with safe rows.

    The unchanged original-CAD/support/finger checks decide acceptance. This
    function merely proposes a repair; it never changes a validation threshold.
    """
    if not failed:return None
    modules=deepcopy(proposal['modules']);spec=policy['carton']
    lane=max(6.4,2*finger_radius+.4-2*policy['item_padding_mm'])
    blocked={}
    if individual and rejected is not None:
        ordered=sorted(proposal['tiled']['leaves'],key=lambda l:(l['position_mm'][2],l['position_mm'][0]))
        for f in rejected['practical']['hand_access'].get('failures',[]):
            for i,leaf in enumerate(ordered,1):
                if f.get('carton_id')==f'module-{i}':blocked[leaf['module']]=f.get('unresolved_units',[])
    for leaf in proposal['tiled']['leaves']:
        index=leaf['module']
        if index not in failed:
            modules[index]['patterns']=[deepcopy(proposal['modules'][index]['patterns'][leaf['pattern']])]
    for index in failed:
        if individual and blocked.get(index):
            from .regular_patterns import floor_patterns
            labels={i['id']:g.get('semantic_parent',g['id']) for g in modules[index]['semantic_groups'] for i in g['items']}
            modules[index]['patterns']=diverse_patterns([p for order in ('group','area') for p in
                floor_patterns(modules[index]['items'],options,policy['item_padding_mm'],spec['inner_wall_mm'],
                    seconds=.5,hand_border=hand_border,gap=spec['gap_mm'],access_lane_mm=lane,
                    access_units=blocked[index],unit_access_margin=max(0.,2*finger_radius+.2-policy['item_padding_mm']),
                    semantic_labels=labels,semantic_order=order)['patterns']],24)
        else:
            modules[index]['patterns']=cohesive_carton_patterns(modules[index]['semantic_groups'],options,policy,
                seconds=1.,mode='rows',hand_border=max(hand_border,2*finger_radius+.2-policy['item_padding_mm']),
                access_lane=lane,packing_gap=lane)
    candidate=tile_modules(modules,time_limit=.4,wall=spec['wall_mm'],foam=spec['protection_mm'],
        reserve=spec['reserved_top_mm'],max_types=proposal['type_cap'],increment=spec['dimension_increment_mm'])['candidate']
    if candidate is None:return None
    return {**proposal,'modules':modules,'tiled':candidate,'local_repair':{'changed_module_indices':sorted(failed),
        'unchanged_module_indices':sorted(set(range(len(modules)))-failed),
        'method':'blocked_unit_access_margins' if individual else 'cohesive_rows_with_access_margin',
        'blocked_units':blocked,
        'finger_radius_mm':finger_radius,'thresholds_relaxed':False}}


def refine_concept(proposal, options, policy, *, seconds=15., hand_border=7.2,access_lane=6.4,minimum_sheet_side=10.):
    """Feed generated outer-block footprints back into the same semantic groups."""
    started=perf_counter();current=deepcopy(proposal);rounds=[];spec=policy['carton']
    for iteration in range(3):
        if perf_counter()-started>=seconds:break
        modules=deepcopy(current['modules']);changed=0
        for leaf in current['tiled']['leaves']:
            index=leaf['module'];module=modules[index]
            selected=current['modules'][index]['patterns'][leaf['pattern']]
            module['patterns']=[deepcopy(selected)]
            remaining=seconds-(perf_counter()-started)
            if remaining<=0:continue
            try:
                new=cohesive_carton_patterns(module['semantic_groups'],options,policy,
                    seconds=min(.5,remaining),mode=proposal['motif_mode'],hand_border=hand_border,
                    access_lane=access_lane,
                    target_footprints=[leaf['external_mm'][:2]],minimum_sheet_side=minimum_sheet_side)
                new=[p for p in new if manual_pattern_screen(p,minimum_sheet_side)['valid']]
                module['patterns'].extend(new);changed+=len(new)
            except ValueError:
                pass
        candidate=tile_modules(modules,time_limit=.25,wall=spec['wall_mm'],foam=spec['protection_mm'],
            reserve=spec['reserved_top_mm'],max_types=proposal['type_cap'],increment=spec['dimension_increment_mm'])['candidate']
        rounds.append({'iteration':iteration+1,'patterns_added':changed,
                       'before_l':current['tiled']['volume_mm3']/1e6,'after_l':candidate['volume_mm3']/1e6 if candidate else None})
        if candidate is None or candidate['volume_mm3']>=current['tiled']['volume_mm3']-1e-6:break
        current={**current,'modules':modules,'tiled':candidate}
    current['joint_refinement']={'seconds':perf_counter()-started,'rounds':rounds,'reference_used':False,
                                 'source':'Footprints generated by this invocation only; semantic membership retained'}
    return current


def refine_source_surfaces(proposal, options, policy, *, seconds=60., hand_border=7.2,minimum_sheet_side=10.):
    """Try compact, source-supported 3D arrangements within generated concepts.

    No external recipe is loaded. Compatible-family support and individual insertion
    remain required; a successful proposal still needs the full independent replay.
    """
    from .source_surfaces import propose
    started=perf_counter();modules=deepcopy(proposal['modules']);diagnostics=[];spec=policy['carton']
    leaves=sorted(proposal['tiled']['leaves'],key=lambda l:-math.prod(l['external_mm']))
    for leaf in leaves:
        module=modules[leaf['module']]
        selected=proposal['modules'][leaf['module']]['patterns'][leaf['pattern']]
        module['patterns']=[deepcopy(selected)]
        labels={i['id']:g.get('semantic_parent',g['id']) for g in module['semantic_groups'] for i in g['items']}
        # A height cap inherited from a low floor layout can accidentally remove
        # the tall stable poses that make a smaller floor possible. Derive the
        # alternate cap from the sources, and explicitly explore footprint-first
        # placement rather than assuming a low first placement is globally best.
        upright_height=max(min(options[i['id']],key=lambda p:math.prod(p['dimensions_mm'][:2]))['dimensions_mm'][2]
                           for i in module['items'])+2*policy['item_padding_mm']
        for factor,objective in ((.85,'volume'),(.7,'footprint'),(1.,'volume')):
            remaining=seconds-(perf_counter()-started)
            if remaining<=0:break
            footprint=[math.ceil(v*factor) for v in selected['external_mm'][:2]]
            generated=propose(module['items'],options,footprint,policy['item_padding_mm'],spec['inner_wall_mm'],
                gap=spec['gap_mm'],border=hand_border,seconds=min(8.,remaining),
                max_height=max(selected['external_mm'][2]*1.5,upright_height),objective=objective,semantic_labels=labels,compact_voids=True,
                minimum_sheet_side=minimum_sheet_side)
            diagnostics.append({'module':leaf['module'],**{k:v for k,v in generated.items() if k!='pattern'}})
            if generated['status']=='complete_source_surface_proposal':
                pattern=generated['pattern']
                material_check=manual_pattern_screen(pattern,minimum_sheet_side)
                diagnostics[-1]['manual_material_screen']=material_check
                if not material_check['valid']:continue
                pattern['semantic_zones']=deepcopy(selected.get('semantic_zones',[]))
                pattern['motif_operations']=[{'action':'place_on_verified_source_surface',
                    'materials':'Enumerated protective contact sheets; retain source packing states',
                    'instruction':'Insert each original unit in the independently verified support order.'}]
                module['patterns'].append(pattern)
    candidate=tile_modules(modules,time_limit=.5,wall=spec['wall_mm'],foam=spec['protection_mm'],
        reserve=spec['reserved_top_mm'],max_types=proposal['type_cap'],increment=spec['dimension_increment_mm'])['candidate']
    result=deepcopy(proposal)
    if candidate and candidate['volume_mm3']<proposal['tiled']['volume_mm3']-1e-6:
        result.update(modules=modules,tiled=candidate)
    result['surface_refinement']={'seconds':perf_counter()-started,'proposals':diagnostics,
                                  'reference_used':False,'thresholds_relaxed':False}
    return result


def refine_irregular_floors(proposal,options,policy,*,executable,seconds=60.,hand_border=7.2,access_lane=6.4):
    """Explore concave source outlines within generated compatible cartons."""
    from .irregular_floor import propose
    started=perf_counter();modules=deepcopy(proposal['modules']);spec=policy['carton'];diagnostics=[]
    for leaf in sorted(proposal['tiled']['leaves'],key=lambda l:-math.prod(l['external_mm'])):
        module=modules[leaf['module']];selected=module['patterns'][leaf['pattern']]
        seeds=[p for p in module['patterns'] if p.get('stable_sku_orientations') and
               not p.get('protective_separators') and not p.get('individual_floor_pairs') and not p.get('supported_pairs')]
        module['patterns']=[deepcopy(selected)]
        if not any(declared_state(i)['kind']=='source_part' for i in module['items']):continue
        if not seeds:
            seeds=cohesive_carton_patterns(module['semantic_groups'],options,policy,seconds=.2,mode='rows',hand_border=hand_border,access_lane=access_lane)
        chosen=[]
        for key in (lambda p:math.prod(p['external_mm']),lambda p:math.prod(p['external_mm'][:2])):
            seed=min(seeds,key=key)
            if seed not in chosen:chosen.append(seed)
        for seed in chosen:
            remaining=seconds-(perf_counter()-started)
            if remaining<=0:break
            generated=propose(module['items'],options,seed,policy['item_padding_mm'],spec['inner_wall_mm'],
                executable=executable,time_limit=min(10.,remaining),gap=spec['gap_mm'],hand_border=hand_border,
                increment=spec['dimension_increment_mm'],access_lane_mm=access_lane)
            diagnostics.append({'module':leaf['module'],**{k:v for k,v in generated.items() if k!='pattern'}})
            if generated['status']=='validated_planar_proposal':
                pattern=generated['pattern'];pattern['semantic_zones']=deepcopy(selected.get('semantic_zones',[]))
                pattern['motif_operations']=[{'action':'place_individual_contour_floor',
                    'materials':'Retained source protection and floor liner',
                    'instruction':'Place each original unit in the independently checked sequence; inspect type organization.'}]
                module['patterns'].append(pattern)
    candidate=tile_modules(modules,time_limit=.5,wall=spec['wall_mm'],foam=spec['protection_mm'],
        reserve=spec['reserved_top_mm'],max_types=proposal['type_cap'],increment=spec['dimension_increment_mm'])['candidate']
    result=deepcopy(proposal)
    if candidate and candidate['volume_mm3']<proposal['tiled']['volume_mm3']-1e-6:result.update(modules=modules,tiled=candidate)
    result['irregular_refinement']={'seconds':perf_counter()-started,'proposals':diagnostics,
        'reference_used':False,'grouping_constraint':'Hard compatible families; type adjacency measured after placement'}
    return result


def design_concepts(library, policy, bom, *, cache=None, annotations=None, seconds=180.,
                    beam_width=12, carton_counts=(3, 4, 5, 6, 7), type_caps=(3, 4, 7),
                    motif_modes=("rows", "stacks"), grouping_modes=("assembly",),
                    max_replays=6, hand_border=7.2, finger_radius=4., progress=None, callback=None,
                    placement_style="zones",repair_budget=60.,proposal_callback=None,refinement_budget=45.,surface_budget=0.,access_lane=6.4,preserve_contact_faces=False,minimum_sheet_side=10.,irregular_executable=None,irregular_budget=0.):
    started = perf_counter()
    if (not math.isfinite(seconds) or seconds <= 0 or beam_width < 1 or max_replays < 1
        or any(not math.isfinite(v) or v<0 for v in (repair_budget,refinement_budget,surface_budget,irregular_budget,hand_border,access_lane,minimum_sheet_side))):
        raise ValueError("Positive finite budgets required")
    if not carton_counts or min(carton_counts) < 1 or max(carton_counts) > 7 or not type_caps or min(type_caps) < 1:
        raise ValueError("Invalid carton/type limits")
    if not motif_modes or any(m not in ("rows", "stacks", "nesting", "alternating", "hybrid") for m in motif_modes):
        raise ValueError("Unknown motif mode")
    if placement_style not in ('zones','cohesive','portfolio'):
        raise ValueError('Unknown concept placement style')
    if policy.get("allow_all_rotations") is not True or policy["item_padding_mm"] <= 0:
        raise ValueError("Original rotation policy and positive protection required")
    if set(policy["families"]) != {i["id"] for i in library["items"]}:
        raise ValueError("Complete compatibility policy required")
    if not reconcile_bom(bom, library)["complete"]:
        raise ValueError("Incomplete source BOM")
    if any(not declared_state(i).get("eligible_for_primary_comparison", False) for i in library["items"]):
        raise ValueError("Research-only packing states cannot enter the primary comparison")
    options = {i["id"]: stable_pose_options(i, cache=cache,include_projection=False,
               maximum=12 if preserve_contact_faces and declared_state(i)['kind']=='source_part' else 8,
               preserve_faces=preserve_contact_faces and declared_state(i)['kind']=='source_part') for i in library["items"]}
    evidence = describe_parts(library, policy, options, annotations); cards = evidence["cards"]
    preparation = perf_counter()-started; spec = policy["carton"]
    if progress:
        progress({"stage": "properties_prepared", "seconds": preparation, "source_skus": len(cards)})
    proposals = []; generation = []; patterns_cache = {}; motif_cache = {}; signatures = set()
    search_start = perf_counter()
    for grouping_mode in grouping_modes:
        groups = (replicated_groups(library,cards,options,policy) if grouping_mode=='replicated' else
                  adaptive_groups(library,cards,options,policy,base_mode='type' if grouping_mode=='adaptive_type' else 'assembly')
                  if grouping_mode in ('adaptive','adaptive_type') else semantic_groups(library,cards,grouping_mode))
        for group in groups:
            group['nesting_affinities']={i['id']:[f'{field}:{cards[i["id"]][field]["value"]}'
                for field in ('part_type','assembly') if cards[i['id']][field]['value'] not in ('unknown','unclassified')]
                for i in group['items']}
        for mode in motif_modes:
            group_sets = []
            for group in groups:
                generated = group_patterns(group, options, policy, seconds=1.5, mode=mode, cache=motif_cache,minimum_sheet_side=minimum_sheet_side)
                if not generated["patterns"]:
                    raise ValueError("No complete source-derived semantic group pattern")
                group_sets.append(generated["patterns"])
                if progress:
                    progress({"stage": "group_motifs", "group": group["id"], "mode": mode,
                              "patterns": len(generated["patterns"]), "seconds": perf_counter()-started})
            for profile in ("compact", "balanced", "organized"):
                beam = concept_partitions(groups, group_sets, beam_width=beam_width, max_cartons=max(carton_counts), profile=profile)
                generation.append({k: v for k, v in beam.items() if k != "states"})
                for state in beam["states"]:
                    if len(state) not in carton_counts:
                        continue
                    signature = (grouping_mode, mode, state)
                    if signature in signatures:
                        continue
                    signatures.add(signature); modules = []
                    for members in state:
                        key = (grouping_mode, mode, members, hand_border, placement_style)
                        if key not in patterns_cache:
                            zones = [{"id": groups[i]["id"], "patterns": group_sets[i]} for i in members]
                            patterns=[]
                            if placement_style in ('zones','portfolio'):
                                patterns.extend(compose_zones(zones, spec["inner_wall_mm"], gap=spec["gap_mm"],
                                                              hand_border=hand_border, access_lane=access_lane,
                                                              increment=spec["dimension_increment_mm"], seconds=.5))
                            if placement_style in ('cohesive','portfolio'):
                                patterns.extend(cohesive_carton_patterns([groups[i] for i in members],options,policy,
                                                                        seconds=.7,mode=mode,hand_border=hand_border,access_lane=access_lane,minimum_sheet_side=minimum_sheet_side))
                            patterns=[p for p in patterns if manual_pattern_screen(p,minimum_sheet_side)['valid']]
                            if not patterns:
                                patterns=cohesive_carton_patterns([groups[i] for i in members],options,policy,
                                    seconds=.5,mode='rows',hand_border=hand_border,access_lane=access_lane)
                            patterns_cache[key]=diverse_patterns(patterns,16)
                        modules.append({"family": groups[members[0]]["family"],
                                        "items": coalesce_items([item for i in members for item in groups[i]["items"]]),
                                        "semantic_groups":[deepcopy(groups[i]) for i in members],
                                        "patterns": patterns_cache[key], "semantic_members": [groups[i]["id"] for i in members]})
                    if any(not m["patterns"] for m in modules):
                        continue
                    for cap in type_caps:
                        tiling = tile_modules(modules, time_limit=.2, wall=spec["wall_mm"], foam=spec["protection_mm"],
                                              reserve=spec["reserved_top_mm"], max_types=cap, increment=spec["dimension_increment_mm"])
                        if tiling["candidate"]:
                            candidate = tiling["candidate"]
                            proposals.append({"modules": modules, "tiled": candidate, "type_cap": cap,
                                              "grouping_mode": grouping_mode, "motif_mode": mode, "profile": profile,
                                              "mixing": sum(len(m["semantic_members"])*(len(m["semantic_members"])-1)//2 for m in modules)})
                    if proposals and perf_counter()-search_start > seconds*.8:
                        break
                if proposals and perf_counter()-search_start > seconds*.8:
                    break
            if proposals and perf_counter()-search_start > seconds*.8:
                break
    search_seconds = perf_counter()-search_start
    # Deduplicate final geometry and retain multiple organization/box-count concepts.
    unique = {}
    for p in proposals:
        key = fingerprint([p["tiled"], [p["modules"][l["module"]]["patterns"][l["pattern"]] for l in p["tiled"]["leaves"]]])
        unique.setdefault(key, p)
    ranked = sorted(unique.values(), key=lambda p: p["tiled"]["volume_mm3"])
    queue = []
    if ranked:
        queue.append(ranked[0])
        organized = min(ranked, key=lambda p: (p["mixing"], p["tiled"]["volume_mm3"]))
        if organized not in queue:
            queue.append(organized)
        for count in carton_counts:
            choices = [p for p in ranked if len(p["modules"]) == count]
            if choices and choices[0] not in queue:
                queue.append(choices[0])
        queue.extend(p for p in ranked if p not in queue)
    results = []; plans = {}; trials = []; replay_start = perf_counter();repair_used=0.;refinement_used=0.;surface_used=0.;irregular_used=0.
    for proposal in queue[:max_replays]:
        if refinement_used<refinement_budget:
            proposal=refine_concept(proposal,options,policy,seconds=min(15.,refinement_budget-refinement_used),hand_border=hand_border,access_lane=access_lane,minimum_sheet_side=minimum_sheet_side)
            refinement_used+=proposal['joint_refinement']['seconds']
        fallback_proposal=deepcopy(proposal)
        if irregular_executable and irregular_used<irregular_budget:
            proposal=refine_irregular_floors(proposal,options,policy,executable=irregular_executable,
                seconds=min(60.,irregular_budget-irregular_used),hand_border=hand_border,access_lane=access_lane)
            irregular_used+=proposal['irregular_refinement']['seconds']
        if surface_used<surface_budget:
            proposal=refine_source_surfaces(proposal,options,policy,seconds=min(60.,surface_budget-surface_used),hand_border=hand_border,minimum_sheet_side=minimum_sheet_side)
            surface_used+=proposal['surface_refinement']['seconds']
        if proposal_callback:
            proposal_callback(proposal)
        record = {"volume_l": proposal["tiled"]["volume_mm3"]/1e6, "cartons": len(proposal["modules"]),
                  "grouping_mode": proposal["grouping_mode"], "motif_mode": proposal["motif_mode"],
                  "estimated_mixed_group_pairs": proposal["mixing"]}
        if 'joint_refinement' in proposal:record['joint_refinement']=proposal['joint_refinement']
        if 'surface_refinement' in proposal:record['surface_refinement']=proposal['surface_refinement']
        if 'irregular_refinement' in proposal:record['irregular_refinement']=proposal['irregular_refinement']
        local_policy = deepcopy(policy); local_policy["max_inner_cartons"] = max(carton_counts); local_policy["max_carton_types"] = proposal["type_cap"]
        try:
            result=None;failure=None
            try:
                result = build_candidate(library, local_policy, proposal["modules"], proposal["tiled"], finger_radius=finger_radius)
            except ValueError as error:
                failure=error
            if (failure or not result['practical']['valid']) and repair_used<repair_budget:
                indices=failed_cartons(proposal,result,failure)
                if indices:
                    repair_start=perf_counter()
                    record['original_rejection']={'error':str(failure) if failure else None,
                        'support':result['practical']['support'] if result else None,
                        'access':result['practical']['hand_access'] if result else None}
                    try:
                        original_proposal=proposal;original_result=result;record['repair_attempts']=[]
                        modes=(True,False) if result and result['practical']['support']['valid'] else (False,)
                        for individual in modes:
                            if repair_used+perf_counter()-repair_start>=repair_budget:break
                            repaired=repair_concept(original_proposal,indices,options,local_policy,hand_border=hand_border,
                                finger_radius=finger_radius,rejected=original_result,individual=individual)
                            if not repaired:continue
                            attempt={**repaired['local_repair'],'volume_l':repaired['tiled']['volume_mm3']/1e6}
                            record['repair_attempts'].append(attempt)
                            if proposal_callback:proposal_callback(repaired)
                            try:
                                candidate=build_candidate(library,local_policy,repaired['modules'],repaired['tiled'],finger_radius=finger_radius)
                                attempt['status']='verified' if candidate['practical']['valid'] else 'rejected'
                                result=candidate;proposal=repaired;failure=None
                                record['local_repair']=repaired['local_repair'];record['volume_l']=attempt['volume_l']
                                if candidate['practical']['valid']:break
                            except ValueError as error:
                                attempt['status']='rejected';attempt['error']=str(error)
                                if result is None:failure=error
                    finally:
                        elapsed=perf_counter()-repair_start;repair_used+=elapsed;record['repair_seconds']=elapsed
            # A speculative 3D improvement must not lose its simpler in-run
            # incumbent when source/access replay or a larger repair rejects it.
            if (any(k in record for k in ('surface_refinement','irregular_refinement')) and
                (failure or result is None or not result['practical']['valid'] or
                 proposal['tiled']['volume_mm3']>fallback_proposal['tiled']['volume_mm3']+1e-6)):
                fallback_started=perf_counter()
                try:
                    fallback=build_candidate(library,local_policy,fallback_proposal['modules'],fallback_proposal['tiled'],finger_radius=finger_radius)
                    record['surface_fallback']={'status':'verified' if fallback['practical']['valid'] else 'rejected',
                        'volume_l':fallback_proposal['tiled']['volume_mm3']/1e6}
                    if fallback['practical']['valid']:
                        result=fallback;proposal=fallback_proposal;failure=None
                        record['volume_l']=fallback_proposal['tiled']['volume_mm3']/1e6
                except ValueError as error:
                    record['surface_fallback']={'status':'rejected','error':str(error)}
                record['surface_fallback']['seconds']=perf_counter()-fallback_started
            if failure:raise failure
            if not result["practical"]["valid"]:
                record.update({"status": "rejected", "support": result["practical"]["support"], "access": result["practical"]["hand_access"]})
            else:
                result["concept"] = {"schema_version": 1, "reference_used": False,
                                     "properties_fingerprint": fingerprint(evidence),
                                     "grouping_mode": proposal["grouping_mode"], "motif_mode": proposal["motif_mode"],
                                     "organization": organization_metrics(result, cards),
                                     "assembly_organization": organization_metrics(result, cards,mode='assembly'),
                                     "manual_material_screen":manual_pattern_screen(
                                         {'protective_separators':result['practical']['protective_separators']},minimum_sheet_side),
                                     "retention_screen":screen_retention(result),"zones": []}
                if not result['concept']['manual_material_screen']['valid']:
                    raise ValueError('Manual contact-sheet dimensions failed independent final screening')
                for index, leaf in enumerate(sorted(proposal["tiled"]["leaves"], key=lambda l: (l["position_mm"][2], l["position_mm"][0])), 1):
                    pattern = proposal["modules"][leaf["module"]]["patterns"][leaf["pattern"]]
                    result["concept"]["zones"].append({"carton_id": f"module-{index}", "groups": deepcopy(pattern.get("semantic_zones", [])),
                                                        "motif_operations": deepcopy(pattern.get("motif_operations", []))})
                plan = build_assembly_plan(result, bom)
                plans[fingerprint(result)] = plan; results.append(result)
                record.update({"status": "verified", "organization": result["concept"]["organization"]})
            if callback:
                callback(result, record)
        except (ValueError, KeyError) as error:
            record.update({"status": "rejected", "error": str(error)})
        trials.append(record)
        if progress:
            progress({"stage": "concept_replay", **record})
    frontier = _concept_frontier(results)
    return {"status": "verified" if frontier else "no_verified_concept", "results": frontier,
            "assembly_plans": [plans[fingerprint(r)] for r in frontier], "properties": evidence,
            "trials": trials, "concept_generation": generation, "proposal_count": len(proposals),
            "unique_proposals": len(ranked), "preparation_seconds": preparation,
            "repair_seconds":repair_used,
            "refinement_seconds":refinement_used,
            "surface_seconds":surface_used,
            "irregular_seconds":irregular_used,
            "search_seconds": search_seconds, "replay_seconds": perf_counter()-replay_start,
            "seconds": perf_counter()-started, "reference_used": False}
