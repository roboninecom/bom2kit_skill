"""Regressions for true cavity use, rather than overlapping drawing envelopes."""
from hashlib import sha256
import json

import numpy as np
import pytest
import trimesh

from bom2kit.spectral_nesting import discover_pairs, variants


def source(tmp_path, iid, mesh):
    mesh.apply_translation(-mesh.bounds[0])
    path = tmp_path / (iid + '.json')
    path.write_text(json.dumps({'units': 'mm', 'vertices_mm': mesh.vertices.tolist(),
                                'triangles': mesh.faces.tolist()}))
    return {'id': iid, 'quantity': 1, 'mesh': {'path': str(path),
            'sha256': sha256(path.read_bytes()).hexdigest()}}, mesh


def options(mesh):
    return [{'transform': np.eye(4).tolist(), 'dimensions_mm': mesh.extents.tolist()}]


def tray():
    pieces = []
    for dims, center in [([60, 60, 3], [30, 30, 1.5]),
                         ([4, 60, 37], [2, 30, 21.5]),
                         ([4, 60, 37], [58, 30, 21.5]),
                         ([52, 4, 37], [30, 2, 21.5]),
                         ([52, 4, 37], [30, 58, 21.5])]:
        part = trimesh.creation.box(dims); part.apply_translation(center)
        pieces.append(part)
    return trimesh.util.concatenate(pieces)


def test_actual_cavity_retains_originals_and_protective_interface(tmp_path):
    host, hm = source(tmp_path, 'tray', tray())
    child, cm = source(tmp_path, 'block', trimesh.creation.box([30, 30, 20]))
    found = discover_pairs(host, child, options(hm), options(cm), seconds=8)
    nested = [r for r in found['recipes'] if r['kind'] == 'supported_nesting']
    assert nested, found['diagnostics']
    recipe = nested[0]
    assert recipe['dimensions_mm'] == pytest.approx([62, 62, 42])
    assert recipe['envelope_saving_fraction'] > .3
    assert recipe['sheet']['dimensions_mm'][2] == pytest.approx(2.2)
    assert recipe['assembly_replay_required']  # Source geometry alone is insufficient.
    a, b = hm.copy(), cm.copy()
    a.apply_transform(recipe['transforms'][0]); b.apply_transform(recipe['transforms'][1])
    manager = trimesh.collision.CollisionManager(); manager.add_object('a', a)
    assert not manager.in_collision_single(b)
    assert manager.min_distance_single(b) >= 2.2 - 1e-6
    assert b.bounds[1, 2] < a.bounds[1, 2]  # Within the cavity, not a stack above it.
    from bom2kit.volumetric_patterns import materialize
    from bom2kit.concept_patterns import compose_zones
    from bom2kit.practical_design import build_candidate
    from bom2kit.carton_tiling import tile_modules
    full_recipe = {**recipe, 'id': 'cavity', 'item_ids': ['tray', 'block'],
                   'sheets': [{**recipe['sheet'], 'lower_index': 0, 'upper_index': 1}]}
    pattern = materialize(full_recipe, {'tray': host, 'block': child}, ['tray#1', 'block#1'], 1., 1.5)
    pattern = compose_zones([{'id': 'cavity', 'patterns': [pattern]}], 1.5, seconds=.05)[0]
    policy = {'families': {'tray': 'printed', 'block': 'printed'}, 'allow_all_rotations': True,
              'max_inner_cartons': 1, 'max_carton_types': 1,
              'item_padding_mm': 1., 'clearance_mm': .2,
              'carton': {'wall_mm': 7., 'protection_mm': 15., 'inner_wall_mm': 1.5,
                         'reserved_top_mm': .8, 'gap_mm': .2, 'dimension_increment_mm': 1.}}
    modules = [{'family': 'printed', 'items': [host, child], 'patterns': [pattern]}]
    tiled = tile_modules(modules, wall=7, foam=15, max_types=1, time_limit=.1)['candidate']
    result = build_candidate({'units': 'mm', 'items': [host, child]}, policy, modules, tiled)
    assert result['practical']['support']['valid']
    assert result['practical']['hand_access']['valid'], result['practical']['hand_access']


