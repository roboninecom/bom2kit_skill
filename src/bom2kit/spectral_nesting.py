"""Volumetric correlation proposals; original meshes certify every retained pair.

This is a CPU implementation of occupancy correlation, not the psacking binary.
Voxel cells only rank candidates. Original source clearance, explicit support
materials, and subsequent complete-kit access replay remain authoritative.
"""
from functools import lru_cache
from itertools import product
import math
from time import perf_counter


@lru_cache(maxsize=192)
def _variant(path, digest, frame_values, turn, pitch, voxel_cache=None):
    import numpy as np
    import trimesh
    from .practical_geometry import load_mesh
    from .regular_stacks import horizontal_cap
    if turn:
        from shapely.affinity import affine_transform
        base = _variant(path, digest, frame_values, 0, pitch, voxel_cache)
        yaw = trimesh.transformations.rotation_matrix(turn * math.pi / 2, [0, 0, 1])
        mesh = base['mesh'].copy(); mesh.apply_transform(yaw)
        yaw[:3, 3] -= mesh.bounds[0]; mesh.apply_translation(-mesh.bounds[0])
        corners = np.array(list(product(*[(base['grid_origin'][k], base['grid_origin'][k] + (base['grid'].shape[k]-1)*pitch) for k in range(3)])))
        planar = [yaw[0, 0], yaw[0, 1], yaw[1, 0], yaw[1, 1], yaw[0, 3], yaw[1, 3]]
        manager = trimesh.collision.CollisionManager(); manager.add_object('source', mesh)
        return {'mesh': mesh, 'frame': yaw @ base['frame'], 'component_indices': base['component_indices'],
                'grid': np.rot90(base['grid'], turn, axes=(0, 1)),
                'grid_origin': trimesh.transform_points(corners, yaw).min(axis=0),
                'faces': [(z, affine_transform(face, planar)) for z, face in base['faces']],
                'down_faces': [(z, affine_transform(face, planar)) for z, face in base['down_faces']],
                'bottom': affine_transform(base['bottom'], planar), 'manager': manager}
    mesh = load_mesh({'mesh': {'path': path, 'sha256': digest}})
    frame = trimesh.transformations.rotation_matrix(turn * math.pi / 2, [0, 0, 1]) @ np.asarray(frame_values).reshape(4, 4)
    mesh.apply_transform(frame)
    frame[:3, 3] -= mesh.bounds[0]
    mesh.apply_translation(-mesh.bounds[0])
    grid_file = None
    if voxel_cache:
        from hashlib import sha256
        import json
        from pathlib import Path
        key = sha256(json.dumps([digest, [float(v) for v in frame_values], pitch, 'source-voxel-v1']).encode()).hexdigest()
        grid_file = Path(voxel_cache)/(key+'.npz')
    if grid_file and grid_file.exists():
        with np.load(grid_file, allow_pickle=False) as saved:
            grid_matrix = saved['matrix']; grid_origin = saved['origin']
        if grid_matrix.ndim != 3 or grid_matrix.dtype != bool or grid_origin.shape != (3,) or not np.isfinite(grid_origin).all():
            raise ValueError('Invalid source voxel cache')
    else:
        grid = mesh.voxelized(pitch).fill(); grid_matrix = grid.matrix; grid_origin = grid.transform[:3, 3]
        if grid_file:
            import tempfile
            grid_file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=grid_file.parent, suffix='.npz', delete=False) as temporary:
                temporary_path = Path(temporary.name)
            np.savez_compressed(temporary_path, matrix=grid_matrix, origin=grid_origin)
            temporary_path.replace(grid_file)
    horizontal = (np.ptp(mesh.triangles[:, :, 2], axis=1) < .02) & (mesh.face_normals[:, 2] > .99)
    plane_values = np.round(mesh.triangles[horizontal, :, 2].mean(axis=1), 3)
    heights, inverse = np.unique(plane_values, return_inverse=True)
    plane_areas = np.bincount(inverse, weights=mesh.area_faces[horizontal])
    heights = heights[np.argsort(-plane_areas)[:12]]
    faces = [(float(z), horizontal_cap(mesh, z, normal_sign=1)) for z in heights]
    faces = sorted((f for f in faces if f[1].area > 1), key=lambda f: -f[1].area)[:12]
    down_mask = (np.ptp(mesh.triangles[:, :, 2], axis=1) < .02) & (mesh.face_normals[:, 2] < -.99)
    down_values = np.round(mesh.triangles[down_mask, :, 2].mean(axis=1), 3)
    down_heights, inverse = np.unique(down_values, return_inverse=True)
    down_areas = np.bincount(inverse, weights=mesh.area_faces[down_mask])
    down_heights = down_heights[np.argsort(-down_areas)[:4]]
    down_faces = [(float(z), horizontal_cap(mesh, z, normal_sign=-1)) for z in down_heights if z > .02]
    manager = trimesh.collision.CollisionManager()
    manager.add_object('source', mesh)
    components = trimesh.graph.connected_components(mesh.edges_unique, nodes=np.arange(len(mesh.vertices)))
    return {'mesh': mesh, 'frame': frame, 'grid': grid_matrix,
            'component_indices': [int(c[0]) for c in components],
            'grid_origin': grid_origin, 'faces': faces,
            'down_faces': [(0., horizontal_cap(mesh, 0., normal_sign=-1)), *down_faces],
            'bottom': horizontal_cap(mesh, 0., normal_sign=-1), 'manager': manager}


