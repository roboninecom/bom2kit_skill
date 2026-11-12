"""Exploded views must not change the certified packing or its contents."""
from copy import deepcopy
import numpy as np
import pytest
from bom2kit.packing_illustrations import cuboid,exploded_scene,render_scene


def fixture():
    modules=[{'id':'a','position_mm':[2,2,2],'external_mm':[10,10,10],'unit_ids':['part#1']},
             {'id':'b','position_mm':[2,2,12],'external_mm':[10,10,10],'unit_ids':['part#2']}]
    panels=[{'id':'foam-bottom','origin_mm':[0,0,0],'dimensions_mm':[14,14,2]},
            {'id':'foam-top','origin_mm':[0,0,22],'dimensions_mm':[14,14,2]}]
    result={'input':{'container':{'inner_mm':[14,14,24]}},
            'logistics':{'policy':{'carton':{'wall_mm':1,'inner_wall_mm':1}},'foam_panels':panels,'block_mm':[10,10,20]}}
    meshes={'part#1':cuboid([3,3,3],[4,4,4]),'part#2':cuboid([3,3,13],[4,4,4])}
    return result,modules,meshes


def test_explosion_preserves_sources_and_uses_one_translation_per_carton():
    result,modules,meshes=fixture();before=deepcopy(result);vertices={k:v.vertices.copy() for k,v in meshes.items()}
    objects,labels,display=exploded_scene(result,modules,meshes)
    assert result==before
    assert [d['carton_id'] for d in display]==['a','b']
    assert display[1]['translation_mm'][2]>display[0]['translation_mm'][2]
    for entry in display:
        for uid in entry['unit_ids']:
            target=vertices[uid]+entry['translation_mm']
            assert any(m.vertices.shape==target.shape and np.allclose(m.vertices,target) for m,_ in objects)
            np.testing.assert_array_equal(meshes[uid].vertices,vertices[uid])


def test_clean_scene_renders_geometry_without_mutating_it(tmp_path):
    pytest.importorskip('vtk')
    from PIL import Image
    mesh=cuboid([0,0,0],[10,15,20]);before=mesh.vertices.copy();output=tmp_path/'view.png'
    render_scene([(mesh,(.7,.7,.7))],output,size=(400,300),labels=[('1',[5,0,10])])
    pixels=np.asarray(Image.open(output).convert('RGB'))
    assert pixels.shape==(300,400,3)
    assert (pixels.mean(axis=2)<225).mean()>.08
    np.testing.assert_array_equal(before,mesh.vertices)
