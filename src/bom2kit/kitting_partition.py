"""Reunite complete accessory sets before generating physical carton layouts."""
from collections import Counter, defaultdict
from copy import deepcopy

from .part_properties import ATOMIC_ACCESSORY_SETS, coalesce_items


def reunite_accessory_sets(groups, cards, cost):
    """Move whole set members to the least-cost proposed carton, retaining IDs.

    Cost is a search estimate. Returned cartons still require complete layout
    generation and replay. Empty groups are removed, never delivered as boxes.
    """
    result = deepcopy(groups)
    def inventory(values):
        return Counter((i['id'], uid) for group in values for i in group
                       for uid in i.get('packing_unit_ids', [f"{i['id']}#{n+1}" for n in range(i['quantity'])]))
    before = inventory(result)
    sets = defaultdict(set)
    for group in result:
        for item in group:
            card = cards[item['id']]; assembly = card['assembly']['value']
            if assembly in ATOMIC_ACCESSORY_SETS:
                sets[(card['family']['value'], assembly)].add(item['id'])
    for ids in sets.values():
        occupied = [n for n, group in enumerate(result) if any(i['id'] in ids for i in group)]
        if len(occupied) <= 1:
            continue
        members = coalesce_items([i for group in result for i in group if i['id'] in ids])
        stripped = [[i for i in group if i['id'] not in ids] for group in result]
        candidates = []
        for target in occupied:
            proposal = deepcopy(stripped)
            proposal[target] = coalesce_items(proposal[target]+members)
            proposal = [g for g in proposal if g]
            candidates.append((sum(cost(g) for g in proposal), proposal))
        result = min(candidates, key=lambda p: p[0])[1]
    if inventory(result) != before or any(n != 1 for n in before.values()):
        raise ValueError('Accessory-set repair changed original source units')
    return result