def test_quarter_turn_voxels_follow_source_coordinates(tmp_path):
    item, mesh = source(tmp_path, 'asymmetric', tray())
    data = variants(item, options(mesh), pitch=2)
    for variant in data:
        occupied = np.argwhere(variant['grid']) * 2 + variant['grid_origin']
        assert occupied.min(0) == pytest.approx(variant['mesh'].bounds[0], abs=2.)
        assert occupied.max(0) == pytest.approx(variant['mesh'].bounds[1], abs=2.)


def test_stale_source_hash_rejected(tmp_path):
    item, mesh = source(tmp_path, 'box', trimesh.creation.box([10, 20, 30]))
    item['mesh']['sha256'] = '0' * 64
    with pytest.raises(ValueError):
        variants(item, options(mesh))


def test_voxel_disk_cache_survives_a_cold_memory_cache(tmp_path, monkeypatch):
    from bom2kit.spectral_nesting import _variant
    item, mesh = source(tmp_path, 'cached', trimesh.creation.box([10, 20, 30]))
    first = variants(item, options(mesh), voxel_cache=tmp_path/'voxels')
    expected = first[0]['grid'].copy()
    _variant.cache_clear()
    def unexpected_rasterization(*args, **kwargs):
        raise AssertionError('A bound disk cache should avoid rasterizing again')
    monkeypatch.setattr(trimesh.Trimesh, 'voxelized', unexpected_rasterization)
    reused = variants(item, options(mesh), voxel_cache=tmp_path/'voxels')
    assert np.array_equal(reused[0]['grid'], expected)


def test_six_individual_parts_expand_without_invented_rigid_group(tmp_path):
    from bom2kit.volumetric_clusters import extend_catalog
    from bom2kit.volumetric_patterns import materialize, cover_variants
    item, mesh = source(tmp_path, 'plate', trimesh.creation.box([30, 30, 5]))
    item['quantity'] = 6
    found = discover_pairs(item, item, options(mesh), options(mesh), seconds=4)
    pair = next(r for r in found['recipes'] if r['kind'] == 'protected_stack')
    recipe = {**pair, 'id': 'test-pair', 'item_ids': ['plate', 'plate'],
              'sheets': [{**pair['sheet'], 'lower_index': 0, 'upper_index': 1}]}
    extended, diagnostic = extend_catalog([recipe], [item], 1., .2, seconds=8)
    six = next(r for r in extended if len(r['item_ids']) == 6)
    pattern = materialize(six, {'plate': item}, [f'plate#{n}' for n in range(6)], 1., 1.5)
    assert len(pattern['placements']) == 6
    assert len(pattern['protective_separators']) == 5
    assert pattern['preassemblies'] == 0
    assert len({p['unit_id'] for p in pattern['placements']}) == 6
    assert cover_variants([item], [recipe, six])
    reduced = {**item, 'quantity': 1}
    assert not cover_variants([reduced], [recipe, six])


def test_cluster_correlation_finds_new_third_part_offset(tmp_path):
    from bom2kit.cluster_correlation import extend_with_correlation
    host, hm = source(tmp_path, 'tray', tray())
    child, cm = source(tmp_path, 'large', trimesh.creation.box([30, 30, 20]))
    small, _ = source(tmp_path, 'small', trimesh.creation.box([10, 10, 10]))
    pair = next(r for r in discover_pairs(host, child, options(hm), options(cm), seconds=3)['recipes']
                if r['kind'] == 'supported_nesting')
    recipe = {**pair, 'id': 'seed', 'item_ids': ['tray', 'large'],
              'sheets': [{**pair['sheet'], 'lower_index': 0, 'upper_index': 1}]}
    library = {'units': 'mm', 'items': [host, child, small]}
    policy = {'item_padding_mm': 1., 'carton': {'gap_mm': .2},
              'families': {i['id']: 'printed' for i in library['items']}}
    found, diagnostic = extend_with_correlation([recipe], library, policy,
        output=tmp_path/'obstacles', seconds=12, pair_seconds=4, maximum_members=3)
    assert found, diagnostic
    nested = min(found, key=lambda r: np.prod(r['dimensions_mm']))
    assert nested['item_ids'] == ['tray', 'large', 'small']
    assert nested['source_hashes'] == [i['mesh']['sha256'] for i in library['items']]
    assert nested['dimensions_mm'] == pytest.approx([62, 62, 42])
    assert len(nested['sheets']) == 2
    assert nested['assembly_replay_required']


