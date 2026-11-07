"""Reference-free compatible modules and filler-free adjustable carton tiling."""
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
from itertools import permutations
import json
import math
from pathlib import Path
from time import perf_counter

from .carton_tiling import tile_modules
from .strip_packing import pack_strip
from .report import fingerprint


class NonImprovingProposal(ValueError):
    """An in-run envelope cannot improve the already certified incumbent."""
    def __init__(self,volume):
        self.volume=volume
        super().__init__("Envelope does not improve the current-run certified incumbent")


def prepare_units(library, policy):
    import numpy as np
    import trimesh
    from .mesh_frames import packing_bounds
    families=policy["families"]
    if library.get("units")!="mm" or not library.get("all_meshes_valid_volumes"):
        raise ValueError("Verified millimetre source library required")
    items={i["id"]:i for i in library["items"]}
    if len(items)!=len(library["items"]) or not items:
        raise ValueError("Unique nonempty source library required")
    if any(type(i.get("quantity")) is not int or i["quantity"]<=0 for i in items.values()):
        raise ValueError("Positive integer source quantities required")
    if set(families) != set(items):
        raise ValueError("Policy must explicitly classify every source SKU exactly once")
    if any(not isinstance(v,str) or not v for v in families.values()):
        raise ValueError("Nonempty family IDs required")
    padding=float(policy["item_padding_mm"])
    if not math.isfinite(padding) or padding<=0 or 2*padding<float(policy["clearance_mm"]):
        raise ValueError("Padding must preserve original-part clearance")
    groups=defaultdict(list);frames={}
    for item in library["items"]:
        raw=Path(item["mesh"]["path"]).read_bytes()
        if sha256(raw).hexdigest()!=item["mesh"]["sha256"]:
            raise ValueError("Source mesh hash mismatch")
        data=json.loads(raw)
        if data.get("units")!="mm":raise ValueError("Source geometry must use millimetres")
        mesh=trimesh.Trimesh(data["vertices_mm"],data["triangles"],process=False)
        if not mesh.is_volume:
            raise ValueError("Positive watertight original geometry required")
        frame,_=packing_bounds(mesh)
        points=trimesh.transform_points(mesh.vertices,frame)
        frame[:3,3]-=points.min(axis=0)
        dimensions=np.ptp(points,axis=0)+2*padding
        frames[item["id"]]={"frame":frame.tolist(),"bare_size":(dimensions-2*padding).tolist()}
        # The current policy explicitly accepts all rigid axis permutations in
        # the generated intrinsic frame; do not silently ignore restricted rules.
        if policy.get("allow_all_rotations") is not True:
            raise ValueError("This version requires explicit unrestricted source rotations")
        choices=[(r,tuple(float(dimensions[k]) for k in r)) for r in permutations(range(3))]
        for copy in range(item["quantity"]):
            groups[families[item["id"]]].append({"item_id":item["id"],"unit_id":f"{item['id']}#{copy+1}",
                                                "dimensions":dimensions.tolist(),"orientations":choices})
    return dict(groups),frames


