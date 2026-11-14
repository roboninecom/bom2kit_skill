from copy import deepcopy

import numpy as np
import pytest

from bom2kit.motif_rectangle import polish


def pattern():
    placements=[]
    for uid, origin, size in [('lower',[7.2,7.2,0],[20,20,10]),
                              ('upper',[7.2,7.2,12.2],[20,20,10]),
                              ('single',[50,30,0],[10,10,10])]:
        frame=np.eye(4);frame[:3,3]=np.asarray(origin)+1
        placements.append({'unit_id':uid,'item_id':uid,'transform':frame.tolist(),
                           'envelope_position_mm':origin,'envelope_dimensions_mm':size})
    return {'external_mm':[80,60,25.2],'placements':placements,
            'semantic_zones':[{'unit_ids':['lower','upper'],'origin_mm':[7.2,7.2,0],'dimensions_mm':[20,20,22.2]},
                              {'unit_ids':['single'],'origin_mm':[50,30,0],'dimensions_mm':[10,10,10]}],
            'protective_separators':[{'lower_unit_id':'lower','upper_unit_id':'upper',
                                      'origin_mm':[8.2,8.2,11.],'dimensions_mm':[18,18,2.2]}]}


def backend(units,seed,width,**kwargs):
    assert all(u['orientations'][0][0]==(0,1,2) and len(u['orientations'])==1 for u in units)
    result=deepcopy(seed);result[0]['position_mm']=[0,0,0];result[1]['position_mm']=[25,0,0]
    return {'status':'validated_envelopes','placements':result,'elapsed_seconds':.1}


def test_translations_preserve_every_part_and_its_support_sheet(monkeypatch):
    monkeypatch.setattr('bom2kit.motif_rectangle.pack_floor',backend)
    original=pattern();frozen=deepcopy(original)
    changed,_=polish(original,'unused')
    assert original==frozen
    assert changed['external_mm'][1] < original['external_mm'][1]
    assert changed['placements'][:2] == original['placements'][:2]
    assert changed['protective_separators'] == original['protective_separators']
    assert changed['placements'][2]['envelope_position_mm'] == pytest.approx([32.2,7.2,0])
    assert np.asarray(changed['placements'][2]['transform'])[:3,:3] == pytest.approx(np.eye(3))


def test_cross_zone_support_cannot_be_silently_separated(monkeypatch):
    monkeypatch.setattr('bom2kit.motif_rectangle.pack_floor',backend)
    original=pattern();original['protective_separators'][0]['upper_unit_id']='single'
    with pytest.raises(ValueError,match='support independently'):
        polish(original,'unused')
