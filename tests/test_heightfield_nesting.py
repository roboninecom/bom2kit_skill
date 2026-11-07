import numpy as np
import pytest

from bom2kit.heightfield_nesting import insertion_heights


@pytest.mark.parametrize("shape",[(2,3),(3,2),(3,3),(4,4)])
def test_insertion_field_matches_direct_column_sweep(shape):
    rng=np.random.default_rng(7);top=rng.integers(0,20,size=(8,9)).astype(float)
    bottom=rng.integers(0,8,size=shape).astype(float);mask=rng.random(shape)>.3;mask[0,0]=True
    actual=insertion_heights(top,bottom,mask)
    for x in range(actual.shape[0]):
        for y in range(actual.shape[1]):
            expected=max(0,(top[x:x+shape[0],y:y+shape[1]]-bottom)[mask].max())
            assert actual[x,y]==expected


def test_whole_family_nesting_preserves_source_geometry_and_insertion(tmp_path):
    import json
    from hashlib import sha256
    trimesh=pytest.importorskip("trimesh");pytest.importorskip("fcl")
    from bom2kit.heightfield_nesting import prepare_shapes,pack_heightfield
    from bom2kit.mesh_validation import validate_mesh_layout
    from bom2kit.mesh_motion import check_vertical_sequence
    items=[]
    for iid,quantity,mesh in (("ring",1,trimesh.creation.annulus(r_min=13,r_max=15,height=6,sections=32)),
                              ("block",3,trimesh.creation.box([8,8,4]))):
        path=tmp_path/(iid+".json")
        path.write_text(json.dumps({"units":"mm","vertices_mm":mesh.vertices.tolist(),"triangles":mesh.faces.tolist()}))
        items.append({"id":iid,"quantity":quantity,"mesh":{"path":str(path),"sha256":sha256(path.read_bytes()).hexdigest()}})
    shapes=prepare_shapes(items,1)
    proposal=pack_heightfield(items,shapes,33,33,pitch=1,clearance=.2,time_limit=20)
    assert proposal and len(proposal["layout"]["placements"])==4
    problem={"units":"mm","items":items,"container":{"inner_mm":proposal["container_mm"]},"clearance_mm":.2}
    assert validate_mesh_layout(problem,proposal["layout"])["valid"]
    assert check_vertical_sequence(problem,proposal["layout"],time_limit=15)["valid"]
    assert np.prod(proposal["bounds_mm"])<sum(shapes[i["id"]]["box_volume"]*i["quantity"] for i in items)
