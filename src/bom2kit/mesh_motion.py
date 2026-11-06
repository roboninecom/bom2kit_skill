"""Conservative straight-up removal checks for an already validated mesh layout.

Each translation step is shorter than half the current surface distance to every
obstacle. The distance is a conservative bound on collision-free travel. Failure
or exhaustion is not a proof that no other insertion path exists.
"""

import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from .mesh_validation import validate_mesh_layout
from .report import fingerprint
from .models import number


def check_vertical_sequence(problem, layout, groups=None, time_limit=30):
    import numpy as np
    import trimesh

    time_limit = number(time_limit, 'time_limit', True)
    groups = {} if groups is None else groups
    if not isinstance(groups, dict):
        raise ValueError('groups must map group names to unit ID lists')
    binding = {'input_sha256': fingerprint(problem), 'layout_sha256': fingerprint(layout),
               'groups_sha256': fingerprint(groups), 'time_limit_seconds': time_limit}
    start = perf_counter()
    static = validate_mesh_layout(problem, layout)
    if not static['valid']:
        return {**binding, 'valid': False, 'scope': 'vertical_group_insertion', 'reason': 'Static layout is invalid',
                'static_validation': static}
    binding['source_sha256'] = {key: value['sha256'] for key, value in static['sources'].items()}
    items = {item['id']: item for item in problem['items']}
    meshes = {}
    for placement in layout['placements']:
        ref = items[placement['item_id']]['mesh']
        path = Path(ref['path'])
        source_bytes = path.read_bytes()
        if sha256(source_bytes).hexdigest() != ref['sha256']:
            raise ValueError('Mesh source changed after static validation')
        if path.suffix.lower() == '.3mf':
            from .mesh_geometry import load_instance_mesh
            data = load_instance_mesh(path, ref['instance_id'], ref.get('frame', 'object'))
            if sha256(path.read_bytes()).hexdigest() != ref['sha256']:
                raise ValueError('3MF source changed while loading motion geometry')
        else:
            data = json.loads(source_bytes.decode('utf-8-sig'))
        mesh = trimesh.Trimesh(vertices=data['vertices_mm'], faces=data['triangles'], process=False)
        mesh.apply_transform(np.asarray(placement['transform']))
        meshes[placement['unit_id']] = mesh
    selected, units = set(), {}
    for name, members in groups.items():
        if not isinstance(name, str) or not name or not isinstance(members, list) or not members:
            raise ValueError('Invalid group declaration')
        if name in meshes:
            raise ValueError('Group name conflicts with unit ID')
        if any(not isinstance(uid, str) or uid not in meshes or uid in selected for uid in members):
            raise ValueError('Unknown or multiply grouped unit')
        if len(set(members)) != len(members):
            raise ValueError('Repeated unit in group')
        selected.update(members)
        units[name] = (members, trimesh.util.concatenate([meshes[uid] for uid in members]))
    for uid, mesh in meshes.items():
        if uid not in selected:
            if uid in units:
                raise ValueError('Group name conflicts with unit ID')
            units[uid] = ([uid], mesh)
    remaining = dict(units)
    removals, distance_queries = [], 0
    while remaining and perf_counter() - start < time_limit:
        progress = False
        # Try the highest groups first; use unit names to make ties reproducible.
        order = sorted(remaining, key=lambda name: (-remaining[name][1].bounds[1, 2], name))
        for name in order:
            members, moving = remaining[name]
            others = [mesh for key, (_, mesh) in remaining.items()
                      if key != name and mesh.bounds[1, 2] >= moving.bounds[0, 2]
                      and all(mesh.bounds[1, axis] >= moving.bounds[0, axis]
                              and moving.bounds[1, axis] >= mesh.bounds[0, axis]
                              for axis in (0, 1))]
            if not others:
                removals.append({'group_id': name, 'unit_ids': members, 'direction': '+Z'})
                del remaining[name]
                progress = True
                break
            manager = trimesh.collision.CollisionManager()
            for i, mesh in enumerate(others):
                manager.add_object(str(i), mesh)
            # Once the moving group's minimum Z exceeds every obstacle maximum,
            # continued upward translation cannot hit an obstacle or side wall.
            travel = max(mesh.bounds[1, 2] for mesh in others) - moving.bounds[0, 2] + 1.0
            # Keep the moving mesh's FCL acceleration structure throughout the
            # continuous path check. min_distance_single rebuilt it every step.
            moving_manager = trimesh.collision.CollisionManager()
            moving_manager.add_object('moving', moving)
            moved, passed = 0.0, False
            for _ in range(500):
                if perf_counter() - start >= time_limit:
                    break
                if moved >= travel:
                    passed = True
                    break
                distance = manager.min_distance_other(moving_manager)
                distance_queries += 1
                if not np.isfinite(distance) or distance <= 1e-6:
                    break
                step = min(distance * 0.49, travel - moved)
                moved += step
                transform = np.eye(4)
                transform[2, 3] = moved
                moving_manager.set_transform('moving', transform)
            if passed:
                removals.append({'group_id': name, 'unit_ids': members, 'direction': '+Z'})
                del remaining[name]
                progress = True
                break
        if not progress:
            break
    return {**binding, 'valid': not remaining, 'scope': 'vertical_group_insertion',
            'removal_sequence': removals,
            'packing_sequence': [{**step, 'direction': '-Z'} for step in reversed(removals)] if not remaining else [],
            'unresolved_groups': sorted(remaining), 'distance_queries': distance_queries,
            'elapsed_seconds': perf_counter() - start,
            'production_validated': False,
            'limitations': ['Grouped parts are handled together; internal group assembly is not checked.',
                            'Open rectangular top assumed, with lid and booklet absent during insertion.',
                            'Continuous path checks are collision checks; the requested static pair clearance is not certified along the whole path.',
                            'No support, hand/tool access, bag thickness or physical trial is checked.',
                            'Floating-point surface distances; failure is not an impossibility proof.']}
