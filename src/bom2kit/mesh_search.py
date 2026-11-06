"""Experimental bounded beam search for complete static mesh manifests.

Voxel correlation proposes placements; retained branches receive mesh collision
checks, and a complete candidate must pass the independent manifest validator.
No support/insertion or physical packing certificate is implied.
"""

from dataclasses import dataclass
from hashlib import sha256
from itertools import permutations, product
import json
import math
from pathlib import Path
from time import perf_counter


@dataclass
class _State:
    grid: object
    placements: list
    meshes: list
    bounds: object
    score: float


def solve_mesh_kit(problem, time_limit=600, beam_width=16, pitch_mm=2,
                   positions_per_rotation=8, order=None, checkpoint_dir=None,
                   progress=None, seed_placements=None, lookahead=False, cache_dir=None,
                   voxel_overlap_cells=0):
    """Search a fixed cavity using a beam of alternate rigid placements.

    Input uses mesh_validation's JSON-file manifest. Optional item orientation_hint
    is a proper 3x3 rotation; otherwise the raw mesh orientation is retained.
    Order is an explicit list of unit IDs. Time limit is soft around FFT and final
    validation operations. Returned partial states never claim a complete fit.
    voxel_overlap_cells relaxes only coarse candidate generation; all accepted
    placements still receive the same triangle collision and clearance checks.
    """
    import numpy as np
    import trimesh
    from scipy.fft import rfftn, irfftn, next_fast_len
    from .mesh_validation import validate_mesh_layout
    from .models import vector

    started = perf_counter()
    if isinstance(voxel_overlap_cells, bool) or not isinstance(voxel_overlap_cells, int) or voxel_overlap_cells < 0:
        raise ValueError("voxel_overlap_cells must be a nonnegative integer")
    if (not math.isfinite(time_limit) or time_limit <= 0 or not math.isfinite(pitch_mm)
            or pitch_mm <= 0 or isinstance(beam_width, bool) or not isinstance(beam_width, int)
            or beam_width < 1 or not isinstance(positions_per_rotation, int) or positions_per_rotation < 1):
        raise ValueError("Invalid search budget or beam configuration")
    if problem.get("units") != "mm":
        raise ValueError("Explicit mm units required")
    inner = np.array(vector(problem["container"]["inner_mm"], "inner_mm", True))
    margin = np.array(vector(problem["container"].get("protection_mm", 0), "protection_mm"))
    reserve = problem["container"].get("reserved_top_mm", 0)
    if isinstance(reserve, bool) or not isinstance(reserve, (int, float)) or not math.isfinite(reserve) or reserve < 0:
        raise ValueError("Invalid reserved top")
    inner[2] -= reserve
    usable = inner - 2 * margin
    if np.any(usable <= 0):
        raise ValueError("No usable cavity")
    clearance = problem.get("clearance_mm", 0)
    if isinstance(clearance, bool) or not isinstance(clearance, (int, float)) or not math.isfinite(clearance) or clearance < 0:
        raise ValueError("Invalid clearance")
    shape = np.floor(usable / pitch_mm).astype(int) + 1
    quantities = [item.get("quantity", 1) for item in problem.get("items", [])]
    if (seed_placements and quantities
            and all(isinstance(q, int) and not isinstance(q, bool) and q > 0 for q in quantities)
            and len(seed_placements) == sum(quantities)):
        # Complete reusable recipes require one fresh certificate, not a new
        # voxel search. The validator binds every mesh to its supplied hash.
        certificate = validate_mesh_layout(problem, {"units": "mm", "placements": seed_placements})
        if not certificate["valid"]:
            raise ValueError(f"Invalid seed placements: {certificate['errors']}")
        result = {"units": "mm", "placements": seed_placements,
                  "status": "validated_static_layout", "mode": "validated_seed_replay",
                  "validation": certificate,
                  "search": {"history": [], "elapsed_seconds": perf_counter() - started,
                             "optimality_proven": False}}
        if checkpoint_dir:
            directory = Path(checkpoint_dir)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "problem.json").write_text(json.dumps(problem, indent=2), encoding="utf8")
            (directory / "layout.json").write_text(json.dumps(result, indent=2), encoding="utf8")
        return result
    if np.prod(shape) > 20_000_000:
        raise ValueError("Voxel cavity too large; increase pitch")
    rotations = []
    cache_root = Path(cache_dir) if cache_dir else (Path(checkpoint_dir).parent / "mesh-voxel-cache" if checkpoint_dir else None)
    if cache_root:
        cache_root.mkdir(parents=True, exist_ok=True)
    for permutation in permutations(range(3)):
        for signs in product((1, -1), repeat=3):
            rotation = np.zeros((3, 3))
            rotation[np.arange(3), permutation] = signs
            if np.linalg.det(rotation) > 0:
                rotations.append(rotation)
    data, expected, originals = {}, {}, {}
    seeded_ids = {pose.get("unit_id") for pose in (seed_placements or []) if isinstance(pose, dict)}
    for item in problem["items"]:
        iid, quantity = item["id"], item.get("quantity", 1)
        if not isinstance(iid, str) or not iid or iid in data:
            raise ValueError("Unique nonempty item IDs required")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise ValueError("Positive integer quantity required")
        ref = item["mesh"]
        path = Path(ref["path"])
        source_bytes = path.read_bytes()
        if sha256(source_bytes).hexdigest() != ref["sha256"]:
            raise ValueError(f"Source hash mismatch: {iid}")
        source = json.loads(source_bytes.decode("utf-8-sig"))
        if source.get("units") != "mm":
            raise ValueError("Mesh JSON must explicitly use mm")
        mesh = trimesh.Trimesh(source["vertices_mm"], source["triangles"], process=False)
        if not mesh.is_volume or np.any(mesh.area_faces <= 0):
            raise ValueError(f"Source must be a nondegenerate watertight positive mesh: {iid}")
        originals[iid] = mesh.copy()
        item_units = {f"{iid}#{index + 1}": iid for index in range(quantity)}
        if set(item_units).issubset(seeded_ids):
            # A partial recipe may already contain every unit of this type.
            # Keep source geometry for validation and seed occupancy, but no
            # orientation candidates are needed for an already placed type.
            data[iid] = []
            expected.update(item_units)
            continue
        align = np.eye(4)
        hint = np.asarray(item.get("orientation_hint", np.eye(3)), dtype=float)
        if (hint.shape != (3, 3) or not np.isfinite(hint).all()
                or not np.allclose(hint.T @ hint, np.eye(3), atol=1e-9, rtol=0)
                or not np.isclose(np.linalg.det(hint), 1, atol=1e-9, rtol=0)):
            raise ValueError("orientation_hint must be a proper rotation")
        align[:3, :3] = hint
        mesh.apply_transform(align)
        align[:3, 3] = -mesh.bounds[0]
        mesh.apply_translation(align[:3, 3])
        cache_key = sha256(json.dumps({"source_sha256": ref["sha256"], "align": align.tolist(),
                                      "pitch_mm": pitch_mm, "trimesh": trimesh.__version__, "schema": 1}, sort_keys=True).encode()).hexdigest()
        cache_path = cache_root / f"{cache_key}.npz" if cache_root else None
        grid = None
        if cache_path and cache_path.exists():
            try:
                with np.load(cache_path, allow_pickle=False) as cached:
                    candidate_grid = cached["grid"]
                    if candidate_grid.ndim == 3 and candidate_grid.dtype == bool:
                        grid = candidate_grid.astype(np.float32)
            except (OSError, ValueError, KeyError):
                grid = None
        if grid is None:
            voxels = mesh.voxelized(pitch_mm).fill()
            if not np.allclose(voxels.transform[:3, 3], 0, atol=1e-8):
                raise ValueError("Unexpected normalized voxel origin")
            grid = voxels.matrix.astype(np.float32)
            if cache_path:
                np.savez_compressed(cache_path, grid=grid.astype(bool))
        orientations, fingerprints = [], set()
        for rotation in rotations:
            perm = np.argmax(np.abs(rotation), axis=1)
            signs = rotation[np.arange(3), perm]
            rotated = np.transpose(grid, perm)
            correction = np.zeros(3)
            for axis, sign in enumerate(signs):
                if sign < 0:
                    rotated = np.flip(rotated, axis=axis)
                    correction[axis] = (rotated.shape[axis] - 1) * pitch_mm
            if np.any(np.array(rotated.shape) > shape):
                continue
            fingerprint = (rotated.shape, sha256(rotated.tobytes()).hexdigest())
            if fingerprint in fingerprints:
                continue
            fingerprints.add(fingerprint)
            transform = np.eye(4)
            transform[:3, :3], transform[:3, 3] = rotation, correction
            rotated_mesh = mesh.copy()
            rotated_mesh.apply_transform(transform)
            # Grid-centre reflection rounds the physical extent to pitch.
            # Normalize the actual rotated geometry separately so a sub-pitch
            # rounding residual cannot consume a full pitch of cavity height.
            # The raster remains a proposal proxy; exact acceptance uses mesh.
            offset = -rotated_mesh.bounds[0]
            transform[:3, 3] += offset
            rotated_mesh.apply_translation(offset)
            orientations.append({"grid": np.ascontiguousarray(rotated), "mesh": rotated_mesh,
                                 "transform": transform @ align, "bounds": rotated_mesh.bounds.copy()})
        data[iid] = orientations
        for index in range(quantity):
            expected[f"{iid}#{index + 1}"] = iid
    units = list(expected) if order is None else list(order)
    if not expected or len(units) != len(expected) or set(units) != set(expected):
        raise ValueError("Order must contain each expected unit exactly once")
    directory = Path(checkpoint_dir) if checkpoint_dir else None
    if directory:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "problem.json").write_text(json.dumps(problem, indent=2), encoding="utf8")
    initial_grid = np.zeros(shape, dtype=np.float32)
    initial_meshes, initial_placements = [], []
    initial_bounds = np.zeros(3)
    if seed_placements:
        counts = {}
        for pose in seed_placements:
            iid = pose["item_id"]
            counts[iid] = counts.get(iid, 0) + 1
        partial_problem = {**problem, "items": [{**item, "quantity": counts[item["id"]]}
                           for item in problem["items"] if item["id"] in counts]}
        certificate = validate_mesh_layout(partial_problem, {"units": "mm", "placements": seed_placements})
        if not certificate["valid"]:
            raise ValueError(f"Invalid seed placements: {certificate['errors']}")
        seeded = set()
        for pose in seed_placements:
            if pose["unit_id"] not in expected or pose["unit_id"] in seeded:
                raise ValueError("Seed unit is not unique in complete manifest")
            seeded.add(pose["unit_id"])
            mesh = originals[pose["item_id"]].copy()
            mesh.apply_transform(pose["transform"])
            mesh.apply_translation(-margin)
            voxels = mesh.voxelized(pitch_mm).fill()
            indices = np.rint(voxels.points / pitch_mm).astype(int)
            indices = indices[np.all((indices >= 0) & (indices < shape), axis=1)]
            initial_grid[tuple(indices.T)] = 1
            initial_meshes.append(mesh)
            initial_placements.append(pose)
            initial_bounds = np.maximum(initial_bounds, mesh.bounds[1])
        units = [uid for uid in units if uid not in seeded]
    beam = [_State(initial_grid, initial_placements, initial_meshes, initial_bounds, float(np.prod(initial_bounds)))]
    best = beam[0]
    if not units:
        certificate = validate_mesh_layout(problem, {"units": "mm", "placements": initial_placements})
        result = {"units": "mm", "placements": initial_placements,
                  "status": "validated_static_layout" if certificate["valid"] else "complete_candidates_failed_validation",
                  "mode": "validated_seed_replay", "validation": certificate,
                  "search": {"history": [], "elapsed_seconds": perf_counter() - started, "optimality_proven": False}}
        if directory:
            (directory / "layout.json").write_text(json.dumps(result, indent=2), encoding="utf8")
        return result
    history = []
    checks = 0
    forward_rejections = 0
    reason = "search_exhausted"

    for depth, uid in enumerate(units):
        if perf_counter() - started >= time_limit:
            reason = "time_limit"
            break
        candidates = []
        kernel_spectra = {}
        forward_kernels = {}
        iid = expected[uid]
        for parent_index, state in enumerate(beam):
            if perf_counter() - started >= time_limit:
                break
            parent_spectra = {}
            for oi, orientation in enumerate(data[iid]):
                if perf_counter() - started >= time_limit:
                    break
                grid = orientation["grid"]
                if not state.placements:
                    # A reflected voxel grid can round its last centre below
                    # the actual mesh extent. Anchor at the first legal index,
                    # rather than discarding this physically valid orientation.
                    shifts = np.ceil(np.maximum(0, -orientation["bounds"][0]) / pitch_mm).astype(int)[None, :]
                else:
                    padded = tuple(next_fast_len(int(a + b - 1), real=True)
                                   for a, b in zip(state.grid.shape, grid.shape))
                    if padded not in parent_spectra:
                        parent_spectra[padded] = rfftn(state.grid, s=padded)
                    if oi not in kernel_spectra:
                        kernel_spectra[oi] = rfftn(grid[::-1, ::-1, ::-1], s=padded)
                    convolution = irfftn(parent_spectra[padded] * kernel_spectra[oi], s=padded)
                    valid_slices = tuple(slice(b - 1, a) for a, b in zip(state.grid.shape, grid.shape))
                    correlation = convolution[valid_slices]
                    shifts = np.argwhere(correlation < voxel_overlap_cells + 0.5)
                if not len(shifts):
                    continue
                low = shifts * pitch_mm + orientation["bounds"][0]
                high = shifts * pitch_mm + orientation["bounds"][1]
                legal = np.all(low >= -1e-8, axis=1) & np.all(high <= usable + 1e-8, axis=1)
                shifts, high = shifts[legal], high[legal]
                if not len(shifts):
                    continue
                bounds = np.maximum(high, state.bounds)
                scores = np.prod(bounds, axis=1) + shifts[:, 2] * pitch_mm * 100
                # Include spatial extremes, not only nearly identical neighbours
                # of the minimum-volume pose. This is essential for later parts.
                chosen = []
                if voxel_overlap_cells and state.placements:
                    overlaps = np.maximum(0, np.rint(correlation[tuple(shifts.T)]))
                    # Preserve proposals from different proxy-overlap bands,
                    # instead of allowing colliding low-volume poses to crowd
                    # out physically valid candidates hidden by coarse voxels.
                    edges = sorted(set([0, 1, max(2, voxel_overlap_cells // 4),
                                        max(3, voxel_overlap_cells // 2), voxel_overlap_cells + 1]))
                    for lower, upper in zip(edges, edges[1:]):
                        indices = np.flatnonzero((overlaps >= lower) & (overlaps < upper))
                        if len(indices):
                            chosen.append(int(indices[np.argmin(scores[indices])]))
                ranked = np.argsort(scores)[:min(256, len(scores))]
                for j in ranked:
                    if not chosen or all(np.linalg.norm((shifts[j] - shifts[k]) * pitch_mm) >= 12 for k in chosen):
                        chosen.append(int(j))
                    if len(chosen) >= max(1, positions_per_rotation // 2):
                        break
                for axis in range(3):
                    for j in (int(np.argmin(shifts[:, axis])), int(np.argmax(shifts[:, axis]))):
                        if j not in chosen:
                            chosen.append(j)
                        if len(chosen) >= positions_per_rotation:
                            break
                    if len(chosen) >= positions_per_rotation:
                        break
                for j in chosen:
                    overlap = float(overlaps[j]) if voxel_overlap_cells and state.placements else 0
                    candidates.append((float(scores[j]), parent_index, oi, shifts[j], bounds[j], overlap))
        # Cheap clean proposals come first. Otherwise volume ranking can spend
        # the entire time budget on thousands of physically colliding proxies.
        candidates.sort(key=lambda candidate: (candidate[5], candidate[0]))
        managers, representatives = {}, {}
        next_beam, seen_grids, parent_counts = [], set(), {}
        deferred = []
        # Limit how many descendants one parent contributes before considering
        # other parents. A second pass fills any otherwise unused beam slots.
        passes = [candidates, deferred]
        for pass_index, sequence in enumerate(passes):
            for score, parent_index, oi, shift, bounds, overlap in sequence:
                if len(next_beam) >= beam_width or perf_counter() - started >= time_limit:
                    break
                if pass_index == 0 and parent_counts.get(parent_index, 0) >= max(2, beam_width // 4):
                    deferred.append((score, parent_index, oi, shift, bounds, overlap))
                    continue
                parent = beam[parent_index]
                orientation = data[iid][oi]
                candidate = orientation["mesh"].copy()
                candidate.apply_translation(shift * pitch_mm)
                checks += 1
                if parent_index not in managers:
                    manager = trimesh.collision.CollisionManager()
                    for index, mesh in enumerate(parent.meshes):
                        manager.add_object(str(index), mesh)
                    managers[parent_index] = manager
                manager = managers[parent_index]
                if parent.meshes:
                    if manager.in_collision_single(candidate) or manager.min_distance_single(candidate) + 1e-8 < clearance:
                        continue
                    # All benchmark parts are connected. Handle compound sources
                    # explicitly as well so a hidden disconnected solid is checked.
                    components = trimesh.graph.connected_components(candidate.edges_unique, nodes=np.arange(len(candidate.vertices)))
                    points = candidate.vertices[[int(c[0]) for c in components]]
                    enclosed = False
                    for mesh in parent.meshes:
                        key = id(mesh)
                        if key not in representatives:
                            components = trimesh.graph.connected_components(mesh.edges_unique, nodes=np.arange(len(mesh.vertices)))
                            representatives[key] = mesh.vertices[[int(c[0]) for c in components]]
                        if mesh.contains(points).any() or candidate.contains(representatives[key]).any():
                            enclosed = True
                            break
                    if enclosed:
                        continue
                updated = parent.grid.copy()
                size = orientation["grid"].shape
                slices = tuple(slice(int(shift[k]), int(shift[k]) + size[k]) for k in range(3))
                updated[slices] = np.maximum(updated[slices], orientation["grid"])
                fingerprint = sha256(updated.tobytes()).digest()
                if fingerprint in seen_grids:
                    continue
                if lookahead and depth + 1 < len(units):
                    next_iid = expected[units[depth + 1]]
                    spectra, has_slot = {}, False
                    for next_index, following in enumerate(data[next_iid]):
                        if perf_counter() - started >= time_limit:
                            break
                        next_grid = following["grid"]
                        padded = tuple(next_fast_len(int(a + b - 1), real=True)
                                       for a, b in zip(updated.shape, next_grid.shape))
                        if padded not in spectra:
                            spectra[padded] = rfftn(updated, s=padded)
                        if next_index not in forward_kernels:
                            forward_kernels[next_index] = rfftn(next_grid[::-1, ::-1, ::-1], s=padded)
                        correlation = irfftn(spectra[padded] * forward_kernels[next_index], s=padded)
                        begin = np.maximum(0, np.ceil(-following["bounds"][0] / pitch_mm).astype(int))
                        end = np.minimum(np.array(updated.shape) - np.array(next_grid.shape),
                                         np.floor((usable - following["bounds"][1]) / pitch_mm).astype(int))
                        if np.any(end < begin):
                            continue
                        window = tuple(slice(int(b - 1 + low), int(b + high))
                                       for b, low, high in zip(next_grid.shape, begin, end))
                        if np.any(correlation[window] < voxel_overlap_cells + .5):
                            has_slot = True
                            break
                    if not has_slot:
                        forward_rejections += 1
                        continue
                seen_grids.add(fingerprint)
                transform = orientation["transform"].copy()
                transform[:3, 3] += shift * pitch_mm + margin
                pose = {"unit_id": uid, "item_id": iid, "transform": transform.tolist()}
                next_beam.append(_State(updated, parent.placements + [pose], parent.meshes + [candidate], bounds, score))
                parent_counts[parent_index] = parent_counts.get(parent_index, 0) + 1
        if not next_beam:
            reason = "time_limit" if perf_counter() - started >= time_limit else "beam_exhausted"
            break
        beam = next_beam
        best = min(beam, key=lambda state: state.score)
        record = {"placed": len(best.placements), "expected": len(expected), "beam_states": len(beam),
                  "mesh_candidates_checked": checks, "forward_rejections": forward_rejections,
                  "elapsed_seconds": perf_counter() - started}
        history.append(record)
        if progress:
            progress(record)
        if directory:
            (directory / "checkpoint.json").write_text(json.dumps({"units": "mm", "placements": best.placements,
                "complete": False, "history": history}, indent=2), encoding="utf8")
        if depth + 1 == len(units):
            for state in beam:
                layout = {"units": "mm", "placements": state.placements}
                validation = validate_mesh_layout(problem, layout)
                if validation["valid"]:
                    result = {**layout, "status": "validated_static_layout", "validation": validation,
                              "search": {"history": history, "pitch_mm": pitch_mm, "beam_width": beam_width,
                                         "voxel_overlap_cells": voxel_overlap_cells,
                                         "elapsed_seconds": perf_counter() - started, "optimality_proven": False}}
                    if directory:
                        (directory / "layout.json").write_text(json.dumps(result, indent=2), encoding="utf8")
                    return result
            reason = "complete_candidates_failed_validation"
    result = {"units": "mm", "placements": best.placements, "status": reason,
              "complete": False, "search": {"history": history, "pitch_mm": pitch_mm,
              "beam_width": beam_width, "voxel_overlap_cells": voxel_overlap_cells,
              "elapsed_seconds": perf_counter() - started,
              "optimality_proven": False}, "validation": validate_mesh_layout(problem, {"units": "mm", "placements": best.placements})}
    if directory:
        (directory / "layout.json").write_text(json.dumps(result, indent=2), encoding="utf8")
    return result
