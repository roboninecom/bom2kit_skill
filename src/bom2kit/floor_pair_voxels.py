"""FFT proposals for same-floor interlocking; original triangles decide fit."""
from functools import lru_cache
from itertools import product


@lru_cache(maxsize=128)
def _grid(source_key,pitch):
    from .regular_floor_pairs import _source_pose
    voxel=_source_pose(*source_key).voxelized(pitch).fill()
    return voxel.matrix,voxel.transform[:3,3]


def floor_offsets(first_key,second_key,yaw,angle,a_extents,b_extents,padding,*,pitch=3.,limit=32):
    """Correlate occupied Z columns to rank XY shifts without assuming a rigid pair.

    The coarse dilated voxel field is a proposal filter only. It can miss a valid
    narrow gap; no zero-correlation cell is itself a clearance certificate.
    """
    import numpy as np
    import trimesh
    from scipy.ndimage import binary_dilation
    from scipy.fft import rfft2,irfft2,next_fast_len
    ga,oa=_grid(first_key,pitch);gb,ob=_grid(second_key,pitch)
    # Padding the proposal obstacle avoids spending every exact check on nearly
    # touching triangles. Final clearance is still 2*padding + policy gap.
    ga=binary_dilation(np.pad(ga,1));oa=oa-pitch
    corners=np.array(list(product(*[(ob[k],ob[k]+(gb.shape[k]-1)*pitch) for k in range(3)])))
    rotated_origin=trimesh.transform_points(corners,yaw).min(axis=0)
    gb=np.rot90(gb,k=angle//90,axes=(0,1));ob=rotated_origin
    zmin=min(oa[2],ob[2]);az=int(round((oa[2]-zmin)/pitch));bz=int(round((ob[2]-zmin)/pitch))
    nz=max(az+ga.shape[2],bz+gb.shape[2])
    a=np.zeros((*ga.shape[:2],nz),dtype=np.float32);b=np.zeros((*gb.shape[:2],nz),dtype=np.float32)
    a[:,:,az:az+ga.shape[2]]=ga;b[:,:,bz:bz+gb.shape[2]]=gb
    size=tuple(next_fast_len(a.shape[k]+b.shape[k]-1) for k in (0,1))
    correlation=irfft2((rfft2(a,s=size,axes=(0,1))*rfft2(b[::-1,::-1,:],s=size,axes=(0,1))).sum(axis=2),s=size)
    cells=np.argwhere(correlation<.5)
    offsets=(cells-np.array(gb.shape[:2])+1)*pitch+oa[:2]-ob[:2]
    span=max(a_extents[1],b_extents[1])
    offsets=offsets[(offsets[:,0]>=-1e-7)&(offsets[:,0]<=a_extents[0]+2*padding+pitch)&
                    (np.abs(offsets[:,1])<=span+pitch)]
    if not len(offsets):return []
    lower=np.minimum(0.,offsets);upper=np.maximum(np.asarray(a_extents[:2]),offsets+np.asarray(b_extents[:2]))
    areas=np.prod(upper-lower+2*padding,axis=1)
    order=np.argsort(areas,kind='stable')[:limit]
    return [tuple(map(float,offsets[i])) for i in order]
