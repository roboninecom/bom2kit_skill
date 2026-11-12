from copy import deepcopy
from hashlib import sha256
import json

import numpy as np
import pytest
import trimesh

from bom2kit.packing_states import declared_state, select_state
from bom2kit.practical_geometry import contact_certificate, stable_pose_options
from bom2kit.regular_patterns import floor_patterns
from bom2kit.practical_design import build_candidate, nondominated
from bom2kit.practical_validation import check_floor_support, check_hand_access
from bom2kit.carton_tiling import tile_modules


def source(tmp_path):
    mesh=trimesh.creation.box([10,20,30]);mesh.apply_translation(-mesh.bounds[0])
    path=tmp_path/'source.json'
    path.write_text(json.dumps({'units':'mm','vertices_mm':mesh.vertices.tolist(),'triangles':mesh.faces.tolist()}))
    return {'id':'part','quantity':2,'mesh':{'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}},mesh


def policy():
    return {'schema_version':1,'families':{'part':'print'},'allow_all_rotations':True,
            'max_inner_cartons':1,'max_carton_types':1,'item_padding_mm':1,'clearance_mm':.2,
            'carton':{'wall_mm':7,'protection_mm':15,'inner_wall_mm':1.5,'reserved_top_mm':.8,
                      'gap_mm':.2,'dimension_increment_mm':1}}


def candidate(tmp_path,gap=9,border=9):
    item,_=source(tmp_path);options={'part':stable_pose_options(item)}
    patterns=floor_patterns([item],options,1,1.5,gap=gap,hand_border=border,seconds=.2)
    modules=[{'family':'print','items':[item],**patterns}]
    tile=tile_modules(modules,time_limit=.1,max_types=1)['candidate']
    library={'units':'mm','all_meshes_valid_volumes':True,'items':[item]}
    return build_candidate(library,policy(),modules,tile)


def test_states_do_not_invent_factory_cartons_or_allow_unmeasured_replacements(tmp_path):
    item,_=source(tmp_path)
    item['packing_state']='Declared purchased-item envelope'
    assert declared_state(item)['kind']=='declared_envelope'
    alternate={**declared_state(item),'id':'bag','kind':'protective_packet'}
    with pytest.raises(ValueError,match='research-only'):select_state(item,alternate)
    selected=select_state(item,alternate,research=True)['selected_packing_state']
    assert selected['id']=='bag' and not selected['eligible_for_primary_comparison']
    disguised=deepcopy(alternate);disguised['id']='source'
    with pytest.raises(ValueError,match='Source state cannot'):select_state(item,disguised)
    alternate['contents_per_unit']={'part':0}
    with pytest.raises(ValueError,match='quantities'):select_state(item,alternate,research=True)


def test_primary_search_rejects_research_only_packing_state(tmp_path):
    from bom2kit.practical_design import design_practical
    item,_=source(tmp_path)
    alternate={**declared_state(item),'id':'experimental-bag','kind':'protective_packet',
               'measurement_status':'declared_estimate'}
    experimental=select_state(item,alternate,research=True)
    with pytest.raises(ValueError,match='Research-only packing states'):
        design_practical({'units':'mm','items':[experimental]},policy(),
                         {'components':[{'id':'part','quantity':2}]})


def test_stable_contact_uses_actual_floor_and_preserves_source(tmp_path):
    item,mesh=source(tmp_path);vertices=mesh.vertices.copy()
    options=stable_pose_options(item)
    assert options and all(p['contact']['valid'] for p in options)
    mesh.apply_translation([0,0,5])
    assert not contact_certificate(mesh)['valid']
    mesh.apply_translation([0,0,-5])
    np.testing.assert_allclose(mesh.vertices,vertices)
    # A point-balanced tetrahedron has a bounding footprint but no support area.
    tetra=trimesh.Trimesh([[0,0,0],[-2,-2,5],[2,-2,5],[0,2,5]],[[0,2,1],[0,3,2],[0,1,3],[1,2,3]])
    assert not contact_certificate(tetra)['valid']


def test_practical_result_replays_support_hand_access_and_original_bom(tmp_path):
    from bom2kit.assembly_plan import build_assembly_plan
    result=candidate(tmp_path)
    assert result['practical']['valid']
    plan=build_assembly_plan(result,{'components':[{'id':'part','quantity':2}]})
    assert not plan['templates']
    assert len(plan['cartons_in_outer_insertion_order'][0]['packing_sequence'])==2
    assert result['practical']['metrics']['compound_preassemblies']==0


def test_search_returns_replayed_plan_bound_to_final_result(tmp_path):
    from bom2kit.practical_design import design_practical
    from bom2kit.report import fingerprint
    item,_=source(tmp_path)
    run=design_practical({'units':'mm','items':[item]},policy(),
                         {'components':[{'id':'part','quantity':2}]},
                         time_limit=.3,carton_counts=(1,),type_caps=(1,),
                         hand_border=9,packing_gap=9,max_replays=1)
    assert run['status']=='verified'
    assert len(run['assembly_plans'])==len(run['results'])==1
    assert run['assembly_plans'][0]['result_fingerprint']==fingerprint(run['results'][0])
    assert not run['assembly_plans'][0]['templates']


def test_search_rejects_post_replay_geometry_mutation(tmp_path):
    from bom2kit.practical_design import design_practical
    item,_=source(tmp_path)
    def corrupt(result,record):
        result['layout']['placements'][0]['transform'][0][3]+=10
    with pytest.raises(ValueError,match='changed after independent assembly replay'):
        design_practical({'units':'mm','items':[item]},policy(),
                         {'components':[{'id':'part','quantity':2}]},
                         time_limit=.3,carton_counts=(1,),type_caps=(1,),
                         hand_border=9,packing_gap=9,max_replays=1,callback=corrupt)


def test_no_rigid_unrestrained_groups_or_false_liner_support(tmp_path):
    result=candidate(tmp_path)
    broken=deepcopy(result);broken['layout']['placements'][0]['transform'][2][3]+=1
    assert not check_floor_support(broken)['valid']
    broken=deepcopy(result);broken['groups']['assembly-slot-1#1']=['part#1','part#2']
    assert not check_floor_support(broken)['valid']
    broken=deepcopy(result);broken['practical']['floor_liners'][0]['dimensions_mm'][2]+=1
    assert not check_floor_support(broken)['valid']
    # A false positive result flag must not replace replay.
    broken=deepcopy(result);broken['practical']['hand_access']['parameters']['radius_mm']=100
    from bom2kit.assembly_plan import build_assembly_plan
    with pytest.raises(ValueError,match='fingertip'):build_assembly_plan(broken,{'components':[{'id':'part','quantity':2}]})


def test_hand_access_rejects_unreachable_tight_carton(tmp_path):
    result=candidate(tmp_path,gap=.2,border=0)
    assert not check_hand_access(result,radius_mm=8)['valid']


def test_access_failure_repacking_keeps_geometry_and_finger_model(tmp_path):
    from bom2kit.access_repair import repair
    item,_=source(tmp_path);options={'part':stable_pose_options(item)}
    patterns=floor_patterns([item],options,1,1.5,gap=.2,hand_border=0,seconds=.2)
    modules=[{'family':'print','items':[item],**patterns}]
    tile=tile_modules(modules,time_limit=.1,max_types=1)['candidate']
    library={'units':'mm','items':[item]}
    before=build_candidate(library,policy(),modules,tile)
    assert not before['practical']['hand_access']['valid']
    proposed,diagnostic=repair((tile['volume_mm3'],modules,tile,1),before,options,policy(),seconds=2)
    assert proposed and diagnostic['repacked_cartons']==['module-1']
    _,repaired_modules,repaired_tile,_=proposed
    after=build_candidate(library,policy(),repaired_modules,repaired_tile)
    assert after['practical']['valid']
    assert after['input']['items']==before['input']['items']
    assert after['practical']['hand_access']['parameters']==before['practical']['hand_access']['parameters']


def test_pareto_retains_simpler_larger_option():
    def r(volume,cartons,types):
        return {'practical':{'metrics':{'external_volume_l':volume,'cartons':cartons,'carton_types':types,
                                      'compound_preassemblies':0,'split_source_skus':0}}}
    compact,simple,bad=r(20,6,4),r(21,4,2),r(22,6,4)
    assert nondominated([compact,simple,bad])==[compact,simple]
    rotated=deepcopy(simple);rotated['practical']['metrics']['additional_sku_orientations']=2
    assert nondominated([rotated,simple])==[simple]


def test_common_floor_partial_allocation_preserves_every_copy(tmp_path):
    from bom2kit.common_floor import family_floors, quantize_heights
    item,_=source(tmp_path); item['quantity']=8
    options={'part':stable_pose_options(item)}
    candidates=family_floors([item],options,[27,47],policy(),maximum_cartons=3,
                             gap=0,border=0,access_lane=0,seconds=2)
    assert candidates
    best=min(candidates,key=lambda c:c[0])
    assert len(best[1])>=2
    ids=[p['unit_id'] for layer in best[1] for p in layer['placements']]
    assert len(ids)==len(set(ids))==8
    assert set(ids)=={f'part#{n}' for n in range(1,9)}
    assert all(layer['external_mm'][:2]==[27,47] for layer in best[1])
    # Upward rounding groups near heights; it never shrinks a source cavity.
    assert quantize_heights([10,11,40,42],2)==[11,11,42,42]
    assert quantize_heights([10,11,40,42],1)==[42]*4


def test_access_row_compaction_keeps_lanes_for_equal_height_neighbors():
    from bom2kit.regular_patterns import compact_access_rows
    units=[{'unit_id':str(i),'dimensions':[20,20,h]} for i,h in enumerate([10,30,30])]
    poses=[{'unit_id':str(i),'rotation':[0,1,2],'position_mm':[0,i*26.4,0]} for i in range(3)]
    compacted=compact_access_rows(poses,units,.2,6.4)
    assert compacted[1]['position_mm'][1]==pytest.approx(20.2)
    assert compacted[2]['position_mm'][1]==pytest.approx(46.6)
    assert poses[1]['position_mm'][1]==26.4


def test_actual_contact_can_support_a_small_bounded_overhang(tmp_path):
    from bom2kit.regular_stacks import make_flat_columns
    items={};choices={};units=[]
    for iid,size in [('base',[100,40,10]),('upper',[80,45,10])]:
        mesh=trimesh.creation.box(size);mesh.apply_translation(-mesh.bounds[0])
        path=tmp_path/(iid+'.json')
        path.write_text(json.dumps({'units':'mm','vertices_mm':mesh.vertices.tolist(),'triangles':mesh.faces.tolist()}))
        items[iid]={'id':iid,'quantity':1,'mesh':{'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}}
        choices[iid]=(0,{'transform':np.eye(4).tolist(),'dimensions_mm':size})
        units.append({'unit_id':iid+'#1','item_id':iid,'dimensions':[v+2 for v in size]})
    columns,expansions=make_flat_columns(units,choices,items,1,24)
    assert len(columns)==1
    assert columns[0]['dimensions']==[102,47,24]
    members=next(iter(expansions.values()))['members']
    assert members[0]['offset_mm']==[0,2.5,0]
    assert members[1]['offset_mm']==[10,0,12]
    # Disabling overhang reproduces the more restrictive proposal model.
    columns,_=make_flat_columns(units,choices,items,1,24,max_overhang_fraction=0)
    assert len(columns)==2


def test_cavity_pair_uses_real_internal_floor_and_individual_insertion(tmp_path):
    from bom2kit.assembly_plan import build_assembly_plan
    bottom=trimesh.creation.cylinder(radius=25,height=5,sections=32);bottom.apply_translation([25,25,2.5])
    wall=trimesh.creation.annulus(r_min=20,r_max=25,height=25,sections=32);wall.apply_translation([25,25,17.5])
    cup=trimesh.util.concatenate([bottom,wall])
    child=trimesh.creation.box([20,20,10]);child.apply_translation(-child.bounds[0])
    items=[];options={}
    for iid,mesh in [('cup',cup),('child',child)]:
        path=tmp_path/(iid+'.json')
        path.write_text(json.dumps({'units':'mm','vertices_mm':mesh.vertices.tolist(),'triangles':mesh.faces.tolist()}))
        items.append({'id':iid,'quantity':1,'mesh':{'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}})
        options[iid]=[{'dimensions_mm':mesh.extents.tolist(),'transform':np.eye(4).tolist(),'contact':{'center_margin_mm':10}}]
    p=policy();p['families']={'cup':'print','child':'print'}
    generated=floor_patterns(items,options,1,1.5,gap=.2,hand_border=9,seconds=2,supported_nesting=True)
    assert any(pattern['supported_pairs'] for pattern in generated['patterns'])
    modules=[{'family':'print','items':items,**generated}]
    tile=tile_modules(modules,time_limit=.1,max_types=1)['candidate']
    result=build_candidate({'units':'mm','all_meshes_valid_volumes':True,'items':items},p,modules,tile)
    assert result['practical']['valid']
    sheet=result['practical']['protective_separators'][0]
    assert sheet['dimensions_mm'][2]==pytest.approx(2.2)
    plan=build_assembly_plan(result,{'components':[{'id':i['id'],'quantity':1} for i in items]})
    assert not plan['templates']
    assert [s['unit_ids'] for s in plan['cartons_in_outer_insertion_order'][0]['packing_sequence']]==[['cup#1'],['child#1']]
    broken=deepcopy(result);broken['practical']['protective_separators'][0]['origin_mm'][2]+=1
    assert not check_floor_support(broken)['valid']


def test_surface_proposal_places_multiple_children_on_one_real_base(tmp_path):
    from bom2kit.source_surfaces import propose
    from bom2kit.assembly_plan import build_assembly_plan
    items=[];options={}
    for iid,size,quantity in [('base',[100,50,5],1),('child',[20,20,10],3)]:
        mesh=trimesh.creation.box(size);mesh.apply_translation(-mesh.bounds[0])
        path=tmp_path/(iid+'.json');path.write_text(json.dumps({'units':'mm','vertices_mm':mesh.vertices.tolist(),'triangles':mesh.faces.tolist()}))
        item={'id':iid,'quantity':quantity,'mesh':{'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}}
        items.append(item);options[iid]=stable_pose_options(item)
    proposal=propose(items,options,[125,75],1,1.5,border=9,seconds=3)
    assert proposal['status']=='complete_source_surface_proposal'
    assert proposal['supported_units']==3
    p=policy();p['families']={i['id']:'print' for i in items}
    modules=[{'family':'print','items':items,'patterns':[proposal['pattern']]}]
    tile=tile_modules(modules,time_limit=.1,max_types=1)['candidate']
    result=build_candidate({'units':'mm','all_meshes_valid_volumes':True,'items':items},p,modules,tile)
    assert result['practical']['valid']
    assert result['practical']['hand_access']['intermediate_load_states_checked']
    plan=build_assembly_plan(result,{'components':[{'id':i['id'],'quantity':i['quantity']} for i in items]})
    assert len(plan['cartons_in_outer_insertion_order'][0]['packing_sequence'])==4


def test_balanced_final_tree_can_still_have_no_stable_individual_order():
    from bom2kit.regular_stacks import removal_stability_checker
    stem=trimesh.creation.box([10,10,20]);stem.apply_translation([50,10,10])
    top=trimesh.creation.box([100,20,5]);top.apply_translation([50,10,22.5])
    base=trimesh.util.concatenate([stem,top]);meshes={'base':base};sheets=[]
    for uid,x in [('left',20),('right',80)]:
        mesh=trimesh.creation.box([40,20,20]);mesh.apply_translation([x,10,37.2]);meshes[uid]=mesh
        sheets.append({'lower_unit_id':'base','upper_unit_id':uid,'origin_mm':[x-20,0,25],
                       'support_surface':'actual_horizontal_face'})
    stable=removal_stability_checker(meshes,sheets,0)
    assert stable({'base','left','right'})
    assert not stable({'base','left'})
    assert not stable({'base','right'})
    assert stable({'base'})


def test_surface_queue_keeps_free_floor_extremes_after_many_placements(tmp_path):
    from bom2kit.source_surfaces import propose
    mesh=trimesh.creation.box([10,10,10]);mesh.apply_translation(-mesh.bounds[0])
    path=tmp_path/'cube.json'
    path.write_text(json.dumps({'units':'mm','vertices_mm':mesh.vertices.tolist(),'triangles':mesh.faces.tolist()}))
    item={'id':'cube','quantity':36,'mesh':{'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}}
    options={'cube':[{'transform':np.eye(4).tolist(),'dimensions_mm':[10,10,10],
                      'contact':contact_certificate(mesh)}]}
    proposal=propose([item],options,[90,90],1,1.5,border=0,seconds=10,max_height=12)
    assert proposal['status']=='complete_source_surface_proposal'
    assert proposal['placed']==36 and proposal['supported_units']==0
    assert len({p['unit_id'] for p in proposal['pattern']['placements']})==36


def test_planar_validator_rejects_overlaps_and_fake_projection(tmp_path):
    from shapely.geometry import mapping,box
    from bom2kit.planar_validation import validate_floor_footprints,check_projection_binding
    items=[{'id':'a','quantity':2,'dimensions_mm':[10,10,10],'footprint':mapping(box(0,0,10,10))}]
    poses=[{'item_id':'a','unit_id':'a#1','rotation':[0,1,2],'dimensions_mm':[10,10,10],'position_mm':[0,0,0]},
           {'item_id':'a','unit_id':'a#2','rotation':[0,1,2],'dimensions_mm':[10,10,10],'position_mm':[8,0,0]}]
    assert not validate_floor_footprints(items,poses,[30,30,20],.2)['valid']
    poses[1]['position_mm']=[11,0,0]
    assert validate_floor_footprints(items,poses,[30,30,20],.2)['valid']
    result=candidate(tmp_path)
    result['envelope_design']['candidate']['input']['planar_footprints']=True
    assert check_projection_binding(result)['valid']
    result['envelope_design']['candidate']['input']['items'][0]['footprint']=mapping(box(0,0,1,1))
    assert not check_projection_binding(result)['valid']


def test_real_exact_cover_worker_preserves_quantities():
    import os
    from pathlib import Path
    from bom2kit.practical_master import select_cartons
    python=os.environ.get('BOM2KIT_CPSAT_PYTHON')
    if not python or not Path(python).is_file():pytest.skip('Set BOM2KIT_CPSAT_PYTHON for isolated OR-Tools integration')
    candidates=[{'contents':contents,'external_mm':dims,'size_key':dims} for contents,dims in
                [({'a':2},[10,10,10]),({'b':1},[10,10,10]),({'a':2,'b':1},[30,30,30]),({'a':1},[3,3,3])]]
    result=select_cartons(candidates,{'a':2,'b':1},2,python=python,time_limit=.5)
    assert result['selected']==[0,1]


def test_real_irregular_solver_source_replay(tmp_path):
    import os
    from pathlib import Path
    from bom2kit.irregular_floor import propose
    solver=os.environ.get('BOM2KIT_IRREGULAR_SOLVER')
    if not solver or not Path(solver).is_file():pytest.skip('Set BOM2KIT_IRREGULAR_SOLVER for real polygon integration')
    item,_=source(tmp_path);options={'part':stable_pose_options(item)}
    seed=floor_patterns([item],options,1,1.5,seconds=.1,hand_border=9)['patterns'][0]
    proposal=propose([item],options,seed,1,1.5,executable=solver,time_limit=.5,gap=9,hand_border=9)
    assert proposal['status']=='validated_planar_proposal'
    modules=[{'family':'print','patterns':[proposal['pattern']]}]
    tile=tile_modules(modules,time_limit=.1,max_types=1)['candidate']
    result=build_candidate({'units':'mm','all_meshes_valid_volumes':True,'items':[item]},policy(),modules,tile)
    assert result['practical']['valid']


def test_irregular_backend_null_certificate_keeps_fallback_available(tmp_path,monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    from bom2kit import irregular_floor
    item,_=source(tmp_path);options={'part':stable_pose_options(item)}
    seed=floor_patterns([item],options,1,1.5,seconds=.1)['patterns'][0]
    def no_incumbent(arguments,**kwargs):
        Path(arguments[arguments.index('--certificate')+1]).write_text('null')
        return SimpleNamespace(returncode=0,stderr='')
    monkeypatch.setattr(irregular_floor.subprocess,'run',no_incumbent)
    proposed=irregular_floor.propose([item],options,seed,1,1.5,executable='test-solver')
    assert proposed['status']=='incomplete'
    assert proposed['reason']=='no_solution_certificate'
    assert 'pattern' not in proposed


def test_rejected_contour_proposal_does_not_displace_regular_fallback(tmp_path,monkeypatch):
    from bom2kit import irregular_floor
    from bom2kit.practical_design import design_practical
    item,_=source(tmp_path)
    def invalid_proposal(items,options,seed,*args,**kwargs):
        invalid=deepcopy(seed);invalid['external_mm']=[1,1,1];invalid['method']='invalid_test_proposal'
        return {'status':'validated_planar_proposal','pattern':invalid}
    monkeypatch.setattr(irregular_floor,'propose',invalid_proposal)
    run=design_practical({'units':'mm','items':[item]},policy(),{'components':[{'id':'part','quantity':2}]},
                         time_limit=1.,carton_counts=(1,),type_caps=(1,),max_replays=2,
                         hand_border=9,packing_gap=9,irregular_executable='test-solver',irregular_budget=.2)
    assert run['status']=='verified'
    assert run['replays'][0]['status']=='rejected'
    assert run['replays'][1]['status']=='verified'
    assert run['results'][0]['practical']['valid']


def test_repeated_kit_partitions_preserve_original_unit_ids(tmp_path):
    from bom2kit.regular_patterns import partition_by_height
    item,_=source(tmp_path);second={**item,'id':'other'}
    options={'part':stable_pose_options(item),'other':stable_pose_options(second)}
    groups=partition_by_height([item,second],options,2,'copies')
    ids=[]
    for group in groups:
        patterns=floor_patterns(group,options,1,1.5,seconds=.1)
        ids.extend(p['unit_id'] for p in patterns['patterns'][0]['placements'])
    assert sorted(ids)==['other#1','other#2','part#1','part#2']
    assert [{i['id']:i['quantity'] for i in group} for group in groups]==[{'other':1,'part':1}]*2


def test_real_stacks_require_flat_faces_counted_sheets_and_individual_steps(tmp_path):
    from bom2kit.assembly_plan import build_assembly_plan
    from bom2kit.regular_stacks import interface_certificate
    item,mesh=source(tmp_path)
    options={'part':stable_pose_options(item)}
    patterns=floor_patterns([item],options,1,1.5,gap=9,hand_border=9,seconds=.3,stack_height_factor=2)
    patterns['patterns']=[p for p in patterns['patterns'] if p['protective_separators']]
    assert patterns['patterns']
    modules=[{'family':'print','items':[item],**patterns}]
    tile=tile_modules(modules,time_limit=.1,max_types=1)['candidate']
    result=build_candidate({'units':'mm','all_meshes_valid_volumes':True,'items':[item]},policy(),modules,tile)
    assert result['practical']['valid']
    plan=build_assembly_plan(result,{'components':[{'id':'part','quantity':2}]})
    steps=plan['cartons_in_outer_insertion_order'][0]['operator_steps']
    assert [s['action'] for s in steps]==['place_source_unit','place_protective_contact_sheet','place_source_unit']
    broken=deepcopy(result);broken['practical']['protective_separators']=[]
    assert not check_floor_support(broken)['valid']
    broken=deepcopy(result);broken['practical']['protective_separators'][0]['dimensions_mm'][2]=.1
    assert not check_floor_support(broken)['valid']
    broken=deepcopy(result);broken['input']['items'][0]['packing_state']='Declared purchased-item envelope'
    assert not check_floor_support(broken)['valid']
    # A pointed top with the same bounding rectangle is not a flat support face.
    cone=trimesh.creation.cone(radius=8,height=30);upper=mesh.copy();upper.apply_translation([0,0,32])
    assert not interface_certificate(cone,upper,2)['valid']


def test_adjacent_floor_pairs_replay_source_clearance_not_overlapping_bounds(tmp_path):
    from bom2kit.practical_geometry import contact_certificate
    from bom2kit.source_floor_validation import validate_source_floor
    a=trimesh.creation.box([20,4,10]);a.apply_translation([10,2,5])
    b=trimesh.creation.box([4,16,10]);b.apply_translation([2,12,5])
    mesh=trimesh.util.concatenate([a,b]);path=tmp_path/'angle.json'
    path.write_text(json.dumps({'units':'mm','vertices_mm':mesh.vertices.tolist(),'triangles':mesh.faces.tolist()}))
    item={'id':'part','quantity':2,'mesh':{'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}}
    options={'part':[{'transform':np.eye(4).tolist(),'dimensions_mm':[20,20,10],'contact':contact_certificate(mesh)}]}
    patterns=floor_patterns([item],options,1,1.5,gap=.2,hand_border=9,seconds=1,floor_pair_budget=2)
    patterns['patterns']=[p for p in patterns['patterns'] if p.get('source_clearance_slots')]
    assert patterns['patterns']
    modules=[{'family':'print','items':[item],**patterns}]
    tiled=tile_modules(modules,time_limit=.1,max_types=1)['candidate']
    result=build_candidate({'units':'mm','items':[item]},policy(),modules,tiled)
    assert result['practical']['support']['valid']
    assert all(len(members)==1 for members in result['groups'].values())
    broken=deepcopy(result)
    broken['envelope_design']['candidate']['input']['items'][0]['source_transform'][0][3]+=1
    assert not check_floor_support(broken)['valid']
    broken['envelope_design']['candidate']['input']['source_clearance_slots']=False
    assert not check_floor_support(broken)['valid']
    broken=deepcopy(result);broken['envelope_design']['candidate']['input']['source_padding_mm']=.1
    assert not check_floor_support(broken)['valid']


def test_real_rectangle_backend_preserves_original_practical_layout(tmp_path):
    import os
    from pathlib import Path
    solver=os.environ.get('BOM2KIT_RECTANGLE_SOLVER')
    if not solver or not Path(solver).is_file():pytest.skip('Set BOM2KIT_RECTANGLE_SOLVER for real rectangle integration')
    item,_=source(tmp_path);options={'part':stable_pose_options(item)}
    patterns=floor_patterns([item],options,1,1.5,gap=9,hand_border=9,seconds=.2,
                            rectangle_executable=solver,rectangle_budget=.4)
    assert any(d['status']=='validated_envelopes' for d in patterns['rectangle_diagnostics'])
    modules=[{'family':'print','items':[item],**patterns}]
    tiled=tile_modules(modules,time_limit=.1,max_types=1)['candidate']
    result=build_candidate({'units':'mm','items':[item]},policy(),modules,tiled)
    assert result['practical']['valid']


def test_height_cost_partition_separates_flat_wide_from_tall_narrow_parts():
    from bom2kit.regular_patterns import partition_by_height
    items=[{'id':iid,'quantity':1} for iid in ('plate-a','plate-b','tall-a','tall-b')]
    options={i['id']:[{'dimensions_mm':[100,100,5] if i['id'].startswith('plate') else [10,10,80]}] for i in items}
    groups=partition_by_height(items,options,2,'cost')
    assert [{i['id'] for i in group} for group in groups]==[{'plate-a','plate-b'},{'tall-a','tall-b'}]


def test_footprint_cost_can_join_a_plate_with_tall_parts_in_another_stable_pose():
    from bom2kit.regular_patterns import partition_by_height
    items=[{'id':iid,'quantity':1} for iid in ('plate','cube','bar')]
    options={'plate':[{'dimensions_mm':[100,100,5]},{'dimensions_mm':[5,100,100]}],
             'cube':[{'dimensions_mm':[20,20,20]}],'bar':[{'dimensions_mm':[5,5,100]}]}
    low=partition_by_height(items,options,2,'cost')
    narrow=partition_by_height(items,options,2,'footprint_cost')
    assert [{i['id'] for i in group} for group in low]==[{'plate'},{'cube','bar'}]
    assert [{i['id'] for i in group} for group in narrow]==[{'cube'},{'plate','bar'}]


def test_directional_access_lane_preserves_source_dimensions_and_hand_access(tmp_path):
    item,_=source(tmp_path);item['quantity']=6
    options={'part':stable_pose_options(item)}
    patterns=floor_patterns([item],options,1,1.5,gap=.2,hand_border=9,access_lane_mm=6.4,seconds=.3)
    modules=[{'family':'print','items':[item],**patterns}]
    tiled=tile_modules(modules,time_limit=.1,max_types=1)['candidate']
    result=build_candidate({'units':'mm','items':[item]},policy(),modules,tiled)
    assert result['practical']['valid']
    assert len(result['layout']['placements'])==6
    for slot in result['envelope_design']['candidate']['layout']['placements']:
        assert sorted(round(v,6) for v in slot['dimensions_mm'])==[12,22,32]
