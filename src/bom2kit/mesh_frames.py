"""Choose geometry-derived envelope frames without worsening the existing axes."""
from collections import OrderedDict
from hashlib import sha256

_BOUND_CACHE = OrderedDict()


def packing_bounds(mesh):
    """Compare approximate oriented bounds with the mesh's own axis-aligned box.

    Search-generated compounds already carry a useful intrinsic packing frame.
    Adding a part entirely inside their bounds must not force a worse approximate
    OBB simply because its convex hull changed. No external frame is accepted.
    """
    import numpy as np
    import trimesh

    key=sha256(mesh.vertices.tobytes()+mesh.faces.tobytes()).digest()
    if key in _BOUND_CACHE:
        frame,extents=_BOUND_CACHE[key];_BOUND_CACHE.move_to_end(key)
        return frame.copy(),extents.copy()
    existing = mesh.extents
    # A solid axis-aligned box already reaches the material-volume lower bound.
    if np.isclose(float(np.prod(existing)),mesh.volume,rtol=1e-10,atol=1e-8):
        frame,extents=np.eye(4),existing.copy()
    else:
        frame, _ = trimesh.bounds.oriented_bounds(mesh)
        extents = np.ptp(trimesh.transform_points(mesh.vertices,frame),axis=0)
        if float(np.prod(existing)) <= float(np.prod(extents))*(1+1e-10):
            frame,extents=np.eye(4),existing.copy()
    _BOUND_CACHE[key]=(frame.copy(),extents.copy())
    if len(_BOUND_CACHE)>256:_BOUND_CACHE.popitem(last=False)
    return frame,extents
