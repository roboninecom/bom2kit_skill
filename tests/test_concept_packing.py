from copy import deepcopy
from hashlib import sha256
import json

import numpy as np
import pytest
import trimesh

from bom2kit.concept_patterns import repeated_rows, compose_zones
from bom2kit.concept_planner import concept_partitions, design_concepts
from bom2kit.part_properties import describe_parts, semantic_groups
from bom2kit.practical_geometry import stable_pose_options


def inputs(tmp_path):
    items = []
    for iid, dims, name in [("servo-a", [20, 30, 15], "Servo in factory carton"),
                            ("servo-b", [20, 30, 15], "Servo in factory carton"),
                            ("clamp", [35, 20, 15], "Metal clamp")]:
        mesh = trimesh.creation.box(dims); mesh.apply_translation(-mesh.bounds[0])
        path = tmp_path/(iid+".json")
        path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist()}))
        items.append({"id": iid, "name": name, "quantity": 2,
                      "mesh": {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()},
                      "packing_state": "Individual factory carton" if "servo" in iid else "Declared purchased-item envelope"})
    policy = {"families": {"servo-a": "electronics", "servo-b": "electronics", "clamp": "mechanics"},
              "allow_all_rotations": True, "max_inner_cartons": 3, "max_carton_types": 3,
              "item_padding_mm": 1., "clearance_mm": .2,
              "carton": {"wall_mm": 7., "protection_mm": 15., "inner_wall_mm": 1.5,
                         "reserved_top_mm": .8, "gap_mm": .2, "dimension_increment_mm": 1.}}
    return {"units": "mm", "items": items}, policy, {"components": [{"id": i["id"], "quantity": i["quantity"]} for i in items]}


def test_cards_keep_inferences_separate_from_contact_authorization(tmp_path):
    library, policy, _ = inputs(tmp_path)
    cards = describe_parts(library, policy)["cards"]
    assert cards["servo-a"]["part_type"]["value"] == "servos"
    assert cards["servo-a"]["part_type"]["status"] == "name_inference"
    assert cards["clamp"]["material"]["status"] == "unknown"
    assert cards["clamp"]["fragility"]["status"] == "unknown"
    with pytest.raises(ValueError, match="cannot modify geometry"):
        describe_parts(library, policy, annotations={"clamp": {"mesh": {"value": "replacement"}}})
    with pytest.raises(ValueError, match="evidence source"):
        describe_parts(library, policy, annotations={"clamp": {"material": {"value": "steel"}}})


def test_row_and_zone_transforms_preserve_source_quantities_and_containment(tmp_path):
    library, policy, _ = inputs(tmp_path)
    item = library["items"][0]; options = {item["id"]: stable_pose_options(item)}
    rows = repeated_rows(item, options, 1., 1.5)
    zones = compose_zones([{"id": "servos", "patterns": rows}], 1.5, seconds=.05)
    assert zones
    for pattern in zones:
        assert {p["unit_id"] for p in pattern["placements"]} == {"servo-a#1", "servo-a#2"}
        for p in pattern["placements"]:
            original = json.loads(open(item["mesh"]["path"]).read())
            vertices = trimesh.transform_points(original["vertices_mm"], p["transform"])
            low = np.asarray(p["envelope_position_mm"]); high = low+p["envelope_dimensions_mm"]
            assert np.all(vertices.min(0) >= low+1.-1e-6)
            assert np.all(vertices.max(0) <= high-1.+1e-6)
        assert all(z["physical_container"] is False for z in pattern["semantic_zones"])


def test_concept_beam_never_merges_incompatible_families(tmp_path):
    library, policy, _ = inputs(tmp_path)
    cards = describe_parts(library, policy)["cards"]
    groups = semantic_groups(library, cards, "sku")
    patterns = [[{"external_mm": [30, 30, 20]}] for _ in groups]
    beam = concept_partitions(groups, patterns, max_cartons=3)
    assert beam["states"]
    for state in beam["states"]:
        assert sorted(i for members in state for i in members) == list(range(len(groups)))
        assert all(len({groups[i]["family"] for i in members}) == 1 for members in state)


def test_compact_concept_does_not_buy_extra_cartons_only_for_more_labels():
    groups=[{'id':f'type-{i}','family':'compatible'} for i in range(12)]
    patterns=[[{'external_mm':[10,10,10]}] for _ in groups]
    beam=concept_partitions(groups,patterns,profile='compact',max_cartons=7)
    # Equal-height groups have the same area/height volume estimate whether
    # together or split. Increasing label count alone must not prefer 7 boxes.
    assert len(beam['states'][0])==1


