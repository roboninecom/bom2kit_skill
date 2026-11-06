from hashlib import sha256
import json

import numpy as np
import pytest

from bom2kit.cavity_groups import empty_windows, discover_cavities


def test_prefix_windows_match_actual_empty_volume():
    grid = np.ones((8,9,10),dtype=int)
    grid[2:6,3:8,1:7] = 0
    prefix = np.pad(grid,((1,0),)*3).cumsum(0).cumsum(1).cumsum(2)
    candidates = empty_windows(prefix,[3,4,5])
    assert candidates
    for x,y,z in candidates:
        assert not grid[x:x+3,y:y+4,z:z+5].any()
    assert empty_windows(prefix,[5,5,6]) == []
    assert empty_windows(prefix,[20,1,1]) == []


def test_cavity_discovery_certifies_original_sources_and_preserves_host_bounds(tmp_path):
    trimesh = pytest.importorskip("trimesh")
    pytest.importorskip("fcl")
    pytest.importorskip("scipy")
    meshes = [trimesh.creation.annulus(r_min=12,r_max=20,height=8,sections=32),
              trimesh.creation.box([6,6,4])]
    items = []
    for index,mesh in enumerate(meshes):
        path = tmp_path/f"shape-{index}.json"
        path.write_text(json.dumps({"units":"mm","vertices_mm":mesh.vertices.tolist(),"triangles":mesh.faces.tolist()}))
        items.append({"id":str(index),"quantity":1,"mesh":{"path":str(path),"sha256":sha256(path.read_bytes()).hexdigest()}})
    library = {"units":"mm","all_meshes_valid_volumes":True,"items":items}
    result = discover_cavities(library,tmp_path/"groups",clearance_mm=.2,pitch_mm=1,time_limit=10)
    assert result["alternatives"], result["attempts"]
    group = result["alternatives"][0]
    assert group["assembly"]["certificate"]["valid"]
    assert group["members"] == ["0","1"]
    assert group["group_box_volume_mm3"] < group["separate_box_volume_mm3"]
    assert all(item["quantity"] == 1 for item in items)
    # A cavity in a compound cannot reuse the only copy of its contained part.
    from bom2kit.nested_groups import extend_groups
    extension = extend_groups(library,result,tmp_path/"nested",time_limit=10,max_pairs=2,cavities=True)
    assert extension["alternatives"] == []