def module_patterns(units, wall, *, time_limit=15, increment=1, gap=.2, executable=None, rectangle_executable=None):
    started=perf_counter();volume=sum(math.prod(u["dimensions"]) for u in units)
    scale=volume**(1/3)
    widths=sorted({math.ceil(v/increment)*increment for v in
                   [scale*f for f in (.65,.8,1,1.2,1.4,1.7,2,2.5)]+
                   [max(min(u["dimensions"]) for u in units),max(max(u["dimensions"]) for u in units)]})
    heights=sorted({v for u in units for v in u["dimensions"]})
    if len(heights)>18:
        heights=[heights[round(i*(len(heights)-1)/17)] for i in range(18)]
    def height_priority(height):
        choices=[[s for _,s in u["orientations"] if s[2]<=height+1e-8] for u in units]
        if any(not c for c in choices):return math.inf
        floor=sum(min(s[0]*s[1] for s in c) for c in choices)
        # Favor useful three-dimensional proportions early under short budgets.
        # This scale derives from unit volume, not an exterior reference box.
        return (math.sqrt(floor)+scale*.2)**2*(height+scale*.2)
    heights.sort(key=height_priority)
    patterns=[];backend_checks=[]

    def retain(p, method):
        if p is None:return
        used=[max(x["position_mm"][k]+x["dimensions_mm"][k] for x in p["placements"]) for k in range(3)]
        external=[math.ceil((v+2*wall)/increment-1e-9)*increment for v in used]
        patterns.append({"external_mm":external,"placements":p["placements"],"method":method})

    for height in heights:
        eligible=[[s for _,s in u["orientations"] if s[2]<=height+1e-8] for u in units]
        if any(not choices for choices in eligible):continue
        floor_scale=math.sqrt(sum(min(s[0]*s[1] for s in choices) for choices in eligible))
        band_widths=sorted(set(widths+[math.ceil(floor_scale*f/increment)*increment for f in (.65,.8,1,1.25,1.6,2)]),
                          key=lambda width:abs(math.log(width/floor_scale)))
        for width in band_widths:
            if perf_counter()-started>time_limit*.55:break
            for mode,order in (("short_side","area"),("height_fill","volume"),
                               ("bottom_left","compact"),("area","best_fit")):
                retain(pack_strip(units,width,height,gap,placement_score=mode,item_order=order),"maximal_free_rectangles")
        if perf_counter()-started>time_limit*.55:break
    if not patterns:
        raise ValueError("No complete compatible module envelope")
    from .supported_packing import pack_supported
    from .validation import validate
    for factor in (.85,1.05,1.3,1.6):
        for aspect in (1,.75,1.35):
            if perf_counter()-started>time_limit*.73:break
            width=scale*factor*aspect;depth=scale*factor/aspect
            for mode,order in (("height","volume"),("height","area"),("volume","volume"),("fit","area"),
                               ("height","perturb-0"),("height","perturb-1")):
                p=pack_supported(units,width,depth,scale*3,gap,mode,item_order=order)
                if not p:continue
                problem={"container":{"inner_mm":p["usable_mm"]},"gap_mm":gap,
                         "items":[{"id":u["unit_id"],"dimensions_mm":u["dimensions"],
                                   "allowed_rotations":[list(r) for r,_ in u["orientations"]]} for u in units]}
                poses=[{**pose,"item_id":pose["unit_id"],"unit_id":pose["unit_id"]+"#1"} for pose in p["placements"]]
                if validate(problem,{"placements":poses})["valid"]:retain(p,"supported_surface_packing")
        if perf_counter()-started>time_limit*.73:break
    from .column_packing import make_columns,make_mixed_columns,expand_columns
    column_heights=sorted({max(min(u["dimensions"]) for u in units),*(scale*f for f in (.65,.85,1,1.3,1.7))})
    for height in column_heights:
        columns,expansion=make_mixed_columns(units,height)
        if columns and len(columns)<len(units):
            floor_scale=math.sqrt(sum(u["dimensions"][0]*u["dimensions"][1] for u in columns))
            for factor in (1,.8,1.25,.65,1.6):
                p=pack_strip(columns,floor_scale*factor,height,gap,placement_score="short_side")
                if p:retain(expand_columns(p,expansion),"compatible_envelope_columns")
        for axis in range(3):
            if perf_counter()-started>time_limit*.85:break
            columns,expansion=make_columns(units,height,axis)
            if not columns or len(columns)==len(units):continue
            floor_scale=math.sqrt(sum(u["dimensions"][0]*u["dimensions"][1] for u in columns))
            for factor in (1,.8,1.25,.65,1.6):
                p=pack_strip(columns,floor_scale*factor,height,gap,placement_score="short_side")
                if p:retain(expand_columns(p,expansion),"repeated_unit_columns")
        if perf_counter()-started>time_limit*.85:break
    # Test the alternative backend on independently derived module footprints.
    if executable:
        from .packing_solver_adapter import pack_boxes
        bases=sorted(patterns,key=lambda p:math.prod(p["external_mm"]))[:3]
        for base in bases:
            remaining=time_limit-(perf_counter()-started)
            if remaining<.2:break
            w,d,_=base["external_mm"]
            packed=pack_boxes(units,w-2*wall,d-2*wall,executable=executable,time_limit=min(2,remaining),gap=gap,repair_support=True)
            backend_checks.append({k:v for k,v in packed.items() if k not in ("placements","validation")})
            if packed["status"]=="validated_envelopes":retain(packed,"packingsolver_box")
    if rectangle_executable:
        from .packing_solver_adapter import pack_floor
        floor_patterns=[p for p in patterns if all(abs(q["position_mm"][2])<1e-8 for q in p["placements"])]
        seen=set();seeds=[]
        for p in sorted(floor_patterns,key=lambda p:math.prod(p["external_mm"])):
            key=(p["external_mm"][0],tuple(sorted((q["unit_id"],q["rotation"][2]) for q in p["placements"])))
            if key not in seen:seen.add(key);seeds.append(p)
        for seed in seeds[:8]:
            packed=pack_floor(units,seed["placements"],seed["external_mm"][0]-2*wall,
                              executable=rectangle_executable,time_limit=1,gap=gap)
            backend_checks.append({"solver":"rectangle",**{k:v for k,v in packed.items() if k not in ("placements","validation")}})
            if packed["status"]=="validated_envelopes":retain(packed,"packingsolver_rectangle_floor")
    # A horizontal quarter turn preserves floor support and gives the carton
    # tiler both aspect ratios without consuming another packing search.
    for p in list(patterns):
        turned=deepcopy(p)
        turned["external_mm"]=[p["external_mm"][1],p["external_mm"][0],p["external_mm"][2]]
        for pose in turned["placements"]:
            for field in ("position_mm","dimensions_mm","rotation"):
                pose[field][0],pose[field][1]=pose[field][1],pose[field][0]
        patterns.append(turned)
    unique={}
    for p in sorted(patterns,key=lambda p:math.prod(p["external_mm"])):
        unique.setdefault(tuple(p["external_mm"]),p)
    ordered=list(unique.values())
    selected=ordered[:16]
    # Preserve useful height bands even when their isolated carton volume is
    # larger. Dropping them prevents the outer search from trading footprint
    # against height and can force a long, foam-expensive shipping carton.
    for height in sorted({p["external_mm"][2] for p in ordered}):
        band=[p for p in ordered if p["external_mm"][2]==height]
        representatives=band[:2]+sorted(band,key=lambda p:(max(p["external_mm"][:2]),math.prod(p["external_mm"])))[:2]
        for p in representatives:
            if p not in selected:selected.append(p)
    for axis in range(3):
        for p in sorted(ordered,key=lambda p:(p["external_mm"][axis],math.prod(p["external_mm"])))[:6]:
            if p not in selected:selected.append(p)
    return {"patterns":selected,"backend_checks":backend_checks,"elapsed_seconds":perf_counter()-started}


