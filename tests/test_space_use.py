import pytest
from bom2kit.space_use import clipped_box_union_volume


def test_union_clips_carton_walls_and_does_not_double_count_nested_sources():
    boxes=[[[0,0,0],[10,10,10]],[[5,0,0],[15,10,10]],[[2,2,2],[4,4,4]]]
    assert clipped_box_union_volume(boxes,[0,0,0],[12,10,10])==1200
    assert clipped_box_union_volume(boxes,[0,0,0],[20,20,20])==1500
    assert clipped_box_union_volume([], [0,0,0],[20,20,20])==0
    with pytest.raises(ValueError):
        clipped_box_union_volume([[[1,0,0],[0,2,2]]],[0,0,0],[10,10,10])
