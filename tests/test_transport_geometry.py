from copy import deepcopy
from hashlib import sha256
import json
import math
import pytest

from bom2kit.carton_tiling import tile_modules
from bom2kit.protection_geometry import foam_panels, validate_foam_shell
from bom2kit.report import fingerprint
from bom2kit.transport_validation import validate_transport


def test_expanded_cartons_tile_without_filler():
    modules=[{"patterns":[{"external_mm":s}]} for s in ([100,80,40],[60,90,30],[80,55,60])]
    result=tile_modules(modules,time_limit=2,max_types=3)["candidate"]
    assert result
    assert math.prod(result["block_mm"]) == sum(math.prod(l["external_mm"]) for l in result["leaves"])
    for leaf in result["leaves"]:
        minimum=modules[leaf["module"]]["patterns"][0]["external_mm"]
        assert all(a>=b for a,b in zip(leaf["external_mm"],minimum))


def test_foam_shell_rejects_missing_overlap_and_intrusion():
    inner=[239,239,291];panels=foam_panels(inner,15)
    assert validate_foam_shell(inner,15,panels)["valid"]
    assert not validate_foam_shell(inner,15,panels[:-1])["valid"]
    wrong=deepcopy(panels);wrong[1]["origin_mm"]=[0,0,0]
    assert not validate_foam_shell(inner,15,wrong)["valid"]
    wrong=deepcopy(panels);wrong[0]["dimensions_mm"][2]+=1
    assert not validate_foam_shell(inner,15,wrong)["valid"]
    wrong=deepcopy(panels);wrong[0]["quantity"]=0;wrong[1]["quantity"]=2
    assert not validate_foam_shell(inner,15,wrong)["valid"]


def fixture():
    policy={"families":{"printed":"print","clamp":"metal"},"max_inner_cartons":2,"max_carton_types":1,
            "carton":{"protection_mm":15}}
    modules=[{"id":"A","family":"print","external_mm":[50,40,30],"position_mm":[15,15,15],"unit_ids":["printed#1"]},
             {"id":"B","family":"metal","external_mm":[50,40,30],"position_mm":[65,15,15],"unit_ids":["clamp#1"]}]
    layers=[{"id":m["id"],"wall_mm":1.5,"inner_mm":[v-3 for v in m["external_mm"]],"position_mm":m["position_mm"]} for m in modules]
    placements=[{"unit_id":"printed#1","item_id":"printed","layer_id":"A"},
                {"unit_id":"clamp#1","item_id":"clamp","layer_id":"B"}]
    result={"input":{"items":[{"id":"printed"},{"id":"clamp"}],"container":{"inner_mm":[130,70,60]}},
            "layout":{"placements":placements},"envelope_design":{"candidate":{"layout":{"layers":layers,"placements":placements}}},
            "logistics":{"policy":deepcopy(policy),"policy_hash":fingerprint(policy),"spacers":[],"modules":modules,
                         "block_mm":[100,40,30],"foam_panels":foam_panels([130,70,60],15)}}
    return result,policy


def test_policy_validator_rejects_mixing_spacers_and_false_shipping_claim():
    result,policy=fixture()
    assert validate_transport(result,policy)["valid"]
    mixed=deepcopy(result);mixed["logistics"]["modules"][0]["unit_ids"].append("clamp#1")
    assert not validate_transport(mixed,policy)["valid"]
    spacer=deepcopy(result);spacer["logistics"]["spacers"]=[{"id":"filler"}]
    assert not validate_transport(spacer,policy)["valid"]
    false=deepcopy(result);false["logistics"]["physical_qualification"]=True
    assert not validate_transport(false,policy)["valid"]
    changed=deepcopy(policy);changed["families"]["clamp"]="print"
    assert not validate_transport(result,changed)["valid"]


def test_policy_validator_rejects_voids_and_type_cap_changes():
    result,policy=fixture()
    void=deepcopy(result);void["logistics"]["block_mm"][0]+=10
    assert not validate_transport(void,policy)["valid"]
    cap=deepcopy(policy);cap["max_inner_cartons"]=1
    result["logistics"]["policy"]=cap;result["logistics"]["policy_hash"]=fingerprint(cap)
    assert not validate_transport(result,cap)["valid"]


