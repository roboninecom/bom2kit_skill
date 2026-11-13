"""Isolated CP-SAT exact-cover master for generated regular carton candidates.

The objective is a proposal surrogate. Outer foam, tiling, actual resulting
carton sizes and original meshes must be independently evaluated afterward.
"""
import json
import math
from pathlib import Path
import sys


def solve(data):
    import ortools
    from ortools.sat.python import cp_model
    model=cp_model.CpModel();candidates=data['candidates'];expected=data['expected']
    variables=[model.new_bool_var(f'candidate-{i}') for i in range(len(candidates))]
    for iid,quantity in expected.items():
        model.add(sum(variables[i]*c['contents'].get(iid,0) for i,c in enumerate(candidates))==quantity)
    if any(set(c['contents'])-set(expected) for c in candidates):raise ValueError('Unknown candidate contents')
    model.add(sum(variables)==data['cartons'])
    types={tuple(c['size_key']) for c in candidates}
    used={key:model.new_bool_var(f'type-{index}') for index,key in enumerate(sorted(types))}
    for i,c in enumerate(candidates):model.add(variables[i]<=used[tuple(c['size_key'])])
    # Types describe pre-tiling patterns only; do not confuse with final carton SKUs.
    for key,var in used.items():model.add(var<=sum(variables[i] for i,c in enumerate(candidates) if tuple(c['size_key'])==key))
    if data.get('max_nominal_types') is not None:model.add(sum(used.values())<=data['max_nominal_types'])
    costs=[math.ceil(math.prod(c['external_mm'])/1000) for c in candidates]
    if data.get('objective','volume')=='types':
        model.minimize(sum(used.values())*(sum(costs)+1)+sum(v*c for v,c in zip(variables,costs)))
    else:model.minimize(sum(v*c for v,c in zip(variables,costs)))
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=data['time_limit']
    solver.parameters.num_search_workers=1;solver.parameters.random_seed=0
    status=solver.solve(model)
    selected=[i for i,v in enumerate(variables) if solver.value(v)] if status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else []
    return {'status':solver.status_name(status),'selected':selected,'seconds':solver.wall_time,
            'ortools_version':ortools.__version__,'scope':'Finite generated candidate cover; not global packing optimality'}


if __name__=='__main__':
    source,target=map(Path,sys.argv[1:3])
    target.write_text(json.dumps(solve(json.loads(source.read_bytes()))),encoding='utf8')
