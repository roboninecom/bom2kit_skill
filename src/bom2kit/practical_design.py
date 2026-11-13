"""Reference-free regular packing with independent support and handling gates."""
from collections import defaultdict
from copy import deepcopy
from itertools import product
import math
from time import perf_counter

from .carton_tiling import tile_modules
from .practical_geometry import stable_pose_options
from .regular_patterns import floor_patterns, partition_by_height
from .report import fingerprint


def build_candidate(library, policy, modules, tiled, *, finger_radius=4.):
    """Materialize original source poses, exact cartons and counted floor liners."""
    import numpy as np
    from shapely.geometry import mapping,box
    from .protection_geometry import foam_panels, validate_foam_shell
    from .layered_design import validate_layered
    from .mesh_validation import validate_mesh_layout
    from .transport_validation import validate_transport
    from .packing_states import audit_states
    from .practical_validation import check_floor_support, check_hand_access, complexity_metrics
    started=perf_counter();timings={}
    spec = policy["carton"];wall=spec["wall_mm"];foam=spec["protection_mm"];t=spec["inner_wall_mm"]
    external = tiled["external_mm"]
    container={"inner_mm":[v-2*wall for v in external],"wall_mm":[wall]*3,
               "protection_mm":[foam]*3,"reserved_top_mm":spec["reserved_top_mm"]}
    layers, manifest, original, slots, slot_items, packaging, liners, separators = [],[],[],[],[],[],[],[]
    groups={};use_planar=False;use_source_slots=False;source_items={i['id']:i for i in library['items']}
    for index,leaf in enumerate(sorted(tiled["leaves"],key=lambda l:(l["position_mm"][2],l["position_mm"][0])),1):
        module = modules[leaf["module"]];pattern=module["patterns"][leaf["pattern"]]
        use_source_slots=use_source_slots or pattern.get('source_clearance_slots',False) or pattern.get('source_contact_slots',False)
        lid=f"module-{index}";origin=np.asarray(leaf["position_mm"])+t
        inner=[v-2*t for v in leaf["external_mm"]]
        placement_check=('source_contact' if pattern.get('source_contact_slots') else 'source_floor' if pattern.get('source_clearance_slots') else
                         'planar' if any('footprint' in p for p in pattern['placements']) else 'envelopes')
        layers.append({"id":lid,"position_mm":leaf["position_mm"],"wall_mm":t,"inner_mm":inner,
                       'placement_check':placement_check})
        members=[]
        for p in pattern["placements"]:
            use_planar = use_planar or 'footprint' in p
            transform=np.asarray(p["transform"]).copy();transform[:3,3]+=origin
            original.append({"item_id":p["item_id"],"unit_id":p["unit_id"],"transform":transform.tolist()})
            sid=f"slot-{len(slots)+1}";uid=sid+"#1"
            slot_transform=np.asarray(p['transform']).copy();slot_transform[:3,3]-=np.asarray(p['envelope_position_mm'])
            slot_items.append({"id":sid,"quantity":1,"dimensions_mm":p["envelope_dimensions_mm"],"allowed_rotations":"fixed",
                               'source_mesh':source_items[p['item_id']]['mesh'],'source_transform':slot_transform.tolist(),
                               "footprint":p.get('footprint',mapping(box(0,0,*p["envelope_dimensions_mm"][:2])))})
            slots.append({"item_id":sid,"unit_id":uid,"layer_id":lid,"rotation":[0,1,2],
                          "dimensions_mm":p["envelope_dimensions_mm"],
                          "position_mm":(origin+np.asarray(p["envelope_position_mm"])).tolist()})
            groups["assembly-"+uid]=[p["unit_id"]];members.append(p["unit_id"])
        manifest.append({"id":lid,"family":module["family"],"method":pattern["method"],
                         "external_mm":leaf["external_mm"],"position_mm":leaf["position_mm"],"unit_ids":members,
                         'source_motifs': deepcopy([operation for operation in pattern.get('motif_operations', [])
                                                   if operation.get('recipe_id') and operation.get('unit_ids')]),
                         "retention_status":"unverified","closure":"Closed carton; physical retention trial required"})
        packaging.append({"id":lid,"quantity":1,"type":"closed_rectangular_inner_carton",
                          "external_mm":leaf["external_mm"],"wall_mm":t,
                          "manufacturing_status":"Dimension specification; supplier approval pending"})
        liners.append({"id":lid+"-floor-liner","quantity":1,"type":"protective_floor_liner",
                       "carton_id":lid,"origin_mm":origin.tolist(),"dimensions_mm":[*inner[:2],policy["item_padding_mm"]],
                       "material":"EPE sheet specification; grade and performance unqualified",
                       "allowance_accounting":"Occupies existing bottom item-padding allowance, not added twice"})
        for sheet in pattern.get('protective_separators',[]):
            separators.append({**sheet,'id':f'{lid}-contact-sheet-{len(separators)+1}',
                               'quantity':1,'type':'protective_contact_sheet','carton_id':lid,
                               'origin_mm':(origin+np.asarray(sheet['origin_mm'])).tolist(),
                               'material':'EPE sheet specification; load capacity unqualified',
                               'allowance_accounting':'Occupies existing facing item-padding allowances'})
    problem={"units":"mm","container":container,"items":slot_items,"inner_wall_mm":t,"gap_mm":spec["gap_mm"]}
    if use_planar:
        problem['planar_footprints']=True
    if use_source_slots:
        problem['source_clearance_slots']=True;problem['source_padding_mm']=policy['item_padding_mm']
    layout={"placements":slots,"layers":layers,"status":"feasible"}
    hierarchy=validate_layered(problem,layout)
    timings['hierarchy_seconds']=perf_counter()-started;check_start=perf_counter()
    if not hierarchy["valid"]:raise ValueError(f"Regular carton hierarchy failed: {hierarchy}")
    panels=foam_panels(container["inner_mm"],foam)
    candidate={"input":problem,"layout":layout,"validation":hierarchy,"external_mm":external,
               "volume_mm3":math.prod(external),"packaging_bom":[*packaging,*liners,*separators,*panels,
               {"id":"outer-carton","quantity":1,"type":"closed_corrugated_outer_carton","external_mm":external,"wall_mm":wall}]}
    result={"status":"validated_mesh_envelope_baseline","input":{"units":"mm","items":deepcopy(library["items"]),
             "container":container,"clearance_mm":policy["clearance_mm"]},"layout":{"units":"mm","placements":original},
            "groups":groups,"envelope_design":{"candidate":candidate},"source_library_sha256":fingerprint(library),
            "logistics":{"policy":deepcopy(policy),"policy_hash":fingerprint(policy),"modules":manifest,
                         "foam_panels":panels,"foam_validation":validate_foam_shell(container["inner_mm"],foam,panels),
                         "spacers":[],"block_mm":tiled["block_mm"],"carton_count":len(layers),"carton_types":tiled["distinct_carton_sizes"],
                         "physical_qualification":False,"retention_verified":False,"reference_used":False},
            "practical":{"schema_version":1,"floor_liner_mm":policy["item_padding_mm"],"floor_liners":liners,
                         "protective_separators":separators,
                         "packing_state_audit":audit_states(library),"group_handling":"Individual source units only"}}
    result["validation"]=validate_mesh_layout(result["input"],result["layout"])
    timings['original_mesh_seconds']=perf_counter()-check_start;check_start=perf_counter()
    if not result["validation"]["valid"]:raise ValueError(f"Original CAD failed: {result['validation']['errors']}")
    result["logistics"]["validation"]=validate_transport(result,policy)
    if not result["logistics"]["validation"]["valid"]:raise ValueError(result["logistics"]["validation"]["errors"])
    result["practical"]["support"]=check_floor_support(result)
    timings['support_seconds']=perf_counter()-check_start;check_start=perf_counter()
    result["practical"]["hand_access"]=check_hand_access(result,radius_mm=finger_radius)
    timings['hand_access_seconds']=perf_counter()-check_start
    result['practical']['verification_seconds']=timings
    result["practical"]["metrics"]=complexity_metrics(result)
    result["practical"]["valid"]=result["practical"]["support"]["valid"] and result["practical"]["hand_access"]["valid"]
    return result