def test_design_replays_original_geometry_bom_and_fingerprint(tmp_path):
    trimesh=pytest.importorskip("trimesh")
    pytest.importorskip("fcl")
    from bom2kit.logistics_design import design_logistics
    mesh=trimesh.creation.box([8,12,16]);path=tmp_path/"part.json"
    path.write_text(json.dumps({"units":"mm","vertices_mm":mesh.vertices.tolist(),"triangles":mesh.faces.tolist()}))
    ref={"path":str(path),"sha256":sha256(path.read_bytes()).hexdigest()}
    library={"units":"mm","all_meshes_valid_volumes":True,"items":[
        {"id":"printed","quantity":2,"mesh":ref},{"id":"metal","quantity":1,"mesh":ref}]}
    policy={"schema_version":1,"families":{"printed":"printed","metal":"mechanics"},
            "item_padding_mm":1,"clearance_mm":.2,"allow_all_rotations":True,
            "max_inner_cartons":2,"max_carton_types":2,
            "carton":{"wall_mm":7,"protection_mm":15,"inner_wall_mm":1.5,"reserved_top_mm":.8,
                      "gap_mm":.2,"dimension_increment_mm":1}}
    bom={"components":[{"id":i["id"],"quantity":i["quantity"]} for i in library["items"]]}
    result,plan=design_logistics(library,policy,bom,time_limit=3,shared_footprint_seconds=.5)
    assert result["validation"]["valid"] and result["logistics"]["validation"]["valid"]
    assert plan["result_fingerprint"]==fingerprint(result)
    assert sorted(len(m["unit_ids"]) for m in result["logistics"]["modules"])==[1,2]
    assert not result["logistics"]["retention_verified"]
    assert result["search"]["shared_footprints"]["attempts"]>0
    from bom2kit.logistics_design import NonImprovingProposal
    with pytest.raises(NonImprovingProposal):
        design_logistics(library,policy,bom,time_limit=2,_incumbent_volume=1)
    split_policy={**policy,"max_inner_cartons":3,"max_carton_types":3}
    split,split_plan=design_logistics(library,split_policy,bom,time_limit=3,largest_family_cartons=3,partition_strategy="packing")
    assert split["logistics"]["carton_count"]==3
    assert split["logistics"]["validation"]["valid"]
    assert split_plan["result_fingerprint"]==fingerprint(split)
    assert split["search"]["family_partition"]["attempts"]>0
    balanced,_=design_logistics(library,split_policy,bom,time_limit=2,balanced_cartons=3,partition_strategy="packing")
    assert balanced["logistics"]["validation"]["valid"]
    assert balanced["search"]["family_partition"]["allocation"]=={"printed":2,"mechanics":1}
    wrong=deepcopy(bom);wrong["components"][0]["quantity"]+=1
    with pytest.raises(ValueError,match="BOM"):
        design_logistics(library,policy,wrong,time_limit=3)
    mixed=deepcopy(policy);del mixed["families"]["metal"]
    with pytest.raises(ValueError,match="classify"):
        design_logistics(library,mixed,bom,time_limit=3)
    with pytest.raises(ValueError,match="source or policy mismatch"):
        design_logistics(library,policy,bom,time_limit=3,
                         _prepared_nesting={"source_library_fingerprint":"other-source","policy_fingerprint":fingerprint(policy)})


def test_columns_preserve_quantity_orientation_and_full_envelope_support():
    from bom2kit.column_packing import make_columns,expand_columns
    from bom2kit.strip_packing import pack_strip
    from bom2kit.validation import validate
    units=[{"item_id":"factory-box","unit_id":f"factory-box#{i}","dimensions":[10,20,30],
            "orientations":[((0,1,2),(10,20,30))]} for i in range(1,5)]
    columns,expansion=make_columns(units,60)
    assert len(columns)==2
    assert all(c["orientations"]==[((0,1,2),(10,20,60))] for c in columns)
    packed=pack_strip(columns,21,60,.2)
    expanded=expand_columns(packed,expansion)
    problem={"container":{"inner_mm":[21,41,60]},"gap_mm":.2,
             "items":[{"id":"factory-box","quantity":4,"dimensions_mm":[10,20,30],"allowed_rotations":"fixed"}]}
    assert validate(problem,expanded)["valid"]
    floating=deepcopy(expanded);floating["placements"][-1]["position_mm"][2]-=1
    assert not validate(problem,floating)["valid"]


