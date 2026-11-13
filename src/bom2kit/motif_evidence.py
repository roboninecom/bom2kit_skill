"""Identify combinations actually present in a frozen individual-part layout."""
import math


def used_motifs(result, meshes):
    import numpy as np
    padding = result['logistics']['policy']['item_padding_mm']
    gap = result['logistics']['policy']['carton']['gap_mm']
    sheets = result.get('practical', {}).get('protective_separators', [])
    evidence = []
    for module in result['logistics']['modules']:
        groups = []
        for operation in module.get('source_motifs', []):
            members = set(operation['unit_ids'])
            if len(members) < 2 or not members <= set(module['unit_ids']):
                raise ValueError('Recorded motif is not contained in its source carton')
            groups.append((members, operation.get('recipe_id')))
        linked = []
        for sheet in sheets:
            if sheet['carton_id'] != module['id']:
                continue
            component = {sheet['lower_unit_id'], sheet['upper_unit_id']}
            touched = [g for g in linked if g & component]
            for group in touched:
                component |= group; linked.remove(group)
            linked.append(component)
        for component in linked:
            if not any(component <= group for group, _ in groups):
                groups.append((component, None))
        seen = set()
        for members, recipe in groups:
            key = tuple(sorted(members))
            if key in seen:
                continue
            seen.add(key)
            if not members <= set(module['unit_ids']):
                raise ValueError('Supported combination crosses carton membership')
            bounds = np.asarray([meshes[uid].bounds for uid in key])
            dimensions = bounds[:, 1].max(0)-bounds[:, 0].min(0)+2*padding
            single = bounds[:, 1]-bounds[:, 0]+2*padding
            # Transparent geometric control, not a feasible or optimal separate
            # carton: retain source orientations and form an X or Y row.
            separate = min((sum(single[:, axis])+gap*(len(key)-1))
                           * max(single[:, 1-axis])*max(single[:, 2]) for axis in (0, 1))
            relevant = [s for s in sheets if {s['lower_unit_id'], s['upper_unit_id']} <= members]
            evidence.append({'carton_id': module['id'], 'unit_ids': list(key), 'recipe_id': recipe,
                             'dimensions_mm': dimensions.tolist(), 'sheets': relevant,
                             'envelope_volume_mm3': math.prod(dimensions),
                             'same_pose_separate_row_mm3': float(separate),
                             'geometric_row_saving_fraction': 1-math.prod(dimensions)/separate,
                             'control_scope': 'Same-orientation bounding-envelope row; not optimized or assembly-replayed',
                             'source': 'Frozen result poses and support sheets; no catalog-only examples'})
    return evidence
