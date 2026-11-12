"""Repack only cartons rejected by actual fingertip replay, then retile the block."""
from copy import deepcopy
from time import perf_counter

from .carton_tiling import tile_modules
from .regular_patterns import floor_patterns


def repair(proposal, rejected, options, policy, *, seconds=10., finger_radius=4.,
           hand_border=0., access_lane=0., gap=.2, family_gaps=None,individual=True):
    """Generate a proposal; original geometry and handling must pass fresh replay.

    Retain source-only carton memberships. Failed cartons get access margins
    derived from the unchanged finger model; other cartons retain their selected
    content arrangement. No reference sizes or manual coordinates are imported.
    """
    started=perf_counter();_,modules,tiled,cap=proposal
    modules=deepcopy(modules);spec=policy['carton'];family_gaps=family_gaps or {}
    failures=rejected['practical']['hand_access']['failures']
    failed={f['carton_id'] for f in failures};changed=[]
    blocked={f['carton_id']:f.get('unresolved_units',[]) for f in failures}
    border=max(hand_border,2*finger_radius+.2-policy['item_padding_mm'])
    lane=max(access_lane,2*finger_radius+.4-2*policy['item_padding_mm'])
    leaves=sorted(tiled['leaves'],key=lambda leaf:(leaf['position_mm'][2],leaf['position_mm'][0]))
    for index,leaf in enumerate(leaves,1):
        module=modules[leaf['module']];selected=module['patterns'][leaf['pattern']]
        module['patterns']=[selected]
        if f'module-{index}' not in failed:continue
        if perf_counter()-started>=seconds:
            return None,{'status':'repair_budget_exhausted','seconds':perf_counter()-started}
        remaining=max(.1,seconds-(perf_counter()-started))
        arguments=dict(gap=family_gaps.get(module['family'],gap),increment=spec['dimension_increment_mm'],
                       seconds=min(1.,remaining),hand_border=hand_border if individual else border,access_lane_mm=lane,
                       access_units=blocked[f'module-{index}'] if individual else (),
                       unit_access_margin=border if individual else 0.)
        generated=floor_patterns(module['items'],options,policy['item_padding_mm'],spec['inner_wall_mm'],**arguments)
        try:
            fixed=floor_patterns(module['items'],options,policy['item_padding_mm'],spec['inner_wall_mm'],
                                 target_footprints=[leaf['external_mm'][:2]],**arguments)
            generated['patterns'].extend(fixed['patterns'])
        except ValueError:
            pass
        module['patterns']=generated['patterns'];changed.append(f'module-{index}')
    if not changed:return None,{'status':'no_failed_cartons','seconds':perf_counter()-started}
    candidate=tile_modules(modules,time_limit=min(2.,max(.05,seconds-(perf_counter()-started))),
                           wall=spec['wall_mm'],foam=spec['protection_mm'],reserve=spec['reserved_top_mm'],
                           max_types=cap,increment=spec['dimension_increment_mm'])['candidate']
    diagnostic={'status':'proposal_requires_replay' if candidate else 'no_repaired_block',
                'seconds':perf_counter()-started,'repacked_cartons':changed,
                'hand_border_mm':hand_border if individual else border,
                'individual_access_margin_mm':border if individual else 0.,
                'access_lane_mm':lane,'finger_radius_mm':finger_radius,
                'mode':'individual_unit_margins' if individual else 'whole_carton_margin',
                'before_l':proposal[0]/1e6,'after_l':candidate['volume_mm3']/1e6 if candidate else None,
                'reference_used':False}
    return ((candidate['volume_mm3'],modules,candidate,cap) if candidate else None),diagnostic