def design_logistics(library, policy, expected_bom, *, time_limit=120, executable=None,
                     nesting_seconds=0, work_directory=None, split_largest_family=False, largest_family_cartons=1,
                     partition_strategy="volume", balanced_cartons=0, nesting_workers=1, rectangle_executable=None, _prepared_nesting=None, _pattern_cache=None,
                     _incumbent_volume=None, shared_footprint_seconds=0, nesting_pitch_mm=4, nesting_objective="volume"):
    import numpy as np
    from .bom import reconcile_bom
    from .assembly_plan import build_assembly_plan
    from .layered_design import validate_layered
    from .mesh_validation import validate_mesh_layout
    from .protection_geometry import foam_panels, validate_foam_shell
    started=perf_counter()
    if not math.isfinite(time_limit) or time_limit<=0 or not math.isfinite(nesting_seconds) or nesting_seconds<0:
        raise ValueError("Positive finite search budget and nonnegative nesting budget required")
    if not math.isfinite(shared_footprint_seconds) or shared_footprint_seconds<0:raise ValueError("Nonnegative finite shared-footprint budget required")
    allowed={"schema_version","families","family_labels","classification_evidence","item_padding_mm",
             "clearance_mm","allow_all_rotations","carton","max_inner_cartons","max_carton_types"}
    if set(policy)-allowed or policy.get("schema_version")!=1:
        raise ValueError("Unsupported logistics policy; reference data must stay outside design")
    coverage=reconcile_bom(expected_bom,{"items":library["items"]})
    if not coverage["complete"]:raise ValueError("Incomplete declared source BOM")
    packing_library=library;packing_policy=policy;nesting=None
    if _prepared_nesting is not None:
        if (_prepared_nesting["source_library_fingerprint"]!=fingerprint(library) or
                _prepared_nesting["policy_fingerprint"]!=fingerprint(policy)):
            raise ValueError("In-run nesting source or policy mismatch")
        nesting=_prepared_nesting
        packing_library=nesting["library"];packing_policy={**policy,"families":nesting["families"]}
    elif nesting_seconds:
        if work_directory is None:raise ValueError("Nesting requires an output directory")
        from .compatible_nesting import discover_compatible_units
        nesting=discover_compatible_units(library,policy,Path(work_directory)/"nesting",nesting_seconds,workers=nesting_workers,pitch_mm=nesting_pitch_mm,shape_objective=nesting_objective)
        packing_library=nesting["library"];packing_policy={**policy,"families":nesting["families"]}
    proposal_started=perf_counter()
    groups,frames=prepare_units(packing_library,packing_policy)
    if len(groups)>policy["max_inner_cartons"]:
        raise ValueError("Required compatible families exceed carton-count cap")
    carton=policy["carton"];t=carton["inner_wall_mm"];modules=[]
    module_sets=sorted(groups.items())
    requested=max(largest_family_cartons,2 if split_largest_family else 1)
    if type(requested) is not int or requested<1:raise ValueError("Positive integer family carton count required")
    if partition_strategy not in ("volume","packing"):raise ValueError("Unknown family partition strategy")
    partition_diagnostics=None
    if type(balanced_cartons) is not int or balanced_cartons<0 or balanced_cartons>policy["max_inner_cartons"]:
        raise ValueError("Balanced carton count must respect the policy cap")
    counts={family:1 for family,_ in module_sets}
    if balanced_cartons:
        if balanced_cartons<len(groups):raise ValueError("Balanced carton count cannot omit compatible families")
        volumes={family:sum(math.prod(u["dimensions"]) for u in units) for family,units in module_sets}
        for _ in range(balanced_cartons-len(groups)):
            eligible=[family for family,units in module_sets if counts[family]<len(units)]
            if not eligible:break
            family=max(eligible,key=lambda family:volumes[family]/counts[family]);counts[family]+=1
    elif requested>1 and len(groups)<policy["max_inner_cartons"]:
        family,units=max(module_sets,key=lambda pair:sum(math.prod(u["dimensions"]) for u in pair[1]))
        counts[family]=min(requested,len(units),policy["max_inner_cartons"]-len(groups)+1)
    divided=[];partition_records=[]
    for family,units in module_sets:
        count=counts[family]
        if count==1:divided.append((family,units));continue
        # Separate tall and short units rather than forcing all floor-packed
        # contents to pay for the tallest part. This uses geometry, not SKU IDs.
        ordered=sorted(units,key=lambda u:(min(u["dimensions"]),math.prod(u["dimensions"])))
        prefix=[0]
        for u in ordered:prefix.append(prefix[-1]+math.prod(u["dimensions"]))
        cuts=[0]
        for index in range(1,count):
            cut=min(range(cuts[-1]+1,len(ordered)-(count-index)+1),key=lambda cut:abs(prefix[cut]-prefix[-1]*index/count))
            cuts.append(cut)
        cuts.append(len(ordered))
        subdivisions=[ordered[a:b] for a,b in zip(cuts,cuts[1:])]
        if partition_strategy=="packing" and count>1:
            from .family_partition import packing_partition
            proposal=packing_partition(units,count,wall=t,gap=carton["gap_mm"],
                                       increment=carton["dimension_increment_mm"],time_limit=min(5,time_limit*.1))
            if proposal["groups"]:subdivisions=proposal["groups"]
            partition_diagnostics={k:v for k,v in proposal.items() if k!="groups"}
            partition_diagnostics["selected_strategy"]="packing" if proposal["groups"] else "volume_fallback"
            partition_records.append({"family":family,**partition_diagnostics})
        divided.extend((family,group) for group in subdivisions)
    module_sets=divided
    if balanced_cartons:partition_diagnostics={"allocation":counts,"partitions":partition_records}
    all_units={u["unit_id"]:u for units in groups.values() for u in units}
    packing_hashes={i["id"]:i["mesh"]["sha256"] for i in packing_library["items"]}
    for family,units in module_sets:
        remaining=time_limit-(perf_counter()-proposal_started)
        key=fingerprint({"family":family,"units":units,"source_hashes":{u["item_id"]:packing_hashes[u["item_id"]] for u in units},
                         "wall":t,"increment":carton["dimension_increment_mm"],"gap":carton["gap_mm"],
                         "rectangle_solver":str(rectangle_executable),"box_solver":str(executable)})
        if _pattern_cache is not None and key in _pattern_cache:
            proposal=deepcopy(_pattern_cache[key]);proposal["reused_in_run"]=True
            proposal["original_pattern_search_seconds"]=proposal["elapsed_seconds"];proposal["elapsed_seconds"]=0
        else:
            proposal=module_patterns(units,t,time_limit=max(1,min(18,remaining/(len(module_sets)-len(modules)+1))),
                                     increment=carton["dimension_increment_mm"],gap=carton["gap_mm"],executable=executable,rectangle_executable=rectangle_executable)
            if _pattern_cache is not None:_pattern_cache[key]=deepcopy(proposal)
        modules.append({"family":family,"unit_ids":[u["unit_id"] for u in units],"_cache_key":key,**proposal})
    shared_diagnostics=None
    if shared_footprint_seconds:
        from .shared_footprints import search_shared_footprints
        shared=search_shared_footprints(module_sets,carton,time_limit=shared_footprint_seconds)
        for candidate in shared["candidates"]:
            for module,pattern in zip(modules,candidate["patterns"]):module["patterns"].append(pattern)
        shared_diagnostics={k:v for k,v in shared.items() if k!="candidates"}
        shared_diagnostics["candidate_volumes_mm3"]=[c["volume_mm3"] for c in shared["candidates"]]
    tiling=tile_modules(modules,time_limit=max(1,min(25,time_limit-(perf_counter()-proposal_started))),wall=carton["wall_mm"],
                        foam=carton["protection_mm"],reserve=carton["reserved_top_mm"],
                        max_types=policy["max_carton_types"],increment=carton["dimension_increment_mm"])
    if not tiling["candidate"]:raise ValueError("No tiling satisfies the carton type cap")
    refinement=[]
    # Repack against dimensions discovered by the joint carton search. An
    # independently optimal skinny module is often a poor fit in the full kit.
    # These are strictly in-run dimensions, never engineer reference sizes.
    for iteration in range(2):
        remaining=time_limit-(perf_counter()-proposal_started)
        if remaining<5:break
        round_start=perf_counter();incumbent=tiling["candidate"]
        targets=[leaf["external_mm"][:2] for leaf in incumbent["leaves"]]
        targets+=[incumbent["block_mm"][:2]]
        per_module=max(.2,min(3,remaining/(2*len(modules))))
        for module_index,module in enumerate(modules):
            substart=perf_counter();units=[all_units[uid] for uid in module["unit_ids"]]
            heights=sorted({s[2] for u in units for _,s in u["orientations"]})
            known={tuple(p["external_mm"]) for p in module["patterns"]}
            own=next(leaf["external_mm"][:2] for leaf in incumbent["leaves"] if leaf["module"]==module_index)
            increment=carton["dimension_increment_mm"]
            neighbours=[]
            for fx,fy in ((1.05,1),(1,1.05),(1.1,1),(1,1.1),(.95,1),(1,.95),(1.2,1),(1,1.2),(1.05,1.05)):
                neighbours.append([math.ceil(own[0]*fx/increment)*increment,math.ceil(own[1]*fy/increment)*increment])
            module_targets=[own,*neighbours,incumbent["block_mm"][:2],*targets]
            for w,d in module_targets:
                from .supported_packing import pack_supported,optimize_supported
                from .validation import validate
                if [w,d]==own:
                    evolved=optimize_supported(units,w-2*t,d-2*t,max(incumbent["block_mm"]),carton["gap_mm"],time_limit=min(1,per_module*.4))
                    p=evolved["packing"]
                    if p:
                        h=math.ceil((p["usable_mm"][2]+2*t)/increment)*increment;size=(w,d,h)
                        if size not in known:
                            module["patterns"].append({"external_mm":list(size),"placements":p["placements"],"method":"supported_order_evolution"});known.add(size)
                for mode,order in (("height","volume"),("height","area"),("volume","volume"),("fit","area"),
                                   ("height","perturb-0"),("height","perturb-1")):
                    p=pack_supported(units,w-2*t,d-2*t,max(incumbent["block_mm"]),carton["gap_mm"],mode,item_order=order)
                    if not p:continue
                    problem={"container":{"inner_mm":p["usable_mm"]},"gap_mm":carton["gap_mm"],
                             "items":[{"id":u["unit_id"],"dimensions_mm":u["dimensions"],
                                       "allowed_rotations":[list(r) for r,_ in u["orientations"]]} for u in units]}
                    poses=[{**pose,"item_id":pose["unit_id"],"unit_id":pose["unit_id"]+"#1"} for pose in p["placements"]]
                    if not validate(problem,{"placements":poses})["valid"]:continue
                    h=math.ceil((p["usable_mm"][2]+2*t)/carton["dimension_increment_mm"])*carton["dimension_increment_mm"]
                    size=(w,d,h)
                    if size not in known:
                        module["patterns"].append({"external_mm":list(size),"placements":p["placements"],"method":"supported_surface_repacking"})
                        known.add(size)
                for height in heights:
                    if perf_counter()-substart>per_module:break
                    for mode in ("height_fill","short_side"):
                        p=pack_strip(units,w-2*t,height,carton["gap_mm"],depth=d-2*t,placement_score=mode)
                        if not p:continue
                        h=math.ceil((p["usable_mm"][2]+2*t)/carton["dimension_increment_mm"])*carton["dimension_increment_mm"]
                        size=(w,d,h)
                        if size not in known:
                            module["patterns"].append({"external_mm":list(size),"placements":p["placements"],"method":"joint_footprint_repacking"})
                            known.add(size)
                if perf_counter()-substart>per_module:break
        remaining=time_limit-(perf_counter()-proposal_started)
        improved=tile_modules(modules,time_limit=max(1,min(20,remaining)),wall=carton["wall_mm"],foam=carton["protection_mm"],
                              reserve=carton["reserved_top_mm"],max_types=policy["max_carton_types"],increment=carton["dimension_increment_mm"])
        if improved["candidate"] and improved["candidate"]["volume_mm3"]<tiling["candidate"]["volume_mm3"]:
            tiling=improved
        refinement.append({"round":iteration+1,"seconds":perf_counter()-round_start,"volume_mm3":tiling["candidate"]["volume_mm3"]})
    chosen=tiling["candidate"];external=chosen["external_mm"];foam=carton["protection_mm"];wall=carton["wall_mm"]
    if _pattern_cache is not None:
        for module in modules:
            _pattern_cache[module["_cache_key"]]={k:deepcopy(v) for k,v in module.items() if k in ("patterns","backend_checks","elapsed_seconds")}
    if _incumbent_volume is not None and chosen["volume_mm3"]>=_incumbent_volume:
        # This is not an accepted plan. Avoid expensive original-mesh replay
        # only when it cannot replace the same-run already checked result.
        raise NonImprovingProposal(chosen["volume_mm3"])
    container={"inner_mm":[v-2*wall for v in external],"wall_mm":[wall]*3,"protection_mm":[foam]*3,
               "reserved_top_mm":carton["reserved_top_mm"]}
    layers=[];envelope_poses=[];poses=[];module_manifest=[];assembly_groups={}
    for index,leaf in enumerate(sorted(chosen["leaves"],key=lambda l:(l["position_mm"][2],l["position_mm"][0])),1):
        module=modules[leaf["module"]];pattern=module["patterns"][leaf["pattern"]]
        lid=f"module-{index}";origin=np.asarray(leaf["position_mm"])+t
        layers.append({"id":lid,"position_mm":leaf["position_mm"],"wall_mm":t,
                       "inner_mm":[v-2*t for v in leaf["external_mm"]]})
        module_units=[]
        for p in sorted(pattern["placements"],key=lambda p:(p["position_mm"][2],p["unit_id"])):
            absolute=np.asarray(p["position_mm"])+origin
            envelope_poses.append({**p,"layer_id":lid,"position_mm":absolute.tolist()})
            source=frames[p["item_id"]];rotation=np.eye(3)[p["rotation"]]
            if np.linalg.det(rotation)<0:rotation[0]*=-1
            transform=np.eye(4);transform[:3,:3]=rotation
            transform[:3,3]=absolute+policy["item_padding_mm"]-np.minimum(rotation,0)@np.asarray(source["bare_size"])
            rigid=transform@np.asarray(source["frame"])
            members=nesting["expansion"][p["unit_id"]] if nesting else [
                {"item_id":p["item_id"],"unit_id":p["unit_id"],"transform":np.eye(4).tolist()}]
            if nesting:assembly_groups["assembly-"+p["unit_id"]]=[m["unit_id"] for m in members]
            for member in members:
                poses.append({**member,"transform":(rigid@np.asarray(member["transform"])).tolist()})
                module_units.append(member["unit_id"])
        module_manifest.append({"id":lid,"family":module["family"],"method":pattern["method"],
                                "external_mm":leaf["external_mm"],"position_mm":leaf["position_mm"],
                                "unit_ids":module_units,
                                "retention_status":"unverified","closure":"Closed carton; prototype retention trial required"})
    envelope_items=[]
    for item in packing_library["items"]:
        u=next(u for g in groups.values() for u in g if u["item_id"]==item["id"])
        envelope_items.append({"id":item["id"],"quantity":item["quantity"],"dimensions_mm":u["dimensions"],
                               "allowed_rotations":[list(r) for r,_ in u["orientations"]]})
    problem={"units":"mm","items":envelope_items,"container":container,"gap_mm":carton["gap_mm"],"inner_wall_mm":t}
    layout={"placements":envelope_poses,"layers":layers,"status":"feasible"}
    hierarchy=validate_layered(problem,layout)
    if not hierarchy["valid"]:raise ValueError(f"Tiled hierarchy failed: {hierarchy}")
    candidate={"input":problem,"layout":layout,"validation":hierarchy,"external_mm":external,
               "volume_mm3":math.prod(external),"packaging_bom":[{"id":m["id"],"quantity":1,
               "type":"closed_rectangular_inner_carton","external_mm":m["external_mm"],"wall_mm":t,
               "manufacturing_status":"Custom dimension specification; supplier approval pending"} for m in module_manifest]}
    panels=foam_panels(container["inner_mm"],foam)
    foam_check=validate_foam_shell(container["inner_mm"],foam,panels)
    candidate["packaging_bom"].extend([
        {"id":"outer-carton","type":"closed_corrugated_outer_carton","quantity":1,
         "external_mm":external,"wall_mm":wall,"manufacturing_status":"Custom specification; strength and supplier approval pending"},
        *deepcopy(panels)])
    result={"status":"validated_mesh_envelope_baseline","input":{"units":"mm","items":deepcopy(library["items"]),
             "container":container,"clearance_mm":policy["clearance_mm"]},"layout":{"units":"mm","placements":poses},
            "envelope_design":{"candidate":candidate},"logistics":{"policy":deepcopy(policy),"policy_hash":fingerprint(policy),
            "modules":module_manifest,"foam_panels":panels,"foam_validation":foam_check,"spacers":[],
            "block_mm":chosen["block_mm"],"carton_count":len(layers),"carton_types":chosen["distinct_carton_sizes"],
            "physical_qualification":False,"retention_verified":False,"reference_used":False},
            "source_library_sha256":fingerprint(library),"search":{"modules":[{k:v for k,v in m.items() if k not in ("patterns","_cache_key")} for m in modules],
            "proposal_seconds":perf_counter()-started,"joint_refinement":refinement,"optimality_proven":False,
            "family_partition":partition_diagnostics,"shared_footprints":shared_diagnostics}}
    if nesting:
        result["groups"]=assembly_groups
        result["group_certificates"]=nesting["certificates"]
        result["search"]["nesting"]={"seconds":nesting["elapsed_seconds"],"families":nesting["search"]}
    result["validation"]=validate_mesh_layout(result["input"],result["layout"])
    if not result["validation"]["valid"]:raise ValueError("Original mesh validation failed")
    from .transport_validation import validate_transport
    result["logistics"]["validation"]=validate_transport(result,policy)
    if not result["logistics"]["validation"]["valid"]:
        raise ValueError(f"Independent logistics checks failed: {result['logistics']['validation']['errors']}")
    plan=build_assembly_plan(result,expected_bom)
    result["search"]["total_seconds"]=perf_counter()-started
    result["search"]["timing_scope"]="Prepared individual library through final geometry and assembly checks; includes preparation"
    plan["result_fingerprint"]=fingerprint(result)
    return result,plan
