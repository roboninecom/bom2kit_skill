"""Extend independently movable source pairs into small source-part clusters."""
from collections import Counter
from copy import deepcopy
from itertools import product
import math
from time import perf_counter


def extend_catalog(recipes, items, padding, gap, *, seconds=30., maximum_members=6):
    import numpy as np
    import trimesh
    from .practical_geometry import load_mesh
    from .report import fingerprint
    if not 2 <= maximum_members <= 6:
        raise ValueError('Source clusters are limited to two through six members')
    started = perf_counter(); meshes = {}; components = {}; tested = 0; rejected = 0
    pairs = [r for r in recipes if len(r['item_ids']) == 2]
    by_id = {i['id']: i for i in items}
    for iid in {iid for r in pairs for iid in r['item_ids']}:
        mesh = load_mesh(by_id[iid]); meshes[iid] = mesh
        components[iid] = [int(c[0]) for c in trimesh.graph.connected_components(mesh.edges_unique, nodes=np.arange(len(mesh.vertices)))]
    frontier = sorted(pairs, key=lambda r: math.prod(r['dimensions_mm']))[:32]
    found = []; signatures = set()
    for count in range(3, maximum_members+1):
        next_frontier = []
        for seed in frontier:
            for anchor, aid in enumerate(seed['item_ids']):
                anchor_frame = np.asarray(seed['transforms'][anchor])
                for pair in pairs:
                    if perf_counter()-started > seconds: break
                    if pair['item_ids'][0] != aid: continue
                    child_id = pair['item_ids'][1]
                    counts = Counter(seed['item_ids']); counts[child_id] += 1
                    if counts[child_id] > by_id[child_id]['quantity']: continue
                    lower = np.asarray(pair['transforms'][0])
                    alignment = anchor_frame @ np.linalg.inv(lower)
                    rotation = alignment[:3, :3]
                    # A horizontal quarter-turn preserves stable support faces
                    # and the rectangular cut-sheet representation.
                    if (not np.allclose(rotation[:, 2], [0, 0, 1], atol=1e-7)
                            or not np.allclose(np.abs(rotation), np.round(np.abs(rotation)), atol=1e-7)):
                        continue
                    child_frame = alignment @ np.asarray(pair['transforms'][1])
                    signature = fingerprint([seed['item_ids']+[child_id], seed['transforms']+[child_frame.tolist()]])
                    if signature in signatures: continue
                    signatures.add(signature); tested += 1
                    child = meshes[child_id].copy(); child.apply_transform(child_frame)
                    manager = trimesh.collision.CollisionManager(); originals = []
                    for k, (iid, frame) in enumerate(zip(seed['item_ids'], seed['transforms'])):
                        source = meshes[iid].copy(); source.apply_transform(frame)
                        manager.add_object(str(k), source); originals.append((iid, source))
                    if manager.in_collision_single(child) or manager.min_distance_single(child) < 2*padding+gap-1e-6:
                        rejected += 1; continue
                    if any(source.contains(child.vertices[components[child_id]]).any()
                           or child.contains(source.vertices[components[iid]]).any() for iid, source in originals):
                        rejected += 1; continue
                    low = np.vstack([source.bounds[0] for _, source in originals]+[child.bounds[0]]).min(axis=0)-padding
                    high = np.vstack([source.bounds[1] for _, source in originals]+[child.bounds[1]]).max(axis=0)+padding
                    frames = [np.asarray(t).copy() for t in seed['transforms']]+[child_frame]
                    for frame in frames: frame[:3, 3] -= low
                    sheets = deepcopy(seed['sheets'])
                    for s in sheets: s['origin_mm'] = (np.asarray(s['origin_mm'])-low).tolist()
                    for s in pair['sheets']:
                        corners = np.array(list(product(*[(o, o+d) for o, d in zip(s['origin_mm'], s['dimensions_mm'])])))
                        corners = trimesh.transform_points(corners, alignment)-low
                        sheets.append({**deepcopy(s), 'lower_index': anchor, 'upper_index': count-1,
                                       'origin_mm': corners.min(axis=0).tolist(),
                                       'dimensions_mm': np.ptp(corners, axis=0).tolist()})
                    recipe = {'id': signature[:20], 'item_ids': seed['item_ids']+[child_id],
                              'transforms': [t.tolist() for t in frames], 'dimensions_mm': (high-low).tolist(),
                              'source_hashes': seed['source_hashes']+[by_id[child_id]['mesh']['sha256']],
                              'sheets': sheets, 'kind': 'source_cluster', 'clearance_mm': 2*padding+gap,
                              'original_clearance_checked': True, 'assembly_replay_required': True,
                              'parents': [seed['id'], pair['id']]}
                    # Lower-bound material sum guides beam diversity; it is not
                    # a measured side-by-side baseline for a larger cluster.
                    recipe['selection_reference_mm3'] = sum(math.prod(meshes[iid].extents+2*padding) for iid in recipe['item_ids'])
                    next_frontier.append(recipe)
                if perf_counter()-started > seconds: break
            if perf_counter()-started > seconds: break
        next_frontier.sort(key=lambda r: math.prod(r['dimensions_mm'])/len(r['item_ids']))
        frontier = next_frontier[:24]; found.extend(frontier)
        if not frontier or perf_counter()-started > seconds: break
    return found, {'seconds': perf_counter()-started, 'tested': tested, 'collision_rejections': rejected,
                   'accepted_proposals': len(found), 'maximum_members': max([2]+[len(r['item_ids']) for r in found]),
                   'complete_replay_required': True}
