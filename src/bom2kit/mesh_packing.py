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


def solve_mesh_pair(problem, time_limit=30, pitch_mm=2, candidates_per_rotation=12):
    import numpy as np
    import trimesh
    from scipy.signal import fftconvolve
    from .mesh_validation import validate_mesh_layout
    from .models import vector

    start = perf_counter()
    if not math.isfinite(time_limit) or time_limit <= 0 or not math.isfinite(pitch_mm) or pitch_mm <= 0:
        raise ValueError("Positive finite time_limit and pitch_mm required")
    if not isinstance(candidates_per_rotation, int) or candidates_per_rotation < 1:
        raise ValueError("candidates_per_rotation must be a positive integer")
    if problem.get("units") != "mm":
        raise ValueError("Explicit mm units required")
    units, meshes = [], []
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
    for mesh in meshes:
        transform = np.eye(4)
        transform[:3, 3] = -mesh.bounds[0]
        transforms.append(transform)
        mesh.apply_transform(transform)
        voxel = mesh.voxelized(pitch_mm).fill()
        # Normalized min bounds yield a zero voxel-grid origin. Explicit check
        # avoids silently confusing voxel indices with physical coordinates.
        if not np.allclose(voxel.transform[:3, 3], 0, atol=1e-8):
            raise ValueError("Unsupported nonzero normalized voxel origin")
        grids.append(voxel.matrix.astype(np.float32))
    fixed, moving = meshes
    manager = trimesh.collision.CollisionManager()
    manager.add_object("fixed", fixed)
    checked, rotations_done, best = 0, 0, None

    def accept(rotation, shift):
        nonlocal checked, best
        transform = np.eye(4)
        transform[:3, :3] = rotation
        transform[:3, 3] = shift
        candidate = moving.copy()
        candidate.apply_transform(transform)
        low = np.minimum(fixed.bounds[0], candidate.bounds[0])
        high = np.maximum(fixed.bounds[1], candidate.bounds[1])
        dimensions = high - low
        volume = float(np.prod(dimensions))
        if np.any(dimensions > inner - 2 * margin + 1e-8) or (best and volume >= best[0]):
            return
        checked += 1
        if manager.in_collision_single(candidate):
            return
        for source, target in ((fixed, candidate), (candidate, fixed)):
            components = trimesh.graph.connected_components(source.edges_unique, nodes=np.arange(len(source.vertices)))
            if target.contains(source.vertices[[int(c[0]) for c in components]]).any():
                return
        if manager.min_distance_single(candidate) + 1e-8 < clearance:
            return
        offset = np.eye(4)
        offset[:3, 3] = margin - low
        best = (volume, [offset @ transforms[0], offset @ transform @ transforms[1]], dimensions)

    # Always try simple non-nested adjacency as a valid fallback.
    for axis in range(3):
        shift = np.zeros(3)
        shift[axis] = fixed.extents[axis] + max(clearance, 0.01)
        accept(np.eye(3), shift)
    for perm in permutations(range(3)):
        for signs in product((1, -1), repeat=3):
            if perf_counter() - start >= time_limit:
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
            correlations = fftconvolve(grids[0], grid[::-1, ::-1, ::-1], mode="full")
            indices = np.argwhere(correlations < 0.5)
            shifts = indices - (np.array(grid.shape) - 1)
            low = np.minimum(0, shifts)
            high = np.maximum(np.array(grids[0].shape), shifts + np.array(grid.shape))
            # Rank candidates inside the requested aspect constraints first.
            # One pitch of slack per face accounts for voxel rounding; exact
            # transformed-vertex bounds remain the acceptance criterion.
            possible = np.all((high - low) * pitch_mm <= inner - 2 * margin + 2 * pitch_mm, axis=1)
            shifts, low, high = shifts[possible], low[possible], high[possible]
            volumes = np.prod(high - low, axis=1)
            count = min(candidates_per_rotation, len(volumes))
            if count:
                selected = np.argpartition(volumes, count - 1)[:count]
                for index in selected[np.argsort(volumes[selected])]:
                    if perf_counter() - start >= time_limit:
                        break
                    accept(rotation, correction + shifts[index] * pitch_mm)
            rotations_done += 1
        if perf_counter() - start >= time_limit:
            break
    result = {"units": "mm", "status": "no_verified_candidate", "placements": [],
              "scope": "two_part_static_mesh_nesting",
              "search": {"pitch_mm": pitch_mm, "checked_mesh_candidates": checked,
                         "rotations_checked": rotations_done, "elapsed_seconds": perf_counter() - start,
                         "time_limit_seconds": time_limit, "optimality_proven": False}}
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
    result["search"]["time_budget_scope"] = "soft bound checked between proposals; preprocessing and final validation may exceed it"
    return result
