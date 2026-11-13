"""Search new 3D offsets against a multi-part obstacle, retaining source units.

The temporary concatenated mesh is only an occupancy/collision obstacle. It is
never a BOM item or a proposed rigid handling assembly.
"""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from itertools import product
import json
import math
from pathlib import Path
from time import perf_counter


def extend_with_correlation(recipes, library, policy, *, output, pose_cache=None,
                            seconds=120., pair_seconds=8., maximum_members=6, progress=None,
                            search_order='depth', partner_limit=2, pitch=3.):
    import numpy as np
    import trimesh
    from shapely.geometry import Point
    from .practical_geometry import load_mesh, stable_pose_options
    from .regular_stacks import horizontal_cap
    from .spectral_nesting import discover_pairs
    from .packing_states import declared_state
    from .report import fingerprint
    if (not math.isfinite(seconds) or seconds <= 0 or not math.isfinite(pair_seconds) or pair_seconds <= 0
            or not 2 <= maximum_members <= 12 or search_order not in ('depth', 'breadth')
            or not isinstance(partner_limit, int) or partner_limit < 1 or not math.isfinite(pitch) or pitch <= 0):
        raise ValueError('Positive finite search budgets and two through twelve members required')
    started = perf_counter(); directory = Path(output); directory.mkdir(parents=True, exist_ok=True)
    by_id = {i['id']: i for i in library['items']}; meshes = {}; options = {}; found = []; trials = []
    padding = policy['item_padding_mm']; gap = policy['carton']['gap_mm']
    seeds = sorted(recipes, key=lambda r: -r.get('saving_vs_best_separate_fraction', 0))
    unique = {}; seen = set()
    for seed in seeds:
        counts = Counter(seed['item_ids'])
        if any(iid not in by_id or n > by_id[iid]['quantity'] for iid,n in counts.items()):
            continue
        if len(set(policy['families'][iid] for iid in counts)) != 1:
            raise ValueError('A cluster seed must retain one compatible family')
        if (len(seed['source_hashes']) != len(seed['item_ids'])
                or any(by_id[iid]['mesh']['sha256'] != digest
                       for iid,digest in zip(seed['item_ids'],seed['source_hashes']))):
            raise ValueError('Cluster seed source hash differs from the current library')
        if len(seed['item_ids']) < maximum_members:
            unique.setdefault(tuple(sorted(seed['item_ids'])), seed)
    frontier = list(unique.values())[:12]
    while frontier and perf_counter()-started < seconds:
        if search_order == 'depth':
            frontier.sort(key=lambda r: (-len(r['item_ids']),
                math.prod(r['dimensions_mm'])/max(1., r.get('selection_reference_mm3', r.get('best_separate_envelope_mm3', 1.)))))
        seed = frontier.pop(0); count = len(seed['item_ids'])
        if count >= maximum_members: continue
        placed = []
        for iid, frame in zip(seed['item_ids'], seed['transforms'], strict=True):
            if iid not in meshes: meshes[iid] = load_mesh(by_id[iid])
            part = meshes[iid].copy(); part.apply_transform(frame); placed.append(part)
        obstacle = trimesh.util.concatenate(placed)
        raw = json.dumps({'units': 'mm', 'vertices_mm': obstacle.vertices.tolist(),
                          'triangles': obstacle.faces.tolist()}).encode()
        digest = sha256(raw).hexdigest(); path = directory/(digest+'.json')
        if not path.exists(): path.write_bytes(raw)
        host = {'id': 'search-obstacle-only', 'quantity': 1, 'mesh': {'path': str(path.resolve()), 'sha256': digest}}
        host_options = [{'transform': np.eye(4).tolist(), 'dimensions_mm': obstacle.extents.tolist()}]
        family = policy['families'][seed['item_ids'][0]]; counts = Counter(seed['item_ids'])
        candidates = [i for i in library['items'] if policy['families'][i['id']] == family
                      and counts[i['id']] < i['quantity']
                      and declared_state(i)['kind'] in ('source_part', 'factory_carton')]
        # New partners, not only the mates already used by pair templates.
        ranked = []
        for item in candidates:
            if item['id'] not in meshes: meshes[item['id']] = load_mesh(item)
            shape = meshes[item['id']]
            ranked.append((min(float(shape.volume), float(math.prod(obstacle.extents)-obstacle.volume)), item))
        for _, item in sorted(ranked, key=lambda row: -row[0])[:partner_limit]:
            if perf_counter()-started >= seconds: break
            iid = item['id']
            if iid not in options:
                options[iid] = stable_pose_options(item, maximum=8, cache=pose_cache,
                                                   preserve_faces=True, include_projection=False)
            result = discover_pairs(host, item, host_options, options[iid], padding=padding, gap=gap,
                                    seconds=min(pair_seconds, max(.1, seconds-(perf_counter()-started))),
                                    pitch=pitch, voxel_cache=directory/'voxels')
            accepted = 0
            for pair in result['recipes']:
                alignment = np.asarray(pair['transforms'][0])
                frames = [(alignment @ np.asarray(f)).tolist() for f in seed['transforms']]+[pair['transforms'][1]]
                sources = []
                for original, frame in zip(seed['item_ids']+[iid], frames):
                    source = meshes[original].copy(); source.apply_transform(frame); sources.append(source)
                sheets = deepcopy(seed['sheets'])
                for sheet in sheets:
                    corners = np.array(list(product(*[(o, o+d) for o, d in zip(sheet['origin_mm'], sheet['dimensions_mm'])])))
                    corners = trimesh.transform_points(corners, alignment)
                    sheet['origin_mm'] = corners.min(axis=0).tolist(); sheet['dimensions_mm'] = np.ptp(corners, axis=0).tolist()
                if pair['sheet']:
                    child = sources[-1]; level = pair['sheet']['origin_mm'][2]
                    upper_level = level+pair['sheet']['dimensions_mm'][2] if pair['sheet']['support_surface']=='paired_horizontal_faces' else child.bounds[0, 2]
                    bottom = horizontal_cap(child, upper_level, normal_sign=-1)
                    center = Point(child.center_mass[:2]); supports = []
                    for index, lower in enumerate(sources[:-1]):
                        if declared_state(by_id[seed['item_ids'][index]])['kind'] not in ('source_part', 'factory_carton'): continue
                        contact = horizontal_cap(lower, level, normal_sign=1).intersection(bottom)
                        if contact.area <= 1e-6 or not contact.convex_hull.covers(center): continue
                        x0, y0, x1, y1 = contact.bounds
                        if min(x1-x0, y1-y0) < 10.: continue
                        supports.append((contact.area, {'lower_index': index, 'upper_index': count,
                            'origin_mm': [x0, y0, level], 'dimensions_mm': [x1-x0, y1-y0, 2*padding+gap],
                            'extra_clearance_mm': gap, 'support_surface': pair['sheet']['support_surface']}))
                    if not supports: continue
                    sheets.append(max(supports, key=lambda s: s[0])[1])
                signature = fingerprint([seed['item_ids']+[iid], frames])
                if signature in seen: continue
                seen.add(signature)
                recipe = {'id': signature[:20], 'item_ids': seed['item_ids']+[iid], 'transforms': frames,
                          'source_hashes': seed['source_hashes']+[item['mesh']['sha256']],
                          'dimensions_mm': pair['dimensions_mm'], 'sheets': sheets, 'kind': 'correlated_cluster',
                          'clearance_mm': 2*padding+gap, 'original_clearance_checked': True,
                          'assembly_replay_required': True, 'parent_recipe': seed['id'],
                          'search_obstacle_sha256': digest,
                          'selection_reference_mm3': sum(math.prod(meshes[j].extents+2*padding) for j in seed['item_ids']+[iid])}
                found.append(recipe); accepted += 1
                if len(recipe['item_ids']) < maximum_members: frontier.append(recipe)
            record = {'seed': seed['id'], 'child': iid, 'accepted_proposals': accepted,
                      'diagnostics': result['diagnostics'], 'seconds': perf_counter()-started}
            trials.append(record)
            if progress: progress({'stage': 'cluster_correlation', **record})
    return found, {'seconds': perf_counter()-started, 'trials': trials,
                   'search_order': search_order, 'partner_limit': partner_limit, 'pitch_mm': pitch,
                   'maximum_members': maximum_members,
                   'accepted_proposals': len(found), 'complete_replay_required': True}