def test_frontier_does_not_discard_keeping_repeated_skus_together():
    from bom2kit.concept_planner import _concept_frontier
    together={'practical':{'metrics':{'external_volume_l':20.,'cartons':4,'carton_types':2,
        'source_and_contact_sheet_placements':20,'additional_sku_orientations':0,'split_source_skus':0}},
        'concept':{'organization':{'mixed_group_pairs':3,'additional_spatial_fragments':0,'split_semantic_groups':0}}}
    split=deepcopy(together);split['practical']['metrics']['split_source_skus']=1
    split['concept']['organization']['split_semantic_groups']=1
    assert _concept_frontier([split,together])==[together]
    split['practical']['metrics']['external_volume_l']=19.
    assert len(_concept_frontier([split,together]))==2


def test_actual_block_assignment_repair_preserves_units_and_compatibility(tmp_path):
    library,policy,bom=inputs(tmp_path)
    run=design_concepts(library,policy,bom,seconds=.5,carton_counts=(2,3),type_caps=(3,),
        grouping_modes=('sku',),motif_modes=('rows',),placement_style='cohesive',max_replays=1,
        refinement_budget=0,assignment_budget=1.)
    assert run['status']=='verified',run['trials']
    refinement=run['trials'][0]['assignment_refinement']
    assert refinement['attempts'] and refinement['final_volume_l']<=refinement['initial_volume_l']
    result=run['results'][0]
    assert result['input']['items']==library['items']
    assert {p['unit_id'] for p in result['layout']['placements']}=={f'{i["id"]}#{n+1}' for i in library['items'] for n in range(i['quantity'])}
    by_unit={p['unit_id']:p['item_id'] for p in result['layout']['placements']}
    assert all(len({policy['families'][by_unit[u]] for u in m['unit_ids']})==1 for m in result['logistics']['modules'])


def test_repeated_group_split_can_reunite_without_duplicating_original_units(tmp_path):
    from bom2kit.part_properties import replicated_groups,coalesce_items
    library,policy,bom=inputs(tmp_path);library['items'][0]['quantity']=4
    bom['components'][0]['quantity']=4
    options={i['id']:stable_pose_options(i) for i in library['items']}
    cards=describe_parts(library,policy,options)['cards']
    groups=replicated_groups(library,cards,options,policy)
    assert any(g['semantic_mode']=='replicated' for g in groups)
    merged=coalesce_items([i for g in groups for i in g['items']])
    assert {i['id']:i['quantity'] for i in merged}=={i['id']:i['quantity'] for i in library['items']}
    assert len({uid for i in merged for uid in i['packing_unit_ids']})==8
    with pytest.raises(ValueError,match='duplicate source'):
        coalesce_items([merged[0],merged[0]])
    run=design_concepts(library,policy,bom,seconds=.5,beam_width=4,carton_counts=(2,3),type_caps=(3,),
        motif_modes=('rows',),grouping_modes=('replicated',),placement_style='cohesive',max_replays=1,refinement_budget=0)
    assert run['status']=='verified',run['trials']
    assert len(run['results'][0]['layout']['placements'])==8


def test_manual_material_screen_rejects_tiny_cut_patches_without_changing_geometry():
    from bom2kit.concept_patterns import manual_pattern_screen
    pattern={'protective_separators':[{'lower_unit_id':'a','upper_unit_id':'b','dimensions_mm':[.7,1.6,2]}]}
    original=deepcopy(pattern)
    assert manual_pattern_screen(pattern)['valid'] is False
    assert pattern==original
    assert manual_pattern_screen({'protective_separators':[]})['valid'] is True


def test_access_row_compaction_preserves_clearance_for_near_disjoint_x():
    from bom2kit.regular_patterns import compact_access_rows
    units=[{'unit_id':'a','dimensions':[10,10,10]}, {'unit_id':'b','dimensions':[10,10,25]}]
    poses=[{'unit_id':'a','position_mm':[0,0,0],'rotation':[0,1,2]},
           {'unit_id':'b','position_mm':[10.1,20,0],'rotation':[0,1,2]}]
    packed=compact_access_rows(poses,units,.2,6.4)
    assert packed[1]['position_mm'][1]>=10.2-1e-8


