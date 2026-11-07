"""Disjoint proposal shards with independent original-mesh certification."""
from concurrent.futures import ProcessPoolExecutor
from time import perf_counter


def _run_pair_shard(arguments):
    from .mesh_groups import discover_pairs
    return discover_pairs(**arguments)


def discover_pair_shards(library, output, *, workers=1, **options):
    from pathlib import Path
    if type(workers) is not int or not 1 <= workers <= 8:
        raise ValueError("Pair workers must be an integer from 1 to 8")
    if workers == 1:
        return _run_pair_shard(dict(library=library,output=output,**options))
    started=perf_counter()
    jobs=[dict(library=library,output=Path(output)/f"shard-{index}",
               proposal_stride=workers,proposal_offset=index,**options) for index in range(workers)]
    # Every worker has the same soft wall budget and a disjoint ranked proposal
    # stream. Verification may overrun; do not drop unfinished certificates.
    with ProcessPoolExecutor(max_workers=workers) as executor:
        results=list(executor.map(_run_pair_shard,jobs))
    first=results[0]
    if any(r["source_library_sha256"] != first["source_library_sha256"] or
           r["clearance_mm"] != first["clearance_mm"] for r in results):
        raise ValueError("Inconsistent pair shard inputs")
    return {**first,"alternatives":[a for r in results for a in r["alternatives"]],
            "attempts":[a for r in results for a in r["attempts"]],
            "proposal_shard":None,"workers":workers,"elapsed_seconds":perf_counter()-started,
            "worker_seconds":[r["elapsed_seconds"] for r in results]}
