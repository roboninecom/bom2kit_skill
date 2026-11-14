"""Independent floor-contact and simplified two-finger access checks."""
from collections import Counter
import math
from time import perf_counter

from .practical_geometry import load_mesh, contact_certificate


def fingertip_candidates(mesh, radius, depth, length):
    """Try an outer pinch first, then accessible local cross-sections of the real CAD."""
    import numpy as np
    import trimesh
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    bounds=mesh.bounds;seen=set()
    def emit(axis,left,right,across,z,actual_depth):
        key=(axis,round(left,3),round(right,3),round(across,3),round(z,3))
        if key in seen:return None
        seen.add(key);fingers=[]
        for value,sign in ((left,-1),(right,1)):
            center=bounds.mean(0)
            center[axis]=value+sign*(radius+.1);center[1-axis]=across;center[2]=z+length/2
            finger=trimesh.creation.cylinder(radius=radius,height=length,sections=24)
            finger.apply_translation(center);fingers.append(finger)
        return axis,fingers,actual_depth
    actual_depth=min(depth,mesh.extents[2]*.8)
    for axis in (0,1):
        candidate=emit(axis,bounds[0,axis],bounds[1,axis],bounds.mean(0)[1-axis],bounds[1,2]-actual_depth,actual_depth)
        if candidate:yield candidate
    for actual_depth in sorted({min(depth,mesh.extents[2]*.8),min(3.,mesh.extents[2]*.5)},reverse=True):
        z=bounds[1,2]-actual_depth
        segments=trimesh.intersections.mesh_plane(mesh,[0,0,1],[0,0,z])
        if not len(segments):continue
        region=unary_union(list(polygonize([LineString(segment[:,:2]) for segment in segments])))
        if region.is_empty:continue
        for axis in (0,1):
            for fraction in (.5,.25,.75):
                across=bounds[0,1-axis]+mesh.extents[1-axis]*fraction
                a=bounds[0,:2].copy()-1;b=bounds[1,:2].copy()+1
                a[1-axis]=b[1-axis]=across
                section=region.intersection(LineString([a,b]))
                pieces=list(section.geoms) if hasattr(section,'geoms') else [section]
                for piece in pieces:
                    if piece.geom_type!='LineString' or piece.length<1e-6:continue
                    coords=np.asarray(piece.coords)
                    candidate=emit(axis,coords[:,axis].min(),coords[:,axis].max(),across,z,actual_depth)
                    if candidate:yield candidate


def check_floor_support(result):
    """Check original parts against explicitly modeled flat protective liners."""
    import numpy as np
    errors, records = [], []
    practical = result.get("practical", {})
    liner = practical.get("floor_liner_mm")
    if not isinstance(liner, (float, int)) or not math.isfinite(liner) or liner <= 0:
        return {"valid": False, "errors": ["A positive specified floor liner is required"]}
    if any(len(members) > 1 for members in result.get("groups", {}).values()):
        errors.append("Unrestrained multipart handling groups are forbidden")
    poses = {p["unit_id"]: p for p in result["layout"]["placements"]}
    sources = {i["id"]: load_mesh(i) for i in result["input"]["items"]}
    layers = {l["id"]: l for l in result["envelope_design"]["candidate"]["layout"]["layers"]}
    liners = practical.get("floor_liners", [])
    if Counter(p.get("carton_id") for p in liners) != Counter(layers.keys()):
        errors.append("Every carton requires exactly one modeled floor liner")
    packaging = result["envelope_design"]["candidate"].get("packaging_bom", [])
    for panel in liners:
        layer = layers.get(panel.get("carton_id"))
        if layer is None:
            continue
        if panel not in packaging or panel.get("quantity") != 1 or not np.allclose(panel["dimensions_mm"], [*layer["inner_mm"][:2],liner],atol=1e-8,rtol=0) or not np.allclose(panel["origin_mm"], np.asarray(layer["position_mm"])+layer["wall_mm"],atol=1e-8,rtol=0):
            errors.append("Floor liner geometry/BOM differs from the supporting surface")
    if liner != result["logistics"]["policy"]["item_padding_mm"]:
        errors.append("Floor liner must occupy the unchanged declared bottom allowance")
    seen = [];placed_meshes={}
    for module in result["logistics"]["modules"]:
        layer = layers[module["id"]]
        floor = layer["position_mm"][2]+layer["wall_mm"]+liner
        for uid in module["unit_ids"]:
            seen.append(uid)
            pose = poses[uid]
            mesh = sources[pose["item_id"]].copy(); mesh.apply_transform(pose["transform"])
            placed_meshes[uid]=mesh
    if Counter(seen) != Counter(poses.keys()):
        errors.append("Support check must cover every source unit once")
    from .regular_stacks import check_stack_support
    stack=check_stack_support(result,placed_meshes,layers,liner)
    errors.extend(stack['errors']);records=stack['parts']
    from .planar_validation import check_projection_binding
    projection = check_projection_binding(result)
    errors.extend(projection['errors'])
    return {"valid": not errors, "errors": errors, "parts": records,
            "floor_liner_mm": liner, "physical_qualification": False,
            "limitations": ["Uniform-density source solids; declared packing envelopes approximate contents.",
                            "Geometric quasistatic floor support only; no material strength or shipping restraint approval."]}


