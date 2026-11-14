"""Keep promising source combinations together in carton-content proposals.

Virtual items exist only in partition estimates. Returned groups contain the
original individual units; actual poses and handling still require replay.
"""
from collections import Counter, defaultdict
from copy import deepcopy

from .regular_patterns import partition_by_height
from .volumetric_patterns import cover_variants


def partition_with_motifs(items, options, count, recipes, *, selection_index=0,
                          padding=1., selections=None):
    if selections is None:
        selections = cover_variants(items, recipes, options=options, padding=padding)
    if not selections:
        return partition_by_height(items, options, count, 'cost')
    selected = selections[min(selection_index, len(selections)-1)]
    by_id = {i['id']: i for i in items}
    remaining = {i['id']: list(i.get('packing_unit_ids',
                 [f"{i['id']}#{n+1}" for n in range(i['quantity'])])) for i in items}
    virtual = []; virtual_options = {}; members = {}
    for number, recipe in enumerate(selected):
        key = f'partition-motif-{number}'
        members[key] = [(iid, remaining[iid].pop(0)) for iid in recipe['item_ids']]
        virtual.append({'id': key, 'quantity': 1})
        virtual_options[key] = [{'dimensions_mm': [max(.001, d-2*padding)
                                                   for d in recipe['dimensions_mm']]}]
    for iid, uids in remaining.items():
        if not uids:
            continue
        key = f'partition-source-{iid}'
        virtual.append({'id': key, 'quantity': len(uids)})
        virtual_options[key] = options[iid]
        members[key] = [(iid, uid) for uid in uids]
    if len(virtual) < count:
        return partition_by_height(items, options, count, 'cost')
    proposed = partition_by_height(virtual, virtual_options, count, 'cost')
    groups = []
    for group in proposed:
        assignments = defaultdict(list)
        for item in group:
            for iid, uid in members[item['id']]:
                assignments[iid].append(uid)
        groups.append([{**deepcopy(by_id[iid]), 'quantity': len(uids),
                        'packing_unit_ids': uids} for iid, uids in assignments.items()])
    expected = Counter((i['id'], uid) for i in items
                       for uid in i.get('packing_unit_ids', [f"{i['id']}#{n+1}" for n in range(i['quantity'])]))
    actual = Counter((i['id'], uid) for group in groups for i in group for uid in i['packing_unit_ids'])
    if actual != expected or any(n != 1 for n in actual.values()):
        raise ValueError('Motif partition changed original unit identities')
    return groups
