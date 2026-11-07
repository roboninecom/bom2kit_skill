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