def check_hand_access(result, *, radius_mm=4., insertion_depth_mm=8., finger_length_mm=24., time_limit=90.):
    """Find a reverse-removal order with two cylindrical fingertips per part.

    The fingers descend beside opposite bounding faces. Distance-bounded rigid
    translations check the whole removal sweep. Actual grasp contacts, skin
    deformation, gloves, wrist reach and grip force remain unqualified.
    """
    import numpy as np
    import trimesh
    started = perf_counter()
    if any(not math.isfinite(v) or v <= 0 for v in (radius_mm, insertion_depth_mm, finger_length_mm,time_limit)):
        raise ValueError("Positive finite hand-access parameters required")
    if finger_length_mm < insertion_depth_mm:
        raise ValueError("Fingers must extend above the grasp depth")
    sources = {i["id"]: load_mesh(i) for i in result["input"]["items"]}
    meshes = {}
    for pose in result["layout"]["placements"]:
        mesh = sources[pose["item_id"]].copy(); mesh.apply_transform(pose["transform"])
        meshes[pose["unit_id"]] = mesh
    layers = {l["id"]: l for l in result["envelope_design"]["candidate"]["layout"]["layers"]}
    sheet_meshes={}
    for sheet in result.get('practical',{}).get('protective_separators',[]):
        size=np.asarray(sheet['dimensions_mm'])
        panel=trimesh.creation.box(size-.002);panel.apply_translation(np.asarray(sheet['origin_mm'])+size/2)
        sheet_meshes[sheet['id']]=panel
    cartons, failures = [], []
    # These world-space source and sheet meshes remain immutable during this
    # check. Reuse their BVH/Convex geometry across independent collision objects;
    # moving-part/finger composites and their transforms are never cached here.
    fixed_ids = {id(mesh) for mesh in [*meshes.values(), *sheet_meshes.values()]}
    geometry_cache = {}; geometry_cache_hits = 0
    class SourceCollisionManager(trimesh.collision.CollisionManager):
        def _get_fcl_obj(self, mesh):
            nonlocal geometry_cache_hits
            key = id(mesh)
            if key not in fixed_ids:
                return super()._get_fcl_obj(mesh)
            if key not in geometry_cache:
                geometry_cache[key] = super()._get_fcl_obj(mesh)
            else:
                geometry_cache_hits += 1
            return geometry_cache[key]
    for module in result["logistics"]["modules"]:
        layer = layers[module["id"]]
        low = np.asarray(layer["position_mm"])+layer["wall_mm"]
        high = low+layer["inner_mm"]
        remaining = set(module["unit_ids"])
        removals = []
        from .regular_stacks import removal_stability_checker
        sheets=[s for s in result.get('practical',{}).get('protective_separators',[]) if s['carton_id']==module['id']]
        stable=removal_stability_checker({uid:meshes[uid] for uid in remaining},sheets,low[2]+result['practical']['floor_liner_mm'])
        if not stable(remaining):
            failures.append({'carton_id':module['id'],'unresolved_units':sorted(remaining),'reason':'initial_support_unstable'})
            continue
        while remaining and perf_counter()-started < time_limit:
            accepted = False
            for uid in sorted(remaining,key=lambda uid:(-meshes[uid].bounds[1,2],uid)):
                if any(s['lower_unit_id']==uid and s['upper_unit_id'] in remaining
                       for s in result.get('practical',{}).get('protective_separators',[])):
                    continue
                if not stable(remaining-{uid}):continue
                mesh = meshes[uid];bounds = mesh.bounds
                own=SourceCollisionManager();own.add_object('part',mesh)
                for axis,fingers,depth in fingertip_candidates(mesh,radius_mm,insertion_depth_mm,finger_length_mm):
                    if perf_counter()-started>=time_limit:break
                    if any(np.any(f.bounds[0,:2]<low[:2]-1e-7) or np.any(f.bounds[1,:2]>high[:2]+1e-7) for f in fingers):
                        continue
                    if any(own.in_collision_single(finger) or own.min_distance_single(finger)<.01 for finger in fingers):
                        continue
                    moving = trimesh.util.concatenate([mesh,*fingers])
                    manager = SourceCollisionManager()
                    # Expanded XY broad phase includes fingers; obstacles remain original triangles.
                    for other in remaining-{uid}:
                        obstacle = meshes[other]
                        if all(moving.bounds[1,k] >= obstacle.bounds[0,k] and moving.bounds[0,k] <= obstacle.bounds[1,k] for k in (0,1)):
                            manager.add_object(other,obstacle)
                    # Each sheet is removed immediately after its upper part.
                    # Other active sheets can obstruct a finger even where the
                    # neighboring source mesh itself has an empty cavity.
                    for sheet in sheets:
                        if sheet['upper_unit_id'] not in remaining or sheet['upper_unit_id']==uid:continue
                        obstacle=sheet_meshes[sheet['id']]
                        if all(moving.bounds[1,k]>=obstacle.bounds[0,k] and moving.bounds[0,k]<=obstacle.bounds[1,k] for k in (0,1)):
                            manager.add_object('protective-sheet:'+sheet['id'],obstacle)
                    moving_manager = SourceCollisionManager()
                    moving_manager.add_object("moving",moving)
                    travel = max(0.,high[2]-moving.bounds[0,2])+1
                    moved = 0.;passed = False
                    while perf_counter()-started < time_limit:
                        distance = manager.min_distance_other(moving_manager)
                        if np.isinf(distance) or moved >= travel:
                            passed = True;break
                        if not math.isfinite(distance) or distance <= 1e-5:
                            break
                        step = min(distance*.45,travel-moved)
                        moved += step
                        transform = np.eye(4);transform[2,3] = moved
                        moving_manager.set_transform("moving",transform)
                    if passed:
                        removals.append({"unit_id": uid,"axis": "XY"[axis],"finger_centers_mm": [f.bounds.mean(0).tolist() for f in fingers],
                                         "direction": "+Z","grasp_depth_mm": depth})
                        remaining.remove(uid);accepted = True;break
                if accepted:break
            if not accepted:break
        if remaining:
            failures.append({"carton_id":module["id"],"unresolved_units":sorted(remaining),
                             'reason':'time_budget_exhausted' if perf_counter()-started>=time_limit else 'no_checked_grip_sequence'})
        cartons.append({"carton_id":module["id"],"removal_sequence":removals,
                        "packing_sequence":[{**s,"direction":"-Z"} for s in reversed(removals)] if not remaining else []})
    return {"valid":not failures,"failures":failures,"cartons":cartons,
            "parameters":{"radius_mm":radius_mm,"insertion_depth_mm":insertion_depth_mm,"finger_length_mm":finger_length_mm},
            "seconds":perf_counter()-started,"physical_qualification":False,
            "immutable_geometry_cache":{"geometries":len(geometry_cache),"hits":geometry_cache_hits,
                                        "scope":"One replay; unchanged original source and sheet meshes only"},
            "intermediate_load_states_checked":True,
            "protective_sheet_obstacles_checked":True,
            "scope":"Two fingertip clearance and rigid vertical sweep; actual manual grip is not certified"}