def test_cluster_seed_is_rejected_when_source_geometry_changes(tmp_path):
    from bom2kit.cluster_correlation import extend_with_correlation
    item, _ = source(tmp_path, 'part', trimesh.creation.box([10, 10, 10]))
    item['quantity'] = 2
    recipe = {'item_ids': ['part', 'part'], 'source_hashes': ['stale', 'stale']}
    policy = {'item_padding_mm': 1., 'carton': {'gap_mm': .2}, 'families': {'part': 'printed'}}
    with pytest.raises(ValueError, match='source hash'):
        extend_with_correlation([recipe], {'items': [item]}, policy, output=tmp_path/'search', seconds=.1)


def test_large_cluster_seed_is_skipped_after_bom_quantity_reduction(tmp_path):
    from bom2kit.cluster_correlation import extend_with_correlation
    item, _ = source(tmp_path, 'part', trimesh.creation.box([10, 10, 10]))
    item['quantity'] = 10
    recipe = {'item_ids': ['part']*11, 'source_hashes': [item['mesh']['sha256']]*11}
    policy = {'item_padding_mm': 1., 'carton': {'gap_mm': .2}, 'families': {'part': 'printed'}}
    found, diagnostic = extend_with_correlation([recipe], {'items': [item]}, policy,
        output=tmp_path/'search', seconds=.1, maximum_members=12)
    assert found == [] and diagnostic['trials'] == []
    assert diagnostic['maximum_members'] == 12


def test_internal_underside_can_rest_on_a_post_without_floating_bottom(tmp_path):
    from copy import deepcopy
    from bom2kit.volumetric_patterns import materialize
    from bom2kit.concept_patterns import compose_zones
    from bom2kit.practical_design import build_candidate
    from bom2kit.practical_validation import check_floor_support
    from bom2kit.carton_tiling import tile_modules
    lower, lm = source(tmp_path, 'post', trimesh.creation.box([20, 20, 30]))
    pieces = []
    for size, center in [([40, 40, 4], [20, 20, 28]), ([4, 40, 26], [2, 20, 13]),
                         ([4, 40, 26], [38, 20, 13])]:
        part = trimesh.creation.box(size); part.apply_translation(center); pieces.append(part)
    upper, um = source(tmp_path, 'bridge', trimesh.util.concatenate(pieces))
    found = discover_pairs(lower, upper, options(lm), options(um), seconds=5)
    nested = [r for r in found['recipes'] if r['sheet'] and r['sheet']['support_surface']=='paired_horizontal_faces']
    assert nested, found['diagnostics']
    recipe = min(nested, key=lambda r: np.prod(r['dimensions_mm']))
    assert recipe['dimensions_mm'][2] == pytest.approx(38.2)
    recipe = {**recipe, 'id': 'internal-roof', 'item_ids': ['post', 'bridge'],
              'sheets': [{**recipe['sheet'], 'lower_index': 0, 'upper_index': 1}]}
    pattern = materialize(recipe, {'post': lower, 'bridge': upper}, ['post#1', 'bridge#1'], 1., 1.5)
    pattern = compose_zones([{'id': 'internal-roof', 'patterns': [pattern]}], 1.5, seconds=.1)[0]
    policy = {'families': {'post': 'printed', 'bridge': 'printed'}, 'allow_all_rotations': True,
              'max_inner_cartons': 1, 'max_carton_types': 1, 'item_padding_mm': 1., 'clearance_mm': .2,
              'carton': {'wall_mm': 7., 'protection_mm': 15., 'inner_wall_mm': 1.5,
                         'reserved_top_mm': .8, 'gap_mm': .2, 'dimension_increment_mm': 1.}}
    modules = [{'family': 'printed', 'items': [lower, upper], 'patterns': [pattern]}]
    tiled = tile_modules(modules, wall=7, foam=15, max_types=1, time_limit=.1)['candidate']
    result = build_candidate({'units': 'mm', 'items': [lower, upper]}, policy, modules, tiled)
    assert result['practical']['support']['valid'], result['practical']['support']
    assert result['practical']['hand_access']['valid'], result['practical']['hand_access']
    bad = deepcopy(result)
    bad['practical']['protective_separators'][0]['origin_mm'][2] += 1.
    assert not check_floor_support(bad)['valid']
