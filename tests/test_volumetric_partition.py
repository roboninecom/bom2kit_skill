from collections import Counter

from bom2kit.volumetric_partition import partition_with_motifs


def test_partition_retains_pairs_and_exact_source_copy_ids():
    items = [{'id': 'large', 'quantity': 2, 'mesh': {'sha256': 'large-source'}},
             {'id': 'small', 'quantity': 3, 'packing_unit_ids': ['small#2', 'small#5', 'small#8'],
              'mesh': {'sha256': 'small-source'}}]
    options = {'large': [{'dimensions_mm': [80, 40, 50]}],
               'small': [{'dimensions_mm': [10, 10, 10]}]}
    recipe = {'id': 'nested', 'item_ids': ['large', 'small'], 'dimensions_mm': [82, 42, 52]}
    groups = partition_with_motifs(items, options, 2, [recipe], selections=[[recipe, recipe]])
    membership = {uid: n for n, group in enumerate(groups) for item in group for uid in item['packing_unit_ids']}
    assert membership['large#1'] == membership['small#2']
    assert membership['large#2'] == membership['small#5']
    assert Counter(i['id'] for g in groups for i in g for _ in i['packing_unit_ids']) == {'large': 2, 'small': 3}
    assert set(membership) == {'large#1', 'large#2', 'small#2', 'small#5', 'small#8'}
    assert all(i['mesh'] == next(source['mesh'] for source in items if source['id'] == i['id'])
               for group in groups for i in group)


def test_partition_without_motifs_keeps_floor_fallback():
    items = [{'id': 'a', 'quantity': 1}, {'id': 'b', 'quantity': 1}]
    options = {i['id']: [{'dimensions_mm': [20, 20, 10]}] for i in items}
    groups = partition_with_motifs(items, options, 2, [])
    assert sorted(i['id'] for group in groups for i in group) == ['a', 'b']
