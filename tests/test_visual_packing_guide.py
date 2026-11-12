"""Drawing labels and inventory counts must refer to the same original units."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('visual_guide',Path(__file__).resolve().parents[1]/'scripts/build_visual_packing_guide.py')
guide=importlib.util.module_from_spec(spec);spec.loader.exec_module(guide)


def fixture():
    poses=[{'item_id':'a','unit_id':'a#1'},{'item_id':'a','unit_id':'a#2'},{'item_id':'b','unit_id':'b#1'}]
    layers=[{'id':'upper'},{'id':'lower'}]
    result={'layout':{'placements':poses},'groups':{'assembly-pair#1':['a#1','a#2']},
            'envelope_design':{'candidate':{'layout':{'layers':layers,'placements':[
                {'unit_id':'b#1','layer_id':'upper'},{'unit_id':'pair#1','layer_id':'lower'}]}}},
            'logistics':{'modules':[{'id':'upper'},{'id':'lower'}]}}
    plan={'cartons_in_outer_insertion_order':[
        {'id':'lower','packing_sequence':[{'unit_ids':['a#1','a#2']}]},
        {'id':'upper','packing_sequence':[{'unit_ids':['b#1']}]}]}
    return result,plan


def test_numbering_follows_plan_not_source_layer_array():
    result,plan=fixture();original=deepcopy(result)
    records=guide.carton_records(result,plan)
    assert [(r['number'],r['module']['id']) for r in records]==[(1,'lower'),(2,'upper')]
    assert records[0]['counts']=={'a':2}
    assert records[0]['item_slots']=={'a':[1]}
    assert records[0]['order']==[[1]]
    assert result==original


def test_missing_original_unit_prevents_a_complete_guide():
    result,plan=fixture();result['groups']['assembly-pair#1']=['a#1']
    plan['cartons_in_outer_insertion_order'][0]['packing_sequence'][0]['unit_ids']=['a#1']
    with pytest.raises(ValueError,match='cover every original'):guide.carton_records(result,plan)


def test_changed_source_is_rejected_before_rendering(tmp_path):
    path=tmp_path/'mesh.json';path.write_text('{}')
    result={'input':{'items':[{'id':'a','mesh':{'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}}]}}
    path.write_text('{"changed":true}')
    with pytest.raises(ValueError,match='Source changed'):guide.load_geometry(result)


def test_property_labels_are_bound_to_the_frozen_concept(tmp_path):
    from bom2kit.report import fingerprint
    properties={'source_library_fingerprint':'source-hash','cards':{'a':{'part_type':{'value':'clamps'}}}}
    path=tmp_path/'properties.json';path.write_text(json.dumps(properties))
    result={'source_library_sha256':'source-hash','input':{'items':[{'id':'a'}]},
            'concept':{'properties_fingerprint':fingerprint(properties)}}
    assert guide.bound_property_cards(result,path)==properties['cards']
    properties['cards']['a']['part_type']['value']='electronics';path.write_text(json.dumps(properties))
    with pytest.raises(ValueError,match='selected concept'):guide.bound_property_cards(result,path)
