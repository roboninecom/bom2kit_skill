from copy import deepcopy

from bom2kit.carton_tiling import tile_modules
from bom2kit.practical_refinement import choose_repacked_block


SPEC = {'wall_mm': 7, 'protection_mm': 15, 'reserved_top_mm': .8,
        'dimension_increment_mm': 1}


def expanded_case():
    original = {'external_mm': [20, 20, 20], 'method': 'nested',
                'placements': [{'unit_id': 'a#1'}, {'unit_id': 'b#1'}]}
    modules = [{'family': 'printed', 'items': [], 'patterns': [original]}]
    expanded = deepcopy(modules)
    expanded[0]['patterns'][0]['external_mm'] = [40, 40, 20]
    tiled = tile_modules(expanded, time_limit=.1, max_types=1)['candidate']
    return modules, tiled


def test_lower_floor_repair_can_lose_shipping_volume_to_original_nesting():
    modules, tiled = expanded_case()
    snapshot = deepcopy((modules, tiled))
    floor = {'external_mm': [30, 30, 10], 'method': 'floor',
             'placements': deepcopy(modules[0]['patterns'][0]['placements'])}
    selected, compact = choose_repacked_block(modules, tiled, {0: [floor]}, SPEC, 1)
    leaf = compact['leaves'][0]
    assert selected[0]['patterns'][leaf['pattern']]['method'] == 'nested'
    floor_only = tile_modules([{**modules[0], 'patterns': [floor]}], time_limit=.1, max_types=1)['candidate']
    assert compact['volume_mm3'] < floor_only['volume_mm3'] < tiled['volume_mm3']
    assert (modules, tiled) == snapshot


def test_floor_repair_is_selected_when_whole_shipping_block_improves():
    modules, tiled = expanded_case()
    floor = {'external_mm': [15, 15, 15], 'method': 'floor',
             'placements': deepcopy(modules[0]['patterns'][0]['placements'])}
    selected, compact = choose_repacked_block(modules, tiled, {0: [floor]}, SPEC, 1)
    assert selected[0]['patterns'][compact['leaves'][0]['pattern']]['method'] == 'floor'
    assert compact['volume_mm3'] < tiled['volume_mm3']


def test_failed_retiling_preserves_original_source_poses(monkeypatch):
    modules, tiled = expanded_case()
    monkeypatch.setattr('bom2kit.practical_refinement.tile_modules', lambda *a, **k: {'candidate': None})
    selected, compact = choose_repacked_block(modules, tiled, {}, SPEC, 1)
    assert selected == modules and compact == tiled
    assert selected is not modules and compact is not tiled
