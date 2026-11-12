"""Bounded two-part nesting: voxel proposals, independently checked mesh output.

The fixed first-part orientation and 24 rotations of the second are a restricted
search, not a global optimizer. Voxel occupancy is never a validity certificate.
"""

from hashlib import sha256
from itertools import permutations, product
import json
import math
from pathlib import Path
from time import perf_counter


def solve_mesh_pair(problem, time_limit=30, pitch_mm=2, candidates_per_rotation=12, voxel_cache=None, objective="volume"):
    import numpy as np
    import trimesh
    from scipy.signal import fftconvolve
    from scipy.ndimage import binary_dilation
    from .mesh_validation import validate_mesh_layout
    from .models import vector

    start = perf_counter()
    if not math.isfinite(time_limit) or time_limit <= 0 or not math.isfinite(pitch_mm) or pitch_mm <= 0:
        raise ValueError("Positive finite time_limit and pitch_mm required")
    if not isinstance(candidates_per_rotation, int) or candidates_per_rotation < 1:
        raise ValueError("candidates_per_rotation must be a positive integer")
    if objective not in ("volume","balanced"):raise ValueError("Unknown pair objective")
    if problem.get("units") != "mm":
        raise ValueError("Explicit mm units required")
    units, meshes, mesh_hashes = [], [], []
    for item in problem["items"]:
        quantity = item.get("quantity", 1)
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise ValueError("Quantities must be positive integers")
        ref = item["mesh"]
        path = Path(ref["path"])
        if sha256(path.read_bytes()).hexdigest() != ref["sha256"]:
            raise ValueError("Source hash mismatch")
        if path.suffix.lower() == ".3mf":
            from .mesh_geometry import load_instance_mesh
            data = load_instance_mesh(path, ref["instance_id"], ref.get("frame", "object"))
        else:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if data.get("units") != "mm":
                raise ValueError("Mesh JSON must use mm")
        mesh = trimesh.Trimesh(vertices=data["vertices_mm"], faces=data["triangles"], process=False)
        if not mesh.is_volume:
            raise ValueError("Pair search requires watertight positive-volume meshes")
        for index in range(quantity):
            units.append((item["id"], f'{item["id"]}#{index + 1}'))
            meshes.append(mesh.copy())
            mesh_hashes.append((ref["sha256"],ref.get("instance_id"),ref.get("frame","object")))
    if len(meshes) != 2 or len(set(u[1] for u in units)) != 2:
        raise ValueError("Pair search requires exactly two distinct unit instances")
    inner = np.array(vector(problem["container"]["inner_mm"], "inner_mm", True))
    reserved = problem["container"].get("reserved_top_mm", 0)
    if isinstance(reserved, bool) or not isinstance(reserved, (int, float)) or not math.isfinite(reserved) or reserved < 0:
        raise ValueError("Invalid reserved_top_mm")
    inner[2] -= reserved
    margin = np.array(vector(problem["container"].get("protection_mm", 0), "protection_mm"))
    if np.any(inner <= 2 * margin):
        raise ValueError("Protection and reserved space consume container")
    clearance = float(problem.get("clearance_mm", 0))
    if not math.isfinite(clearance) or clearance < 0:
        raise ValueError("Invalid clearance")
    transforms, grids = [], []
    cache_hits = 0
    for mesh,mesh_hash in zip(meshes,mesh_hashes):
        transform = np.eye(4)
        transform[:3, 3] = -mesh.bounds[0]
        transforms.append(transform)
        mesh.apply_transform(transform)
        cache_key = (*mesh_hash,pitch_mm)
        if voxel_cache is not None and cache_key in voxel_cache:
            grid = voxel_cache[cache_key]
            cache_hits += 1
        else:
            voxel = mesh.voxelized(pitch_mm).fill()
            # Only proposal grids are reused; source hashes and all retained
            # original triangle geometry are still checked on every call.
            if not np.allclose(voxel.transform[:3, 3], 0, atol=1e-8):
                raise ValueError("Unsupported nonzero normalized voxel origin")
            grid = voxel.matrix.astype(np.float32)
            grid.flags.writeable = False
            if voxel_cache is not None:
                voxel_cache[cache_key] = grid
        grids.append(grid)
    fixed, moving = meshes
    manager = trimesh.collision.CollisionManager()
    manager.add_object("fixed", fixed)
    samples = []
    for mesh in meshes:
        components = trimesh.graph.connected_components(mesh.edges_unique,nodes=np.arange(len(mesh.vertices)))
        samples.append(mesh.vertices[[int(c[0]) for c in components]])
    proposal_grids = [(grids[0],0)]
    if clearance > 0:
        radius = math.ceil(clearance/pitch_mm)
        coordinates = np.indices((2*radius+1,)*3)-radius
        sphere = np.sum(coordinates**2,axis=0) <= radius**2
        expanded = binary_dilation(np.pad(grids[0].astype(bool),radius),structure=sphere).astype(np.float32)
        proposal_grids.insert(0,(expanded,radius))
    search_started = perf_counter()
    checked, rotations_done, best, best_spread = 0, 0, None, -1.
    best_pose = None
    balance_padding=(sum(float(np.prod(m.extents)) for m in meshes)**(1/3))*.4 if objective=="balanced" else 0
    best_score=math.inf

    def accept(rotation, shift):
        nonlocal checked, best, best_spread, best_pose, best_score
        transform = np.eye(4)
        transform[:3, :3] = rotation
        transform[:3, 3] = shift
        candidate = moving.copy()
        candidate.apply_transform(transform)
        low = np.minimum(fixed.bounds[0], candidate.bounds[0])
        high = np.maximum(fixed.bounds[1], candidate.bounds[1])
        dimensions = high - low
        volume = float(np.prod(dimensions))
        score=float(np.prod(dimensions+balance_padding))
        spread = float(np.linalg.norm(candidate.bounds.mean(axis=0)-fixed.bounds.mean(axis=0)))
        if np.any(dimensions > inner - 2 * margin + 1e-8):
            return
        if best and (round(score,6),-spread) >= (round(best_score,6),-best_spread):
            return
        checked += 1
        if manager.in_collision_single(candidate):
            return
        if manager.min_distance_single(candidate) + 1e-8 < clearance:
            return
        # Query each immutable local mesh so its ray acceleration structure can
        # be reused. Rigid inverse mapping preserves the containment predicate.
        overlapping_bounds = np.all(np.minimum(fixed.bounds[1],candidate.bounds[1]) >
                                    np.maximum(fixed.bounds[0],candidate.bounds[0]))
        if overlapping_bounds:
            if moving.contains((samples[0]-shift)@rotation).any():
                return
            if fixed.contains(samples[1]@rotation.T+shift).any():
                return
        offset = np.eye(4)
        offset[:3, 3] = margin - low
        best = (volume, [offset @ transforms[0], offset @ transform @ transforms[1]], dimensions)
        best_spread = spread
        best_score=score
        best_pose = (rotation.copy(), shift.copy())

    # Always try simple non-nested adjacency as a valid fallback.
    for axis in range(3):
        shift = np.zeros(3)
        shift[axis] = fixed.extents[axis] + max(clearance, 0.01)
        accept(np.eye(3), shift)
    pending = {}
    proposal_budget = time_limit * .4
    for perm in permutations(range(3)):
        for signs in product((1, -1), repeat=3):
            if perf_counter() - search_started >= proposal_budget:
                break
            rotation = np.zeros((3, 3))
            for row, col in enumerate(perm):
                rotation[row, col] = signs[row]
            if np.linalg.det(rotation) < 0:
                continue
            grid = np.transpose(grids[1], perm)
            correction = np.zeros(3)
            for axis, sign in enumerate(signs):
                if sign < 0:
                    grid = np.flip(grid, axis=axis)
                    correction[axis] = (grid.shape[axis] - 1) * pitch_mm
            for proposal_grid,padded_cells in proposal_grids:
                if perf_counter()-search_started >= proposal_budget:
                    break
                correlations = fftconvolve(proposal_grid, grid[::-1, ::-1, ::-1], mode="full")
                indices = np.argwhere(correlations < 0.5)
                # Padding moves the proposal grid origin. Physical poses and
                # volume ranking must remain in the original source frame.
                shifts = indices-(np.array(grid.shape)-1)-padded_cells
                low = np.minimum(0, shifts)
                high = np.maximum(np.array(grids[0].shape), shifts+np.array(grid.shape))
                possible = np.all((high-low)*pitch_mm <= inner-2*margin+2*pitch_mm,axis=1)
                shifts,low,high = shifts[possible],low[possible],high[possible]
                volumes = np.prod(high-low+balance_padding/pitch_mm,axis=1)
                count = min(candidates_per_rotation,len(volumes))
                if count:
                    selected = np.argpartition(volumes,count-1)[:count]
                    for index in selected[np.argsort(volumes[selected])]:
                        if perf_counter()-search_started >= proposal_budget:
                            break
                        shift = correction+shifts[index]*pitch_mm
                        corners = np.array([moving.bounds[0],moving.bounds[1]])
                        rotated = corners @ rotation.T + shift
                        lo = np.minimum(fixed.bounds[0],rotated.min(axis=0))
                        hi = np.maximum(fixed.bounds[1],rotated.max(axis=0))
                        volume = float(np.prod(hi-lo+balance_padding))
                        key = (*rotation.ravel(),*shift)
                        pending[key] = (volume,rotation.copy(),shift.copy())
            rotations_done += 1
        if perf_counter() - search_started >= proposal_budget:
            break
    proposal_seconds = perf_counter()-search_started
    # Exact checks must compete across orientations, rather than allowing the
    # first expensive orientation to consume the entire short search budget.
    for _,rotation,shift in sorted(pending.values(),key=lambda p:p[0]):
        if perf_counter()-search_started >= time_limit*.8:
            break
        accept(rotation,shift)
    # Coarse voxel translations are proposals, not manufacturing coordinates.
    # Refine the best exact pose with decreasing physical steps. Every accepted
    # move still passes original-triangle distance and containment checks.
    refinement_started = perf_counter()
    for step in (pitch_mm/2, pitch_mm/4, pitch_mm/8):
        for _ in range(16):
            if best_pose is None or perf_counter()-search_started>=time_limit:break
            rotation,shift=best_pose
            previous=best_score
            for axis in range(3):
                for sign in (-1,1):
                    if perf_counter()-search_started>=time_limit:break
                    trial=shift.copy();trial[axis]+=sign*step
                    accept(rotation,trial)
            if best_score>=previous-1e-7:break
    refinement_seconds=perf_counter()-refinement_started
    result = {"units": "mm", "status": "no_verified_candidate", "placements": [],
              "scope": "two_part_static_mesh_nesting",
              "search": {"pitch_mm": pitch_mm, "checked_mesh_candidates": checked,
                         "objective":objective,"shape_balance_padding_mm":balance_padding,
                         "rotations_checked": rotations_done,
                         "orientation_proposals":len(pending), "proposal_seconds":proposal_seconds,
                         "translation_refinement_seconds":refinement_seconds,
                         "rotation_count_scope":"Rotations with voxel proposals; exact candidates are counted separately", "elapsed_seconds": perf_counter() - start,
                         "preparation_seconds": search_started - start,
                         "voxel_cache_hits": cache_hits,
                         "proposal_clearance_dilation": clearance > 0,
                         "equal_volume_tiebreak":"Separate part centres to avoid occupying the middle of a reusable cavity",
                         "search_seconds": perf_counter() - search_started,
                         "time_limit_seconds": time_limit, "optimality_proven": False}}
    verification_started = perf_counter()
    if best:
        result["placements"] = [{"item_id": iid, "unit_id": uid, "transform": transform.tolist()}
                                for (iid, uid), transform in zip(units, best[1])]
        result["envelope_mm"] = best[2].tolist()
        result["envelope_volume_l"] = best[0] / 1e6
        result["separate_envelope_volume_l"] = sum(float(np.prod(mesh.extents)) for mesh in meshes) / 1e6
        result["validation"] = validate_mesh_layout(problem, result)
        if result["validation"]["valid"]:
            result["status"] = "validated_static_layout"
        else:
            result["status"] = "candidate_failed_independent_validation"
    result["search"]["total_elapsed_seconds_including_validation"] = perf_counter() - start
    result["search"]["verification_seconds"] = perf_counter() - verification_started
    result["search"]["time_budget_scope"] = "Search-only soft bound checked between proposals; preparation and final verification are timed separately"
    return result
