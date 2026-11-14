"""Translate certified motif envelopes with PackingSolver; source replay is separate."""
from copy import deepcopy
import math

from .packing_solver_adapter import pack_floor


def polish(pattern, executable, *, wall=1.5, border=7.2, lane=6.4, gap=.2, seconds=1., increment=1.):
    if not all(math.isfinite(v) for v in (wall,border,lane,gap,seconds,increment)) or min(wall,seconds,increment)<=0 or min(border,lane,gap)<0:
        raise ValueError('Finite positive geometry and solver parameters required')
    zones=pattern.get('semantic_zones',[])
    if not zones or any('origin_mm' not in z for z in zones):
        return None, {'status':'no_bound_motif_zones','elapsed_seconds':0.}
    ownership={uid:str(n) for n,z in enumerate(zones) for uid in z['unit_ids']}
    if len(ownership)!=sum(len(z['unit_ids']) for z in zones) or set(ownership)!={p['unit_id'] for p in pattern['placements']}:
        raise ValueError('Zone membership must exactly cover original units')
    units=[];seed=[];extra=max(0.,lane-gap)
    for n,z in enumerate(zones):
        size=[z['dimensions_mm'][0],z['dimensions_mm'][1]+extra,z['dimensions_mm'][2]]
        units.append({'item_id':str(n),'unit_id':str(n),'dimensions':size,'orientations':[((0,1,2),size)]})
        seed.append({'item_id':str(n),'unit_id':str(n),'position_mm':[z['origin_mm'][0]-border,z['origin_mm'][1]-border,0.],
                     'rotation':[0,1,2],'dimensions_mm':size})
    width=pattern['external_mm'][0]-2*(wall+border)
    trial=pack_floor(units,seed,width,executable=executable,time_limit=seconds,gap=gap)
    if trial['status']!='validated_envelopes':return None,trial
    changed=deepcopy(pattern);positions={p['unit_id']:p['position_mm'] for p in trial['placements']}
    deltas={str(n):[positions[str(n)][k]+border-z['origin_mm'][k] for k in (0,1)] for n,z in enumerate(zones)}
    for p in changed['placements']:
        delta=deltas[ownership[p['unit_id']]]
        for k in (0,1):p['transform'][k][3]+=delta[k];p['envelope_position_mm'][k]+=delta[k]
    for s in changed.get('protective_separators',[]):
        lower=ownership[s['lower_unit_id']];upper=ownership[s['upper_unit_id']]
        if lower!=upper:raise ValueError('Cannot translate a source support independently')
        for k in (0,1):s['origin_mm'][k]+=deltas[lower][k]
    for n,z in enumerate(changed['semantic_zones']):
        for k in (0,1):z['origin_mm'][k]+=deltas[str(n)][k]
    used=[max(p['envelope_position_mm'][k]+p['envelope_dimensions_mm'][k] for p in changed['placements']) for k in range(3)]
    changed['external_mm']=[math.ceil((v+2*wall+(border if k<2 else 0))/increment-1e-8)*increment for k,v in enumerate(used)]
    changed['method']='rectangle_translated_source_motifs'
    changed['motif_rectangle_proposal']={k:v for k,v in trial.items() if k not in ('placements','validation')}
    return changed,{k:v for k,v in trial.items() if k not in ('placements','validation')}