def test_mixed_columns_have_supported_original_slots():
    from bom2kit.column_packing import make_mixed_columns,expand_columns
    from bom2kit.strip_packing import pack_strip
    from bom2kit.validation import validate
    units=[{"item_id":iid,"unit_id":iid+"#1","dimensions":size,"orientations":[((0,1,2),tuple(size))]}
           for iid,size in (("large",[30,20,10]),("small",[15,10,5]))]
    columns,expansion=make_mixed_columns(units,15)
    assert len(columns)==1
    p=pack_strip(columns,30,15,.2)
    expanded=expand_columns(p,expansion)
    problem={"container":{"inner_mm":[30,20,15]},"gap_mm":.2,
             "items":[{"id":u["item_id"],"quantity":1,"dimensions_mm":u["dimensions"],"allowed_rotations":"fixed"} for u in units]}
    assert validate(problem,expanded)["valid"]
    expanded["placements"][-1]["position_mm"][0]=16
    assert not validate(problem,expanded)["valid"]


def test_supported_surface_places_two_units_on_one_base():
    from bom2kit.supported_packing import pack_supported
    from bom2kit.validation import validate
    specs=[("base","base#1",[40,20,10]),("small","small#1",[19.8,20,10]),("small","small#2",[19.8,20,10])]
    units=[{"item_id":iid,"unit_id":uid,"dimensions":size,"orientations":[((0,1,2),tuple(size))]} for iid,uid,size in specs]
    packed=pack_supported(units,40,20,20,.2)
    assert packed
    assert [p["position_mm"][2] for p in packed["placements"]]==[0,10,10]
    problem={"container":{"inner_mm":[40,20,20]},"gap_mm":.2,"items":[
        {"id":"base","quantity":1,"dimensions_mm":[40,20,10],"allowed_rotations":"fixed"},
        {"id":"small","quantity":2,"dimensions_mm":[19.8,20,10],"allowed_rotations":"fixed"}]}
    assert validate(problem,packed)["valid"]


def test_single_size_carton_grid_preserves_all_module_membership():
    from bom2kit.carton_tiling import tile_modules,carton_size_key
    modules=[{"patterns":[{"external_mm":size,"placements":[]}]} for size in
             ([10,20,30],[11,19,29],[9,21,28],[12,18,27],[8,22,26],[13,17,25])]
    result=tile_modules(modules,time_limit=.01,max_types=1)
    candidate=result["candidate"]
    assert candidate and candidate["distinct_carton_sizes"]==1
    assert sorted(leaf["module"] for leaf in candidate["leaves"])==list(range(6))
    assert len({carton_size_key(l["external_mm"]) for l in candidate["leaves"]})==1
    assert sum(math.prod(l["external_mm"]) for l in candidate["leaves"])==math.prod(candidate["block_mm"])


def test_supported_order_search_improves_height_without_relaxing_support():
    from itertools import permutations
    from bom2kit.supported_packing import pack_supported,optimize_supported
    from bom2kit.validation import validate
    sizes=[[11,12,9],[11,11,7],[13,7,4],[12,11,8],[13,6,3],[11,8,4],[5,12,9]]
    units=[{"item_id":str(i),"unit_id":f"{i}#1","dimensions":s,
            "orientations":[(r,tuple(s[k] for k in r)) for r in permutations(range(3))]} for i,s in enumerate(sizes)]
    baseline=pack_supported(units,25,25,50,.2)
    result=optimize_supported(units,25,25,50,.2,time_limit=10,max_iterations=64)
    assert result["packing"]["usable_mm"][2]<baseline["usable_mm"][2]
    problem={"container":{"inner_mm":[25,25,50]},"gap_mm":.2,"items":[
        {"id":str(i),"quantity":1,"dimensions_mm":s,"allowed_rotations":[list(r) for r in permutations(range(3))]} for i,s in enumerate(sizes)]}
    assert validate(problem,result["packing"])["valid"]