def nondominated(results):
    """Preserve operational improvements even when their exterior is larger."""
    def values(result):
        m=result["practical"]["metrics"]
        organization=m.get('organization')
        # Missing measurements must not masquerade as perfectly grouped parts.
        grouping=tuple(organization[k] for k in ('mixed_group_pairs',
            'additional_spatial_fragments','split_semantic_groups')) if organization else (math.inf,)*3
        return (*[m[k] for k in ("external_volume_l","cartons","carton_types","compound_preassemblies","split_source_skus")],
                m.get('source_and_contact_sheet_placements',m.get('total_counted_placements',0)),
                m.get('contact_sheet_sizes',0),m.get('additional_sku_orientations',0),*grouping)
    return [r for i,r in enumerate(results) if not any(j!=i and all(a<=b for a,b in zip(values(other),values(r)))
            and any(a<b for a,b in zip(values(other),values(r))) for j,other in enumerate(results))]


def design_practical(library,policy,bom,*,cache=None,time_limit=120,carton_counts=(3,4,5,6,7),type_caps=(2,3,4),
                     hand_border=8.,packing_gap=None,finger_radius=4.,max_replays=12,callback=None,cp_sat_python=None,
                     irregular_executable=None,irregular_budget=0.,family_gaps=None,progress=None,stack_height_factor=0.,refinement_budget=0.,
                     rectangle_executable=None,rectangle_budget=0.,floor_pair_budget=0.,access_lane_mm=0.,
                     common_floor_budget=0.,common_floor_only=False,supported_nesting=False,source_surface_budget=0.,access_repair_budget=0.,volumetric_catalog=None,annotations=None,
                     motif_rectangle_budget=0.):
    """Search source-derived family partitions and retain a verified Pareto set."""
    from .bom import reconcile_bom
    from .assembly_plan import build_assembly_plan
    from .packing_states import declared_state
    from .part_properties import describe_parts, check_accessory_set_cohesion, organization_metrics
    from .kitting_partition import reunite_accessory_sets
    started=perf_counter()
    if not reconcile_bom(bom,library)["complete"]:raise ValueError("Incomplete source BOM")
    if any(not declared_state(i).get('eligible_for_primary_comparison',False) for i in library['items']):
        raise ValueError('Research-only packing states cannot enter the primary practical comparison')
    if policy.get("allow_all_rotations") is not True:raise ValueError("Stable pose search requires explicitly unrestricted source rotations")
    if set(policy["families"])!={i["id"] for i in library["items"]}:raise ValueError("Complete family policy required")
    if not math.isfinite(policy['item_padding_mm']) or policy['item_padding_mm']<=0:
        raise ValueError('Practical packing requires a positive protective floor-liner allowance')
    if not math.isfinite(time_limit) or time_limit<=0:raise ValueError("Positive time limit required")
    if not carton_counts or not type_caps or not isinstance(max_replays,int) or max_replays<1:
        raise ValueError('Nonempty carton/type search and a positive replay count required')
    values=[hand_border,irregular_budget,refinement_budget,rectangle_budget,floor_pair_budget,access_lane_mm,common_floor_budget,source_surface_budget,access_repair_budget,motif_rectangle_budget]
    if packing_gap is not None:values.append(packing_gap)
    if any(not math.isfinite(v) or v<0 for v in values):raise ValueError('Finite nonnegative search parameters required')
    if common_floor_only and not common_floor_budget:raise ValueError('Common-floor-only mode requires a positive budget')
    if motif_rectangle_budget and (not rectangle_executable or volumetric_catalog is None):
        raise ValueError('Motif rectangle search requires a catalog and rectangle executable')
    if not math.isfinite(finger_radius) or finger_radius<=0:raise ValueError('Positive finite fingertip radius required')
    if any(n<1 or n>7 for n in carton_counts) or any(n<1 or n>7 for n in type_caps):raise ValueError("Invalid carton/type search limits")
    if not math.isfinite(stack_height_factor) or stack_height_factor<0:raise ValueError('Invalid stack height factor')
    if stack_height_factor and irregular_executable:raise ValueError('Stack and planar-contour modes must be evaluated separately')
    if floor_pair_budget and irregular_executable:raise ValueError('Floor pairs and projected contours require separate experiments')
    if supported_nesting and (irregular_executable or floor_pair_budget):raise ValueError('Supported cavity pairs require a separate experiment')
    # Rectangular and volumetric motifs do not use planar triangle unions.
    # Prepare them only for an explicitly requested contour backend.
    options={i["id"]:stable_pose_options(i,cache=cache,include_projection=bool(irregular_executable)) for i in library["items"]}
    properties = describe_parts(library, policy, annotations=annotations)
    preparation_seconds=perf_counter()-started
    if progress:progress({'stage':'sources_prepared','seconds':preparation_seconds,'source_skus':len(options)})
    search_start=perf_counter()
    families=defaultdict(list)
    for item in library["items"]:families[policy["families"][item["id"]]].append(item)
    family_names=sorted(families);spec=policy["carton"]
    gap=spec["gap_mm"] if packing_gap is None else max(spec["gap_mm"],packing_gap)
    family_gaps={} if family_gaps is None else family_gaps
    if set(family_gaps)-set(families) or any(not math.isfinite(v) or v<spec['gap_mm'] for v in family_gaps.values()):
        raise ValueError('Family gap overrides must preserve the declared clearance and name known families')
    patterns_cache={};cached_items={};proposals=[];attempts=[];irregular_used=0.;irregular_diagnostics=[];rectangle_used=0.;rectangle_diagnostics=[];pair_used=0.
    surface_used=0.;surface_diagnostics=[];motif_rectangle_used=0.;motif_rectangle_diagnostics=[]
    allocations=[counts for counts in product(range(1,max(carton_counts)+1),repeat=len(families))
                 if sum(counts) in carton_counts and all(c<=len(families[f]) for f,c in zip(family_names,counts))]
    group_estimates={}
    partitions={}; motif_selections={}
    def partition(family,count,strategy):
        key=(family,count,strategy)
        if key not in partitions:
            if strategy.startswith('motif_'):
                from .volumetric_patterns import cover_variants
                from .volumetric_partition import partition_with_motifs
                if family not in motif_selections:
                    motif_selections[family] = cover_variants(families[family], volumetric_catalog['recipes'],
                        options=options, padding=policy['item_padding_mm'])
                partitions[key] = partition_with_motifs(families[family], options, count,
                    volumetric_catalog['recipes'], selection_index=0 if strategy=='motif_volume' else 1,
                    padding=policy['item_padding_mm'], selections=motif_selections[family])
            else:
                partitions[key]=partition_by_height(families[family],options,count,strategy)
            partitions[key] = reunite_accessory_sets(partitions[key], properties['cards'], group_cost)
        return partitions[key]
    def group_cost(subset):
        key=tuple(sorted((i['id'],i['quantity']) for i in subset))
        if key in group_estimates:return group_estimates[key]
        costs=[]
        heights=sorted({p['dimensions_mm'][2] for i in subset for p in options[i['id']]})
        for h in heights:
            areas=[]
            for i in subset:
                possible=[math.prod(v+2*policy['item_padding_mm'] for v in p['dimensions_mm'][:2])
                          for p in options[i['id']] if p['dimensions_mm'][2]<=h+1e-7]
                if not possible:break
                areas.append(min(possible)*i['quantity'])
            if len(areas)==len(subset):
                costs.append((math.sqrt(sum(areas))+2*(spec['inner_wall_mm']+hand_border))**2*(h+2*(spec['inner_wall_mm']+policy['item_padding_mm'])))
        value=min(costs);group_estimates[key]=value;return value
    def allocation_cost(counts):
        return sum(min(sum(group_cost(s) for s in partition(f,n,strategy))
                       for strategy in ('cost','height','copies')) for f,n in zip(family_names,counts))
    if common_floor_only:allocations=[]
    else:allocations.sort(key=allocation_cost)
    if progress:progress({'stage':'partitions_ranked','seconds':perf_counter()-started,'allocations':len(allocations)})
    # Visit every requested carton count before spending the budget on variants.
    seeds=[next((c for c in allocations if sum(c)==n),None) for n in carton_counts]
    allocations=[c for c in seeds if c is not None]+[c for c in allocations if c not in seeds]
    strategies = (("motif_volume", "cost", "motif_footprint", "footprint_cost", "copies", "height", "area")
                  if volumetric_catalog is not None else ("cost", "footprint_cost", "copies", "height", "area"))
    # A catalog makes each partition more expensive. Round-robin the initial
    # counts before trying all strategies for one count; otherwise a fixed
    # budget can finish without ever proposing the requested larger counts.
    initial = [c for c in seeds if c is not None]
    scheduled = [(counts, (strategy,)) for strategy in strategies for counts in initial]
    scheduled.extend((counts, strategies) for counts in allocations if counts not in initial)
    for counts, trial_strategies in scheduled:
        if proposals and perf_counter()-search_start>time_limit*.72:break
        for strategy in trial_strategies:
            modules=[]
            for family,count in zip(family_names,counts):
                local_gap=family_gaps.get(family,gap)
                for subset in partition(family,count,strategy):
                    key=tuple(sorted((i['id'],tuple(i.get('packing_unit_ids',[f"{i['id']}#{k+1}" for k in range(i['quantity'])]))) for i in subset))
                    if key not in patterns_cache:
                        if progress:progress({'stage':'family_patterns_start','family':family,'source_skus':len(subset),'seconds':perf_counter()-started})
                        cached_items[key]=deepcopy(subset)
                        left=max(.2,time_limit*.72-(perf_counter()-search_start))
                        patterns_cache[key]=floor_patterns(subset,options,policy["item_padding_mm"],spec["inner_wall_mm"],
                            gap=local_gap,increment=spec["dimension_increment_mm"],seconds=min(1.5,left),hand_border=hand_border,
                            stack_height_factor=0.,rectangle_executable=rectangle_executable,
                            supported_nesting=False,
                            access_lane_mm=access_lane_mm,
                            rectangle_budget=min(2,max(0,rectangle_budget-rectangle_used)),
                            floor_pair_budget=0.)
                        patterns_cache[key]['regular_floor_patterns']=list(patterns_cache[key]['patterns'])
                        if volumetric_catalog is not None:
                            from .volumetric_patterns import volumetric_patterns
                            local_diagnostics = []
                            patterns_cache[key]['patterns'].extend(volumetric_patterns(subset, options,
                                {**policy, '_volumetric_catalog': volumetric_catalog}, seconds=1.,
                                hand_border=hand_border, access_lane=access_lane_mm,
                                rectangle_executable=rectangle_executable,
                                rectangle_budget=min(4., max(0., motif_rectangle_budget-motif_rectangle_used)),
                                rectangle_diagnostics=local_diagnostics))
                            motif_rectangle_used += sum(d.get('elapsed_seconds', 0.) for d in local_diagnostics)
                            motif_rectangle_diagnostics.extend(local_diagnostics)
                        if stack_height_factor or supported_nesting or floor_pair_budget>pair_used:
                            # Experimental patterns compete per carton with the
                            # regular floor; enabling stacks must not force every
                            # family into columns and discard a better incumbent.
                            alternative=floor_patterns(subset,options,policy['item_padding_mm'],spec['inner_wall_mm'],
                                gap=local_gap,increment=spec['dimension_increment_mm'],seconds=1.,hand_border=hand_border,
                                access_lane_mm=access_lane_mm,
                                stack_height_factor=stack_height_factor,supported_nesting=supported_nesting,
                                floor_pair_budget=0. if stack_height_factor else min(6,max(0.,floor_pair_budget-pair_used)))
                            pair_used+=alternative['floor_pair_seconds']
                            patterns_cache[key]['patterns'].extend(alternative['patterns'])
                            patterns_cache[key]['supported_pair_diagnostics'].extend(alternative['supported_pair_diagnostics'])
                        if stack_height_factor and floor_pair_budget>pair_used:
                            adjacent=floor_patterns(subset,options,policy['item_padding_mm'],spec['inner_wall_mm'],
                                gap=local_gap,increment=spec['dimension_increment_mm'],seconds=1.,hand_border=hand_border,
                                access_lane_mm=access_lane_mm,floor_pair_budget=min(6,floor_pair_budget-pair_used))
                            pair_used+=adjacent['floor_pair_seconds']
                            patterns_cache[key]['patterns'].extend(adjacent['patterns'])
                        rectangle_used+=patterns_cache[key]['rectangle_seconds']
                        rectangle_diagnostics.extend(patterns_cache[key]['rectangle_diagnostics'])
                        if source_surface_budget>surface_used:
                            from .source_surfaces import propose as surface_propose
                            base=min(patterns_cache[key]['patterns'],key=lambda p:math.prod(p['external_mm']))
                            for factor,objective in ((.85,'volume'),(.7,'height')):
                                remaining=source_surface_budget-surface_used
                                if remaining<=0:break
                                footprint=[math.ceil(v*factor) for v in base['external_mm'][:2]]
                                started_surface=perf_counter()
                                proposal=surface_propose(subset,options,footprint,policy['item_padding_mm'],spec['inner_wall_mm'],
                                    gap=local_gap,border=hand_border,seconds=min(12,remaining),
                                    max_height=max(base['external_mm'][2]*1.5,
                                                   max(min(p['dimensions_mm'][2] for p in options[i['id']]) for i in subset)+2*policy['item_padding_mm']),
                                    objective=objective)
                                surface_used+=perf_counter()-started_surface
                                surface_diagnostics.append({'family':family,**{k:v for k,v in proposal.items() if k!='pattern'}})
                                if proposal['status']=='complete_source_surface_proposal':patterns_cache[key]['patterns'].append(proposal['pattern'])
                        if irregular_executable and irregular_used<irregular_budget:
                            from .irregular_floor import propose
                            irregular_start=perf_counter()
                            eligible=[p for p in patterns_cache[key]['patterns'] if 'stable_sku_orientations' in p]
                            seeds=[]
                            # The two smallest-volume rows can have the same
                            # width and miss all useful contour strip widths.
                            for scoring in (lambda p:math.prod(p['external_mm']),
                                            lambda p:p['external_mm'][0],
                                            lambda p:math.prod(p['external_mm'][:2]),
                                            lambda p:p['external_mm'][2]):
                                seed=min(eligible,key=scoring)
                                if seed not in seeds:seeds.append(seed)
                            for seed in seeds:
                                left=irregular_budget-irregular_used-(perf_counter()-irregular_start)
                                if left<=0:break
                                from shapely.errors import GEOSException
                                try:
                                    proposal=propose(subset,options,seed,policy['item_padding_mm'],spec['inner_wall_mm'],
                                        executable=irregular_executable,time_limit=min(2.,left),gap=local_gap,hand_border=hand_border,
                                        increment=spec['dimension_increment_mm'],access_lane_mm=access_lane_mm)
                                except (ValueError,GEOSException) as error:
                                    proposal={'status':'rejected_geometry_proposal','error':str(error)}
                                irregular_diagnostics.append({'members':[i['id'] for i in subset],**{k:v for k,v in proposal.items() if k!='pattern'}})
                                if proposal['status']=='validated_planar_proposal':patterns_cache[key]['patterns'].append(proposal['pattern'])
                            irregular_used+=perf_counter()-irregular_start
                    modules.append({"family":family,"items":subset,**patterns_cache[key]})
            if progress:progress({'stage':'carton_candidates','counts':dict(zip(family_names,counts)),'actual_cartons':len(modules),'strategy':strategy,
                                  'seconds':perf_counter()-started,'irregular_seconds':irregular_used})
            if any(len(m['patterns'])>len(m['regular_floor_patterns']) for m in modules):
                regular=[{**m,'patterns':m['regular_floor_patterns']} for m in modules]
                fallback=tile_modules(regular,time_limit=.2,wall=spec['wall_mm'],foam=spec['protection_mm'],
                    reserve=spec['reserved_top_mm'],max_types=max(type_caps),increment=spec['dimension_increment_mm'])['candidate']
                if fallback:
                    fallback['proposal_kind']='regular_floor_fallback'
                    proposals.append((fallback['volume_mm3'],regular,fallback,max(type_caps)))
            for cap in type_caps:
                left=time_limit*.85-(perf_counter()-search_start)
                if left<.1 and proposals:break
                tiled=tile_modules(modules,time_limit=max(.05,min(1,left)),wall=spec["wall_mm"],foam=spec["protection_mm"],
                                   reserve=spec["reserved_top_mm"],max_types=cap,increment=spec["dimension_increment_mm"])
                candidate=tiled["candidate"]
                attempts.append({"counts":dict(zip(family_names,counts)),"strategy":strategy,"type_cap":cap,
                                 "volume_l":candidate["volume_mm3"]/1e6 if candidate else None})
                if candidate:proposals.append((candidate["volume_mm3"],modules,candidate,cap))
            if proposals and perf_counter()-search_start>time_limit*.72:break
    common_diagnostics=[]
    if common_floor_budget:
        from .common_floor import propose_common_floors
        common,common_diagnostics=propose_common_floors(library,options,policy,seconds=common_floor_budget,
            carton_counts=carton_counts,type_caps=type_caps,gap=gap,border=hand_border,access_lane=access_lane_mm,progress=progress)
        proposals.extend(common)
    master_diagnostics=[]
    if cp_sat_python:
        from .practical_master import select_cartons
        master_candidates=[];master_modules=[]
        for key,entry in patterns_cache.items():
            subset=cached_items[key]
            from .concept_patterns import diverse_patterns
            for pattern in diverse_patterns(entry['patterns'], 12):
                size=pattern['external_mm']
                master_candidates.append({'contents':{p['unit_id']:1 for p in pattern['placements']},
                                          'external_mm':size,'size_key':[*sorted(size[:2]),size[2]]})
                master_modules.append({'family':policy['families'][subset[0]['id']],'items':subset,'patterns':[pattern]})
        expected={f"{i['id']}#{k+1}":1 for i in library['items'] for k in range(i['quantity'])}
        for n in carton_counts:
            for objective in ('volume','types'):
                if perf_counter()-search_start>time_limit and master_diagnostics:break
                selection=select_cartons(master_candidates,expected,n,python=cp_sat_python,time_limit=1.,objective=objective)
                master_diagnostics.append({'cartons':n,'objective':objective,**selection})
                if not selection['selected']:continue
                modules=[deepcopy(master_modules[i]) for i in selection['selected']]
                for cap in type_caps:
                    tiled=tile_modules(modules,time_limit=.25,wall=spec['wall_mm'],foam=spec['protection_mm'],
                                       reserve=spec['reserved_top_mm'],max_types=cap,increment=spec['dimension_increment_mm'])
                    if tiled['candidate']:proposals.append((tiled['candidate']['volume_mm3'],modules,tiled['candidate'],cap))
    refinement_diagnostics=[]
    if refinement_budget:
        from .practical_refinement import refine
        refinement_start=perf_counter()
        seeds=[]
        for n in carton_counts:
            matching=[p for p in proposals if len(p[1])==n]
            if matching:seeds.append(min(matching,key=lambda p:p[0]))
        for seed in sorted(seeds,key=lambda p:p[0]):
            left=refinement_budget-(perf_counter()-refinement_start)
            if left<=0:break
            improved,diagnostic=refine(seed,options,policy,seconds=min(15,left),gap=gap,family_gaps=family_gaps,
                hand_border=hand_border,stack_height_factor=stack_height_factor,access_lane_mm=access_lane_mm,
                supported_nesting=supported_nesting,volumetric_catalog=volumetric_catalog)
            proposals.append(improved);refinement_diagnostics.append(diagnostic)
            if progress:progress({'stage':'joint_refinement','before_l':seed[0]/1e6,'after_l':improved[0]/1e6,**diagnostic})
    verified=[];verified_plans={};replays=[];seen=set();repair_used=0.
    # Select diverse carton/type alternatives instead of discarding them on volume alone.
    ranked=sorted(proposals,key=lambda p:p[0]);queue=ranked[:1]
    fallbacks=[p for p in ranked if p[2].get('proposal_kind')=='regular_floor_fallback']
    if fallbacks:queue.append(fallbacks[0])
    for n in carton_counts:
        subset=[p for p in ranked if len(p[1])==n]
        if subset:queue.append(subset[0])
    for cap in type_caps:
        subset=[p for p in ranked if p[2]["distinct_carton_sizes"]<=cap]
        if subset:queue.append(subset[0])
    queue+=ranked
    for volume,modules,tiled,cap in queue:
        signature=fingerprint([{'family':modules[l['module']]['family'],
                                'position_mm':l['position_mm'],'external_mm':l['external_mm'],
                                'placements':sorted(modules[l['module']]['patterns'][l['pattern']]['placements'],key=lambda p:p['unit_id'])}
                               for l in tiled['leaves']])
        if signature in seen:continue
        seen.add(signature)
        if len(replays)>=max_replays:break
        trial_policy={**deepcopy(policy),"max_inner_cartons":max(carton_counts),"max_carton_types":cap}
        try:
            # Repack against the expanded, current-run carton dimensions. This
            # does not import an external recipe. If this reduces a module's
            # required height, retile the block before independent replay.
            modules=deepcopy(modules);tiled=deepcopy(tiled);replacements={}
            for leaf in tiled['leaves']:
                module=modules[leaf['module']]
                try:
                    repaired=floor_patterns(module['items'],options,policy['item_padding_mm'],spec['inner_wall_mm'],
                        gap=family_gaps.get(module['family'],gap),increment=spec['dimension_increment_mm'],seconds=.3,hand_border=hand_border,
                        target_footprints=[leaf['external_mm'][:2]],
                        stack_height_factor=0. if tiled.get('proposal_kind')=='regular_floor_fallback' else stack_height_factor,
                        access_lane_mm=access_lane_mm,
                        supported_nesting=False if tiled.get('proposal_kind')=='regular_floor_fallback' else supported_nesting)
                    fits=[p for p in repaired['patterns'] if all(a<=b+1e-7 for a,b in zip(p['external_mm'],leaf['external_mm']))]
                    # Keep contour packing when a rectangular repair loses its fit.
                    if fits:
                        replacement=min(fits,key=lambda p:p['external_mm'][2])
                        replacements[leaf['module']]=[replacement]
                except ValueError:
                    pass
            from .practical_refinement import choose_repacked_block
            compact_modules, compact = choose_repacked_block(modules,tiled,replacements,spec,cap)
            post_repack_retiling = {'before_l': volume/1e6, 'after_l': volume/1e6}
            if compact and compact['volume_mm3'] < volume-1e-6:
                volume, modules, tiled = compact['volume_mm3'], compact_modules, compact
                post_repack_retiling['after_l'] = volume/1e6
            result=build_candidate(library,trial_policy,modules,tiled,finger_radius=finger_radius)
            repair_diagnostic=None
            if result['practical']['support']['valid'] and not result['practical']['hand_access']['valid'] and repair_used<access_repair_budget:
                from .access_repair import repair
                repair_start=perf_counter()
                repair_attempts=[]
                try:
                    for individual in (True,False):
                        remaining=access_repair_budget-repair_used-(perf_counter()-repair_start)
                        if remaining<=0:break
                        repaired,diagnostic=repair((volume,modules,tiled,cap),result,options,trial_policy,
                            seconds=min(10.,remaining),finger_radius=finger_radius,individual=individual,
                            hand_border=hand_border,access_lane=access_lane_mm,gap=gap,family_gaps=family_gaps)
                        repair_attempts.append(diagnostic)
                        if repaired:
                            repaired_volume,repaired_modules,repaired_tiled,_=repaired
                            repaired_result=build_candidate(library,trial_policy,repaired_modules,repaired_tiled,finger_radius=finger_radius)
                            diagnostic['original_failures']=result['practical']['hand_access']['failures']
                            diagnostic['replay_passed']=repaired_result['practical']['valid']
                            if repaired_result['practical']['valid']:
                                volume,modules,tiled,result=repaired_volume,repaired_modules,repaired_tiled,repaired_result
                                break
                finally:
                    elapsed=perf_counter()-repair_start;repair_used+=elapsed
                    repair_diagnostic={'attempts':repair_attempts,'including_replay_seconds':elapsed}
            record={"volume_l":volume/1e6,"cartons":len(modules),"types":tiled["distinct_carton_sizes"],
                    "support":result["practical"]["support"]["valid"],"hand_access":result["practical"]["hand_access"]["valid"],
                    'post_repack_retiling': post_repack_retiling}
            if repair_diagnostic:record['access_repair']=repair_diagnostic
            cohesion = check_accessory_set_cohesion(result, properties['cards'])
            result['practical']['accessory_set_cohesion'] = cohesion
            result['practical']['properties_fingerprint'] = fingerprint(properties)
            result['practical']['valid'] &= cohesion['valid']
            record['accessory_set_cohesion'] = cohesion
            if result["practical"]["valid"]:
                result['practical']['metrics']['organization'] = organization_metrics(result, properties['cards'])
                plan=build_assembly_plan(result,bom)
                verified.append(result)
                verified_plans[id(result)]=plan
                record["status"]="verified"
            else:
                record["status"]="rejected_practical_checks"
                record["hand_failures"]=result["practical"]["hand_access"]["failures"]
            if callback:callback(result,record)
        except ValueError as error:
            record={"status":"rejected","volume_l":volume/1e6,"error":str(error)}
        replays.append(record)
    frontier=nondominated(verified)
    cavity_diagnostics=[d for entry in patterns_cache.values() for d in entry.get('supported_pair_diagnostics',[])]
    for result in frontier:
        if verified_plans[id(result)]['result_fingerprint']!=fingerprint(result):
            raise ValueError('Result changed after independent assembly replay')
        result["search"]={"total_seconds":perf_counter()-started,"preparation_seconds":preparation_seconds,
                          "method":"regular_stable_floor_portfolio","attempts":attempts,"replays":replays,
                          "exact_cover_master":master_diagnostics,
                          "irregular_proposals":irregular_diagnostics,
                          "joint_refinement":refinement_diagnostics,
                          "rectangle_proposals":rectangle_diagnostics,
                          'motif_rectangle_proposals': motif_rectangle_diagnostics,
                          "common_footprint_proposals":common_diagnostics,
                          "supported_pair_proposals":cavity_diagnostics,
                          "source_surface_proposals":surface_diagnostics,
                          "optimality_proven":False,"reference_used":False,
                          "timing_scope":"Complete current invocation including pose preparation and failed replay trials"}
        # Only search metadata was added after the independent replay. Rebind
        # that exact plan rather than performing a third identical CAD replay.
        verified_plans[id(result)]['result_fingerprint']=fingerprint(result)
    return {"results":frontier,"assembly_plans":[verified_plans[id(r)] for r in frontier],
            "attempts":attempts,"replays":replays,"exact_cover_master":master_diagnostics,
            "joint_refinement":refinement_diagnostics,
            "rectangle_proposals":rectangle_diagnostics,
            'motif_rectangle_proposals': motif_rectangle_diagnostics,
            "common_footprint_proposals":common_diagnostics,
            "supported_pair_proposals":cavity_diagnostics,
            "source_surface_proposals":surface_diagnostics,
            "irregular_proposals":irregular_diagnostics,"seconds":perf_counter()-started,
            "preparation_seconds":preparation_seconds,"part_properties":properties,
            "status":"verified" if frontier else "no_verified_practical_layout"}