def complexity_metrics(result):
    """Count actual placements and compound handling, never invent labor seconds."""
    from .packing_states import audit_states
    groups = result.get("groups",{})
    compounds = [g for g in groups.values() if len(g)>1]
    units = len(result["layout"]["placements"])
    original = {p["unit_id"]:p["item_id"] for p in result["layout"]["placements"]}
    split_skus = Counter()
    orientations = {}
    for p in result['layout']['placements']:
        key = tuple(round(p['transform'][i][j],3) for i in range(3) for j in range(3))
        orientations.setdefault(p['item_id'],set()).add(key)
    for m in result["logistics"]["modules"]:
        split_skus.update(set(original[uid] for uid in m["unit_ids"]))
    return {"external_volume_l":result["envelope_design"]["candidate"]["volume_mm3"]/1e6,
            "cartons":result["logistics"]["carton_count"],"carton_types":result["logistics"]["carton_types"],
            "packing_units":units,"compound_preassemblies":len(compounds),
            "placements_into_cartons":units-sum(len(g)-1 for g in compounds),
            "placements_inside_compounds":sum(len(g) for g in compounds),
            "total_counted_placements":units+len(compounds),
            "protective_sheet_placements":len(result.get('practical',{}).get('protective_separators',[])),
            "floor_liner_placements":len(result.get('practical',{}).get('floor_liners',[])),
            "source_and_contact_sheet_placements":units+len(compounds)+len(result.get('practical',{}).get('protective_separators',[])),
            "contact_sheet_sizes":len({tuple(round(v,2) for v in sorted(s['dimensions_mm'][:2])+s['dimensions_mm'][2:])
                                       for s in result.get('practical',{}).get('protective_separators',[])}),
            "compound_templates":len(result.get('group_certificates',[])),
            "max_compound_members":max((len(g) for g in compounds),default=1),
            "additional_sku_orientations":sum(len(v)-1 for v in orientations.values()),
            "split_source_skus":sum(n>1 for n in split_skus.values()),
            "packing_states":audit_states(result["input"])["packing_unit_counts"],
            "manual_seconds":None,"supplier_cost":None}