def variants(item, options, pitch=2., voxel_cache=None):
    """Retain independent stable faces for each part, including opposite faces."""
    import numpy as np
    return [_variant(item['mesh']['path'], item['mesh']['sha256'],
                     tuple(np.asarray(option['transform']).ravel()), turn, pitch, str(voxel_cache) if voxel_cache else None)
            for option in options for turn in range(4)]


def correlation_offsets(a, b, levels, clearance, *, pitch=2., per_level=32):
    """Search XYZ occupancy, then evaluate exact support heights on original CAD."""
    import numpy as np
    from scipy.signal import fftconvolve
    from scipy.ndimage import binary_dilation
    # Surface voxels already extend by a cell through quantization. Leave one
    # cell for that uncertainty: this is proposal generation, not clearance
    # certification. Otherwise exact protected contact planes disappear.
    dilation = max(0, int(math.floor(clearance / pitch)) - 1)
    ga = np.pad(a['grid'], dilation)
    if dilation:
        ga = binary_dilation(ga, iterations=dilation)
    oa = a['grid_origin'] - dilation * pitch
    gb = b['grid']; ob = b['grid_origin']
    field = fftconvolve(ga.astype('float32'), gb[::-1, ::-1, ::-1].astype('float32'), mode='full')
    da, db = a['mesh'].extents, b['mesh'].extents
    candidates = []
    for z, face in levels:
        zi = int(round((z - oa[2] + ob[2]) / pitch)) + gb.shape[2] - 1
        if not 0 <= zi < field.shape[2]:
            if z < da[2] + clearance - 1e-6:
                continue
            cells = np.indices(field.shape[:2]).reshape(2, -1).T
        else:
            cells = np.argwhere(field[:, :, zi] < .5)
        xy = (cells - np.asarray(gb.shape[:2]) + 1) * pitch + oa[:2] - ob[:2]
        low = np.minimum(0., xy); high = np.maximum(da[:2], xy + db[:2])
        dims = high - low + clearance
        costs = np.prod(dims, axis=1) * (max(da[2], z + db[2]) + clearance)
        # Equal envelopes can have very different hand access. Prefer centered
        # cavity placements and retain offset alternatives for final replay.
        centers = np.linalg.norm(xy + db[:2]/2 - da[:2]/2, axis=1)
        order = np.lexsort((centers, costs))[:per_level]
        candidates.extend((float(costs[i]), [float(xy[i, 0]), float(xy[i, 1]), z], face) for i in order)
    return sorted(candidates, key=lambda c: c[0])


