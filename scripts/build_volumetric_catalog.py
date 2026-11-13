"""Discover reusable protected 3D source combinations without reference layouts."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from bom2kit.volumetric_catalog import build_catalog
from bom2kit.volumetric_clusters import extend_catalog


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('library', type=Path); p.add_argument('policy', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cache', type=Path); p.add_argument('--pose-cache', type=Path)
    p.add_argument('--pair-seconds', type=float, default=15.)
    p.add_argument('--max-pairs', type=int, default=32)
    p.add_argument('--pitch', type=float, default=2.)
    p.add_argument('--minimum-sheet-side', type=float, default=10.)
    p.add_argument('--extend-catalog', type=Path, help='Reuse an existing source catalog and only extend its pairs')
    p.add_argument('--cluster-seconds', type=float, default=30.)
    p.add_argument('--source-kinds', nargs='+', choices=['source_part', 'factory_carton'],
                   default=['source_part', 'factory_carton'])
    p.add_argument('--merge-catalog', type=Path, action='append', default=[], help='Merge earlier source-bound proposals before cluster extension')
    a = p.parse_args()
    library = json.loads(a.library.read_bytes()); policy = json.loads(a.policy.read_bytes())
    result = json.loads(a.extend_catalog.read_bytes()) if a.extend_catalog else build_catalog(library, policy,
                           cache=a.cache, pose_cache=a.pose_cache, pair_seconds=a.pair_seconds,
                           max_pairs=a.max_pairs, pitch=a.pitch, minimum_sheet_side=a.minimum_sheet_side,
                           source_kinds=a.source_kinds,
                           progress=lambda r: print(json.dumps(r), flush=True))
    known = {i['id']: i['mesh']['sha256'] for i in library['items']}
    if result['protection'] != {'padding_mm': policy['item_padding_mm'], 'gap_mm': policy['carton']['gap_mm']}:
        raise ValueError('Changed protection requires a new catalog')
    result['merged_catalogs'] = []
    for path in a.merge_catalog:
        earlier = json.loads(path.read_bytes())
        if earlier['protection'] != result['protection']: raise ValueError('Cannot merge different protection policies')
        result['recipes'].extend(earlier['recipes'])
        from hashlib import sha256
        result['merged_catalogs'].append({'path': str(path), 'sha256': sha256(path.read_bytes()).hexdigest()})
    result['recipes'] = [r for r in result['recipes'] if len(r['item_ids']) == 2
                         and all(known.get(iid) == digest for iid, digest in zip(r['item_ids'], r['source_hashes'], strict=True))]
    extensions, result['cluster_search'] = extend_catalog(result['recipes'], library['items'],
        policy['item_padding_mm'], policy['carton']['gap_mm'], seconds=a.cluster_seconds)
    result['recipes'].extend(extensions)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({'recipes': len(result['recipes']), 'discovery_seconds': result.get('seconds'),
                      'cluster_seconds': result['cluster_search']['seconds'],
                      'reused_catalog': str(a.extend_catalog) if a.extend_catalog else None}), flush=True)


if __name__ == '__main__':
    main()