def test_equal_bounding_boxes_do_not_erase_opposite_supported_faces(tmp_path):
    bottom=trimesh.creation.cylinder(radius=25,height=5,sections=16);bottom.apply_translation([25,25,2.5])
    rim=trimesh.creation.annulus(r_min=20,r_max=25,height=25,sections=16);rim.apply_translation([25,25,17.5])
    mesh=trimesh.util.concatenate([bottom,rim]);path=tmp_path/'cup.json'
    path.write_text(json.dumps({'units':'mm','vertices_mm':mesh.vertices.tolist(),'triangles':mesh.faces.tolist()}))
    item={'id':'cup','quantity':2,'mesh':{'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}}
    options=stable_pose_options(item,maximum=12,preserve_faces=True,include_projection=False,cache=tmp_path/'poses')
    assert all('footprint' not in p for p in options)
    upright=[p for p in options if abs(p['dimensions_mm'][2]-30)<.05 and abs(p['contact_frame_signature'][2])>.999]
    assert len(upright)>=2
    assert np.allclose(sorted(upright[0]['dimensions_mm'][:2]),sorted(upright[1]['dimensions_mm'][:2]),atol=.05)
    assert any(np.dot(a['contact_frame_signature'],b['contact_frame_signature'])<-.999 for a in upright for b in upright)
    assert all(p['contact']['valid'] for p in options)


def test_compact_surface_search_uses_a_real_cavity_before_unused_floor(tmp_path):
    from bom2kit.source_surfaces import propose
    from bom2kit.practical_geometry import contact_certificate
    from bom2kit.practical_design import build_candidate
    from bom2kit.carton_tiling import tile_modules
    bottom=trimesh.creation.cylinder(radius=25,height=5,sections=32);bottom.apply_translation([25,25,2.5])
    rim=trimesh.creation.annulus(r_min=20,r_max=25,height=25,sections=32);rim.apply_translation([25,25,17.5])
    cup=trimesh.util.concatenate([bottom,rim])
    child=trimesh.creation.box([20,20,10]);child.apply_translation(-child.bounds[0])
    items=[];options={}
    for iid,mesh in [('cup',cup),('child',child)]:
        path=tmp_path/(iid+'.json');path.write_text(json.dumps({'units':'mm','vertices_mm':mesh.vertices.tolist(),'triangles':mesh.faces.tolist()}))
        items.append({'id':iid,'quantity':1,'mesh':{'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}})
        options[iid]=[{'dimensions_mm':mesh.extents.tolist(),'transform':np.eye(4).tolist(),'contact':contact_certificate(mesh)}]
    generated=propose(items,options,[110,90],1,1.5,border=9,seconds=3,objective='volume',
        compact_voids=True,semantic_labels={'cup':'frames','child':'blocks'})
    assert generated['status']=='complete_source_surface_proposal'
    assert generated['supported_units']==1
    assert generated['pattern']['external_mm'][2]<=35
    _,policy,_=inputs(tmp_path);policy['families']={'cup':'print','child':'print'}
    modules=[{'family':'print','items':items,'patterns':[generated['pattern']]}]
    tile=tile_modules(modules,time_limit=.1,max_types=1)['candidate']
    result=build_candidate({'units':'mm','items':items},policy,modules,tile)
    assert result['practical']['valid']


def test_cached_pair_reuses_geometry_with_new_unit_ids_and_preserved_clearance(tmp_path):
    from bom2kit.regular_floor_pairs import make_floor_pairs, _pair_recipes
    from bom2kit.practical_geometry import contact_certificate
    a=trimesh.creation.box([20,4,10]);a.apply_translation([10,2,5])
    b=trimesh.creation.box([4,16,10]);b.apply_translation([2,12,5])
    mesh=trimesh.util.concatenate([a,b]);path=tmp_path/'angle.json'
    path.write_text(json.dumps({'units':'mm','vertices_mm':mesh.vertices.tolist(),'triangles':mesh.faces.tolist()}))
    source={'id':'angle','quantity':2,'mesh':{'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}}
    choices={'angle':(0,{'transform':np.eye(4).tolist(),'dimensions_mm':[20,20,10],'contact':contact_certificate(mesh)})}
    def units(prefix,count):
        return [{'item_id':'angle','unit_id':f'{prefix}-{k}','dimensions':[22,22,12],
                 'orientations':[((0,1,2),(22,22,12))]} for k in range(count)]
    _pair_recipes.clear()
    _,_,first=make_floor_pairs(units('first',2),choices,{'angle':source},1,.2,seconds=1.)
    assert first
    _,expansions,reused=make_floor_pairs(units('new',4),choices,{'angle':source},1,.2,seconds=0.)
    assert len(reused)==2
    assert {uid for p in reused for uid in p['unit_ids']}=={f'new-{k}' for k in range(4)}
    for entry in expansions.values():
        meshes=[]
        for member in entry['members']:
            transformed=mesh.copy();transformed.apply_transform(member.get('transform_override',np.eye(4)))
            transformed.apply_translation(np.asarray(member['offset_mm'])+1.);meshes.append(transformed)
        manager=trimesh.collision.CollisionManager();manager.add_object('first',meshes[0])
        assert manager.min_distance_single(meshes[1])>=2.2-1e-6
    # Changed protection cannot hit the previous motif cache.
    assert not make_floor_pairs(units('changed',2),choices,{'angle':source},2,.2,seconds=0.)[2]


def test_free_translation_screen_proves_empty_paths_but_not_restraint():
    from bom2kit.retention_screen import free_box_translation
    bounds=[[0,0,0],[10,10,10]]
    assert free_box_translation(bounds,[],[0,0,0],[10,10,30],2,1)==20
    assert free_box_translation(bounds,[[[0,0,15],[10,10,20]]],[0,0,0],[10,10,30],2,1)==5
    # AABB overlap can represent interlocking original CAD; do not call it fixed.
    assert free_box_translation(bounds,[[[2,2,2],[8,8,8]]],[0,0,0],[10,10,30],2,1) is None


def test_access_failure_repairs_geometry_without_relaxing_finger_model(tmp_path):
    library,policy,bom=inputs(tmp_path)
    run=design_concepts(library,policy,bom,seconds=.5,beam_width=4,carton_counts=(2,),type_caps=(2,),
                       motif_modes=('rows',),max_replays=1,hand_border=0.,placement_style='cohesive',repair_budget=20.)
    assert run['status']=='verified',run['trials']
    assert run['trials'][0]['original_rejection']['access']['valid'] is False
    assert run['trials'][0]['local_repair']['thresholds_relaxed'] is False
    assert run['results'][0]['practical']['hand_access']['parameters']['radius_mm']==4.
    assert run['results'][0]['input']['items']==library['items']


def test_stack_motifs_do_not_mix_semantic_groups(tmp_path):
    from bom2kit.regular_stacks import make_flat_columns
    library,_,_=inputs(tmp_path)
    items={i['id']:i for i in library['items'][:2]};choices={};units=[]
    for iid,item in items.items():
        pose=stable_pose_options(item)[0];choices[iid]=(0,pose)
        for copy in range(2):
            units.append({'unit_id':f'{iid}#{copy+1}','item_id':iid,'cohesion_group':iid,
                          'dimensions':[v+2 for v in pose['dimensions_mm']]})
    columns,expanded=make_flat_columns(units,choices,items,1,200,max_overhang_fraction=0)
    assert len(columns)==2
    assert all(len({m['unit']['cohesion_group'] for m in group['members']})==1 for group in expanded.values())


def test_small_contact_cut_rejects_only_that_stack_not_the_valid_neighbors(tmp_path):
    from bom2kit.regular_stacks import make_flat_columns
    from bom2kit.practical_geometry import contact_certificate
    sources={};choices={};units=[]
    for iid,dims in [('wide',[20,20,5]),('thin',[30,2,5])]:
        mesh=trimesh.creation.box(dims);mesh.apply_translation(-mesh.bounds[0])
        path=tmp_path/(iid+'.json');path.write_text(json.dumps({'units':'mm','vertices_mm':mesh.vertices.tolist(),'triangles':mesh.faces.tolist()}))
        sources[iid]={'id':iid,'quantity':2,'mesh':{'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}}
        choices[iid]=(0,{'transform':np.eye(4).tolist(),'dimensions_mm':dims,'contact':contact_certificate(mesh)})
        units.extend({'item_id':iid,'unit_id':f'{iid}#{n+1}','cohesion_group':iid,'dimensions':[d+2 for d in dims]} for n in range(2))
    columns,expanded=make_flat_columns(units,choices,sources,1,30,max_overhang_fraction=0,minimum_sheet_side=10)
    assert len(columns)==3
    sheets=[sheet for group in expanded.values() for sheet in group['separators']]
    assert len(sheets)==1 and sheets[0]['lower_unit_id'].startswith('wide#')
    assert {m['unit']['unit_id'] for group in expanded.values() for m in group['members']}=={u['unit_id'] for u in units}


@pytest.mark.parametrize('style',['zones','cohesive'])
def test_complete_concept_replays_and_adapts_to_changed_bom(tmp_path,style):
    library, policy, bom = inputs(tmp_path)
    kwargs = dict(seconds=.5, beam_width=4, carton_counts=(2, 3), type_caps=(3,),
                  motif_modes=("rows",), max_replays=2, hand_border=9.,placement_style=style)
    run = design_concepts(library, policy, bom, **kwargs)
    assert run["status"] == "verified", run["trials"]
    assert all(r["practical"]["valid"] for r in run["results"])
    assert all(not r["concept"]["reference_used"] for r in run["results"])
    changed = deepcopy(library); changed["items"][0]["quantity"] = 3
    changed_bom = deepcopy(bom); changed_bom["components"][0]["quantity"] = 3
    rerun = design_concepts(changed, policy, changed_bom, **kwargs)
    assert rerun["status"] == "verified", rerun["trials"]
    for result in rerun["results"]:
        assert len(result["layout"]["placements"]) == 7
        assert sum(p["item_id"] == "servo-a" for p in result["layout"]["placements"]) == 3