def discover_pairs(first, second, first_options, second_options, *, padding=1., gap=.2,
                   pitch=2., seconds=30., maximum=8, minimum_sheet_side=10., voxel_cache=None):
    """Find source-relative pair recipes; no fixed carton/reference dimensions."""
    import numpy as np
    import trimesh
    from shapely.affinity import translate
    from shapely.geometry import Point
    from .packing_states import declared_state
    if (not first_options or not second_options or maximum < 1
            or not all(math.isfinite(v) for v in (padding, gap, pitch, seconds, minimum_sheet_side))
            or min(padding, pitch, seconds) <= 0 or min(gap, minimum_sheet_side) < 0):
        raise ValueError('Finite positive search/protection parameters and source poses required')
    started = perf_counter(); diagnostics = {'orientations': 0, 'exact_checks': 0,
        'clearance_rejections': 0, 'support_rejections': 0, 'sheet_rejections': 0}
    required = 2 * padding + gap
    cache_before = _variant.cache_info()
    av = variants(first, first_options, pitch, voxel_cache)[::4]; bv = variants(second, second_options, pitch, voxel_cache)
    cache_after = _variant.cache_info()
    diagnostics.update(memory_cache_hits=cache_after.hits-cache_before.hits,
                       memory_cache_misses=cache_after.misses-cache_before.misses,
                       voxel_disk_cache_enabled=voxel_cache is not None)
    separate_best = min(
        min((a['mesh'].extents[0]+b['mesh'].extents[0]+4*padding+gap)
            * max(a['mesh'].extents[1]+2*padding, b['mesh'].extents[1]+2*padding),
            max(a['mesh'].extents[0]+2*padding, b['mesh'].extents[0]+2*padding)
            * (a['mesh'].extents[1]+b['mesh'].extents[1]+4*padding+gap))
        * max(a['mesh'].extents[2]+2*padding, b['mesh'].extents[2]+2*padding)
        for a in av for b in bv)
    prepared = perf_counter(); deadline = prepared + seconds
    # Simultaneous yaw is redundant. Cycle stable faces before spending the
    # budget on nearby translations of the first orientation.
    choices = [(a, bv[((index + step) % len(second_options))*4 + turn])
               for step in range(len(second_options)) for turn in (2, 0, 1, 3)
               for index, a in enumerate(av)]
    found = []; signatures = set(); queue = []
    proposal_deadline = prepared + .55 * seconds
    for a, b in choices:
        if queue and perf_counter() > proposal_deadline:
            break
        diagnostics['orientations'] += 1
        levels = [(0., None)]
        if declared_state(first)['kind'] in ('source_part', 'factory_carton'):
            levels.extend((z + required - upper_z, {'lower': face, 'upper': upper_face,
                           'lower_z': z, 'upper_z': upper_z})
                          for z, face in a['faces'] for upper_z, upper_face in b['down_faces']
                          if z + required - upper_z >= -1e-7)
        candidates = correlation_offsets(a, b, levels, required, pitch=pitch, per_level=12)
        queue.extend((cost, a, b, offset, face) for cost, offset, face in candidates)
    diagnostics['correlation_candidates'] = len(queue)
    for _, a, b, offset, face in sorted(queue, key=lambda row: row[0]):
        if perf_counter() > deadline:
            break
        shift = np.asarray(offset); low = np.minimum(0., shift)
        size = np.maximum(a['mesh'].extents, shift + b['mesh'].extents) - low + 2 * padding
        pa = a['mesh'].extents + 2 * padding; pb = b['mesh'].extents + 2 * padding
        separate = min((pa[0]+pb[0]+gap)*max(pa[1],pb[1]),
                       max(pa[0],pb[0])*(pa[1]+pb[1]+gap))*max(pa[2],pb[2])
        if math.prod(size) > separate * 1.02:
            continue
        overlap = np.minimum(a['mesh'].extents, shift + b['mesh'].extents) - np.maximum(0., shift)
        if face is None and (math.prod(size) > .98 * separate or min(overlap[:2]) < .5):
            continue
        sheet = None
        if face is not None:
            contact = face['lower'].intersection(translate(face['upper'], xoff=shift[0], yoff=shift[1]))
            center = Point(b['mesh'].center_mass[:2] + shift[:2])
            if contact.area <= 1e-6 or not contact.convex_hull.covers(center) or contact.convex_hull.boundary.distance(center) < .05:
                diagnostics['support_rejections'] += 1; continue
            x0, y0, x1, y1 = contact.bounds
            if min(x1-x0, y1-y0) < minimum_sheet_side - 1e-7:
                diagnostics['sheet_rejections'] += 1; continue
            sheet = {'origin_mm': [x0, y0, face['lower_z']],
                     'dimensions_mm': [x1-x0, y1-y0, required],
                     'extra_clearance_mm': gap, 'support_surface': 'paired_horizontal_faces' if face['upper_z'] > .02 else 'actual_horizontal_face'}
            panel = trimesh.creation.box(np.asarray(sheet['dimensions_mm']) - .002)
            panel.apply_translation(np.asarray(sheet['origin_mm']) + np.asarray(sheet['dimensions_mm'])/2)
            inverse_shift = np.eye(4); inverse_shift[:3, 3] = -shift
            if a['manager'].in_collision_single(panel) or b['manager'].in_collision_single(panel, inverse_shift):
                diagnostics['sheet_rejections'] += 1; continue
        transform = np.eye(4); transform[:3, 3] = shift
        diagnostics['exact_checks'] += 1
        # Reuse the moving source's acceleration tree across translations.
        # *_single rebuilt its BVH for every candidate and dominated runtime.
        # Keep it separate from the fixed manager even for identical variants.
        if 'moving_manager' not in b:
            b['moving_manager'] = trimesh.collision.CollisionManager()
            b['moving_manager'].add_object('source', b['mesh'])
        b['moving_manager'].set_transform('source', transform)
        if (a['manager'].in_collision_other(b['moving_manager'])
                or a['manager'].min_distance_other(b['moving_manager']) < required - 1e-6):
            diagnostics['clearance_rejections'] += 1; continue
        if (a['mesh'].contains(b['mesh'].vertices[b['component_indices']] + shift).any()
                or b['mesh'].contains(a['mesh'].vertices[a['component_indices']] - shift).any()):
            diagnostics['clearance_rejections'] += 1; continue
        frames = [a['frame'].copy(), b['frame'].copy()]
        frames[0][:3, 3] += padding - low
        frames[1][:3, 3] += shift + padding - low
        if sheet:
            sheet['origin_mm'] = (np.asarray(sheet['origin_mm']) + padding - low).tolist()
        signature = (tuple(np.round(size, 3)), tuple(np.round(shift, 2)),
                     tuple(np.round(a['frame'][:3, :3].ravel(), 3)),
                     tuple(np.round(b['frame'][:3, :3].ravel(), 3)))
        if signature in signatures:
            continue
        signatures.add(signature)
        found.append({'dimensions_mm': size.tolist(), 'transforms': [f.tolist() for f in frames],
                      'sheet': sheet, 'bounds_overlap_mm': np.maximum(overlap, 0.).tolist(),
                      'envelope_saving_fraction': 1-math.prod(size)/separate,
                      'best_separate_envelope_mm3': float(separate_best),
                      'saving_vs_best_separate_fraction': float(1-math.prod(size)/separate_best),
                      'kind': 'supported_nesting' if sheet and shift[2] < a['mesh'].extents[2] else
                              'protected_stack' if sheet else 'complementary_floor_pair',
                      'source_hashes': [first['mesh']['sha256'], second['mesh']['sha256']],
                      'clearance_mm': required, 'pitch_mm': pitch,
                      'original_clearance_checked': True, 'assembly_replay_required': True})
    # Keep distinct footprint/height choices, rather than only the smallest pair volume.
    ranked = sorted(found, key=lambda r: math.prod(r['dimensions_mm']))
    selected = []
    for key in (lambda r: math.prod(r['dimensions_mm']), lambda r: r['dimensions_mm'][2],
                lambda r: math.prod(r['dimensions_mm'][:2])):
        if ranked:
            candidate = min(ranked, key=key)
            if candidate not in selected: selected.append(candidate)
    for kind in ('supported_nesting', 'protected_stack', 'complementary_floor_pair'):
        alternatives = [r for r in ranked if r['kind'] == kind]
        if alternatives and alternatives[0] not in selected:
            selected.append(alternatives[0])
    selected.extend(r for r in ranked if r not in selected)
    return {'recipes': selected[:maximum], 'diagnostics': {**diagnostics, 'preparation_seconds': prepared-started,
        'search_seconds': perf_counter()-prepared, 'seconds': perf_counter()-started, 'accepted_recipes': len(found),
        'timed_out': perf_counter() > deadline, 'backend': 'scipy_full_3d_correlation'}}
