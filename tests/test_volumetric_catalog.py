from copy import deepcopy

import trimesh

from bom2kit.volumetric_catalog import build_catalog
from bom2kit.volumetric_patterns import cover_variants
from test_spectral_nesting import source


def test_cache_reuses_geometry_but_not_changed_protection(tmp_path):
    item, _ = source(tmp_path, 'part', trimesh.creation.box([30, 30, 10]))
    item['quantity'] = 2
    library = {'units': 'mm', 'items': [item]}
    policy = {'item_padding_mm': 1., 'families': {'part': 'printed'}, 'carton': {'gap_mm': .2}}
    kwargs = {'cache': tmp_path/'cache', 'pose_cache': tmp_path/'poses', 'max_pairs': 1, 'pair_seconds': .5}
    first = build_catalog(library, policy, **kwargs)
    assert first['trials'] and not first['trials'][0]['cache_hit']
    changed_bom = deepcopy(library); changed_bom['items'][0]['quantity'] = 3
    reused = build_catalog(changed_bom, policy, **kwargs)
    assert reused['trials'][0]['cache_hit']
    assert first['source_library_hash'] != reused['source_library_hash']
    changed_protection = deepcopy(policy); changed_protection['carton']['gap_mm'] = .8
    rebuilt = build_catalog(library, changed_protection, **kwargs)
    assert not rebuilt['trials'][0]['cache_hit']
    assert all(r['clearance_mm'] == 2.8 for r in rebuilt['recipes'])


def test_shared_carton_height_keeps_stack_with_larger_isolated_pair_volume():
    items = [{'id': 'plate', 'quantity': 2}, {'id': 'tall-part', 'quantity': 1}]
    options = {'plate': [{'dimensions_mm': [30, 30, 5]}],
               'tall-part': [{'dimensions_mm': [10, 10, 40]}]}
    stack = {'id': 'stack', 'item_ids': ['plate', 'plate'], 'dimensions_mm': [32, 32, 14.2],
             'best_separate_envelope_mm3': 64.2*32*7}
    assert 32*32*14.2 > stack['best_separate_envelope_mm3']
    selected = cover_variants(items, [stack], options=options)
    assert selected == [[stack]]  # Saves half the plate footprint at shared height.


def test_factory_cartons_are_stack_candidates_and_recipe_ids_bind_skus(tmp_path):
    first, _ = source(tmp_path, 'servo-a', trimesh.creation.box([30, 30, 10]))
    first.update(quantity=2, packing_state='Individual factory carton')
    second = {**deepcopy(first), 'id': 'servo-b'}
    policy = {'item_padding_mm': 1., 'families': {'servo-a': 'electronics', 'servo-b': 'electronics'},
              'carton': {'gap_mm': .2}}
    catalog = build_catalog({'units': 'mm', 'items': [first, second]}, policy,
                            cache=tmp_path/'cache', max_pairs=3, pair_seconds=1.,
                            source_kinds=('factory_carton',))
    assert any(r['kind'] == 'protected_stack' for r in catalog['recipes'])
    assert any(len(set(r['item_ids'])) == 2 for r in catalog['recipes'])
    assert len({r['id'] for r in catalog['recipes']}) == len(catalog['recipes'])
