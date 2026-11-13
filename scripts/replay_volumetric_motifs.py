"""Independently replay and illustrate catalog motifs as individual source parts.

These are subset experiments, not evidence that a complete kit improves.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from bom2kit.carton_tiling import tile_modules
from bom2kit.concept_patterns import compose_zones, manual_pattern_screen
from bom2kit.practical_design import build_candidate
from bom2kit.practical_geometry import load_mesh
from bom2kit.volumetric_patterns import materialize
from bom2kit.report import fingerprint


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('library', 'policy', 'catalog'): p.add_argument(name, type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--maximum', type=int, default=5)
    p.add_argument('--recipe-id')
    p.add_argument('--render', action='store_true')
    p.add_argument('--control-floor', action='store_true', help='Independently replay a separate floor-layout control for the same source subset')
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
    library, policy, catalog = [json.loads(getattr(a, k).read_bytes()) for k in ('library', 'policy', 'catalog')]
    by_id = {i['id']: i for i in library['items']}; spec = policy['carton']
    if catalog['protection'] != {'padding_mm': policy['item_padding_mm'], 'gap_mm': spec['gap_mm']}:
        raise ValueError('Catalog protection differs from replay policy')
    recipes = sorted(catalog['recipes'], key=lambda r: -r.get('saving_vs_best_separate_fraction', 0))
    if a.recipe_id: recipes = [r for r in recipes if r['id'] == a.recipe_id]
    records = []; signatures = set()
    for recipe in recipes:
        signature = (tuple(sorted(recipe['item_ids'])), recipe['kind'])
        if signature in signatures: continue
        signatures.add(signature)
        started = perf_counter(); counts = Counter(recipe['item_ids'])
        record = {'recipe_id': recipe['id'], 'kind': recipe['kind'], 'items': dict(counts),
                  'scope': 'Source subset; not a complete-kit or physical transport certificate',
                  'local_envelope_saving_fraction': recipe.get('saving_vs_best_separate_fraction')}
        directory = a.output/f'motif-{len(records)+1:02}'; directory.mkdir(exist_ok=True)
        control = None
        try:
            if any(i not in by_id or n > by_id[i]['quantity'] for i, n in counts.items()):
                raise ValueError('Recipe exceeds source BOM quantities')
            items = [{**deepcopy(by_id[i]), 'quantity': n} for i, n in counts.items()]
            used = Counter(); uids = []
            for iid in recipe['item_ids']:
                used[iid] += 1; uids.append(f'{iid}#{used[iid]}')
            pattern = materialize(recipe, by_id, uids, policy['item_padding_mm'], spec['inner_wall_mm'])
            if not manual_pattern_screen(pattern)['valid']: raise ValueError('Contact sheet below manual handling minimum')
            pattern = compose_zones([{'id': 'source-motif', 'patterns': [pattern]}], spec['inner_wall_mm'],
                                    gap=spec['gap_mm'], seconds=.1)[0]
            local = {**policy, 'families': {i: policy['families'][i] for i in counts},
                     'max_inner_cartons': 1, 'max_carton_types': 1}
            if len(set(local['families'].values())) != 1: raise ValueError('Incompatible source families')
            modules = [{'family': next(iter(local['families'].values())), 'items': items, 'patterns': [pattern]}]
            tiled = tile_modules(modules, wall=spec['wall_mm'], foam=spec['protection_mm'],
                                 reserve=spec['reserved_top_mm'], time_limit=.2, max_types=1)['candidate']
            result = build_candidate({'units': 'mm', 'items': items}, local, modules, tiled)
            record.update(valid=result['practical']['valid'], support=result['practical']['support']['valid'],
                          access=result['practical']['hand_access']['valid'],
                          external_volume_l=result['practical']['metrics']['external_volume_l'],
                          result_fingerprint=fingerprint(result))
            (directory/'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
            (directory/'recipe.json').write_text(json.dumps(recipe, indent=2), encoding='utf8')
            if a.control_floor and record['valid']:
                from bom2kit.practical_geometry import stable_pose_options
                from bom2kit.regular_patterns import floor_patterns
                control_started = perf_counter()
                options = {i['id']: stable_pose_options(i, include_projection=False) for i in items}
                floors = floor_patterns(items, options, policy['item_padding_mm'], spec['inner_wall_mm'],
                    gap=spec['gap_mm'], seconds=2., hand_border=7.2, access_lane_mm=6.4)['patterns']
                controls = []
                for floor in floors:
                    module = [{**modules[0], 'patterns': [floor]}]
                    candidate = tile_modules(module, wall=spec['wall_mm'], foam=spec['protection_mm'],
                        reserve=spec['reserved_top_mm'], time_limit=.1, max_types=1)['candidate']
                    if candidate: controls.append((candidate['volume_mm3'], module, candidate))
                attempts = []
                for _, module, candidate in sorted(controls, key=lambda c: c[0])[:6]:
                    try:
                        proposal = build_candidate({'units': 'mm', 'items': items}, local, module, candidate)
                        attempts.append({'valid': proposal['practical']['valid'],
                                         'external_volume_l': candidate['volume_mm3']/1e6})
                        if proposal['practical']['valid']:
                            control = proposal; break
                    except ValueError as error:
                        attempts.append({'valid': False, 'error': str(error)})
                record['floor_control'] = {'attempts': attempts, 'seconds': perf_counter()-control_started,
                    'scope': 'Same complete source subset and protection; bounded floor portfolio, not global optimality'}
                if control:
                    before_l = control['practical']['metrics']['external_volume_l']
                    record['floor_control'].update(external_volume_l=before_l,
                        shipping_volume_saving_fraction=1-record['external_volume_l']/before_l,
                        support=True, access=True)
                    (directory/'floor-control.json').write_text(json.dumps(control, indent=2), encoding='utf8')
            if a.render and record['valid']:
                from bom2kit.packing_illustrations import render_scene, cuboid, FOAM
                colors = [(.76,.78,.80), (.48,.65,.76), (.78,.64,.48), (.56,.72,.60)]
                objects = []
                for index, placement in enumerate(result['layout']['placements']):
                    mesh = load_mesh(by_id[placement['item_id']]); mesh.apply_transform(placement['transform'])
                    objects.append((mesh, colors[index % len(colors)]))
                for sheet in result['practical']['protective_separators']:
                    objects.append((cuboid(sheet['origin_mm'], sheet['dimensions_mm']), FOAM))
                for view in ('iso', 'top', 'side'):
                    render_scene(objects, directory/(view+'.png'), view=view, trim=True)
                if control:
                    objects = []
                    for index, placement in enumerate(control['layout']['placements']):
                        mesh = load_mesh(by_id[placement['item_id']]); mesh.apply_transform(placement['transform'])
                        objects.append((mesh, colors[index % len(colors)]))
                    render_scene(objects, directory/'floor-control-iso.png', trim=True)
        except ValueError as error:
            record.update(valid=False, error=str(error))
        record['seconds'] = perf_counter()-started; records.append(record)
        (directory/'record.json').write_text(json.dumps(record, indent=2), encoding='utf8')
        (a.output/'summary.json').write_text(json.dumps(records, indent=2), encoding='utf8')
        print(json.dumps(record), flush=True)
        if len(records) >= a.maximum: break


if __name__ == '__main__': main()
