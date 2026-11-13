"""Source-hash-bound reusable search catalog, independent of carton references."""
from hashlib import sha256
from itertools import combinations_with_replacement
import json
import math
from pathlib import Path
from time import perf_counter

from .packing_states import declared_state
from .practical_geometry import load_mesh, stable_pose_options
from .report import fingerprint
from .spectral_nesting import discover_pairs


def build_catalog(library, policy, *, cache=None, pose_cache=None, pair_seconds=15.,
                  max_pairs=32, pitch=2., minimum_sheet_side=10., progress=None,
                  source_kinds=('source_part', 'factory_carton')):
    started = perf_counter()
    if max_pairs < 1:
        raise ValueError('Positive pair count required')
    padding = policy['item_padding_mm']; gap = policy['carton']['gap_mm']
    items = {i['id']: i for i in library['items']}
    options = {}; geometry = {}; candidates = []
    for item in library['items']:
        if declared_state(item)['kind'] not in source_kinds:
            continue
        mesh = load_mesh(item)
        # Tiny accessory parts cannot drive a whole kit's shipping dimensions.
        # They still retain complete ordinary placement and BOM coverage.
        if math.prod(mesh.extents) < 1000:
            continue
        geometry[item['id']] = {'volume': float(mesh.volume), 'envelope': float(math.prod(mesh.extents)),
                                'void': max(0., float(math.prod(mesh.extents)-mesh.volume))}
    repeated = []; mixed = []
    for a, b in combinations_with_replacement(geometry, 2):
        if policy['families'][a] != policy['families'][b] or (a == b and items[a]['quantity'] < 2):
            continue
        ga, gb = geometry[a], geometry[b]
        score = min(ga['void'], gb['envelope']) + min(gb['void'], ga['envelope'])
        if declared_state(items[a])['kind'] == declared_state(items[b])['kind'] == 'factory_carton':
            score += min(ga['envelope'], gb['envelope'])
        (repeated if a == b else mixed).append((score, a, b))
    # A pure size sort repeatedly tests the same two large housings and misses
    # the rest of a kit. Diminishing endpoint weights spread a bounded search
    # across source parts while retaining promising alternative partners.
    used = {}
    while len(candidates) < max_pairs and (repeated or mixed):
        for queue in (repeated, mixed):
            if not queue or len(candidates) >= max_pairs: continue
            selected = max(queue, key=lambda c: c[0]/(1+used.get(c[1], 0)+used.get(c[2], 0)))
            queue.remove(selected); candidates.append(selected)
            for iid in set(selected[1:]): used[iid] = used.get(iid, 0)+1
    recipes = []; trials = []; directory = Path(cache) if cache else None
    if directory: directory.mkdir(parents=True, exist_ok=True)
    engine = sha256(Path(__file__).with_name('spectral_nesting.py').read_bytes()).hexdigest()
    for index, (_, aid, bid) in enumerate(candidates):
        first, second = items[aid], items[bid]
        for item in (first, second):
            if item['id'] not in options:
                if progress:
                    progress({'stage': 'volumetric_source_preparation', 'item': item['id'],
                              'seconds': perf_counter()-started})
                options[item['id']] = stable_pose_options(item, maximum=8, cache=pose_cache,
                                                         preserve_faces=True, include_projection=False)
        # Try both host directions for unequal parts. Height/contact is directional.
        for aid, bid in ([(aid, bid)] if aid == bid else [(aid, bid), (bid, aid)]):
            first, second = items[aid], items[bid]
            binding = {'engine': engine, 'hashes': [first['mesh']['sha256'], second['mesh']['sha256']],
                       'options': [options[aid], options[bid]], 'padding': padding, 'gap': gap,
                       'pitch': pitch, 'seconds': pair_seconds, 'minimum_sheet_side': minimum_sheet_side}
            key = fingerprint(binding); file = directory / (key+'.json') if directory else None
            cached = bool(file and file.exists()); tick = perf_counter()
            if cached:
                data = json.loads(file.read_bytes())
                if data['binding'] != binding:
                    raise ValueError('Catalog cache binding mismatch')
                found = data['result']
            else:
                found = discover_pairs(first, second, options[aid], options[bid], padding=padding, gap=gap,
                                       pitch=pitch, seconds=pair_seconds, minimum_sheet_side=minimum_sheet_side,
                                       voxel_cache=directory/'voxel-grids' if directory else None)
                if file: file.write_text(json.dumps({'binding': binding, 'result': found}), encoding='utf8')
            trial = {'items': [aid, bid], 'cache_hit': cached, 'wall_seconds': perf_counter()-tick,
                     'diagnostics': found['diagnostics']}
            trials.append(trial)
            for position, pair in enumerate(found['recipes']):
                recipe = {k: v for k, v in pair.items() if k != 'sheet'}
                recipe.update(id=fingerprint([key, aid, bid, position])[:20], item_ids=[aid, bid], sheets=[])
                if pair['sheet']:
                    recipe['sheets'] = [{**pair['sheet'], 'lower_index': 0, 'upper_index': 1}]
                recipes.append(recipe)
            if progress:
                progress({'stage': 'volumetric_pair', 'pair': index+1, 'total_pairs': len(candidates),
                          'items': [aid, bid], 'recipes': len(found['recipes']), 'cache_hit': cached,
                          'seconds': perf_counter()-started})
    return {'schema': 1, 'backend': 'scipy_full_3d_correlation', 'source_library_hash': fingerprint(library),
            'protection': {'padding_mm': padding, 'gap_mm': gap}, 'engine_sha256': engine,
            'recipes': recipes, 'trials': trials, 'seconds': perf_counter()-started,
            'scope': 'Source clearance proposals. Complete-kit support/access/BOM replay still required.'}
