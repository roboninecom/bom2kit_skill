"""Choose geometry-derived envelope frames without worsening the existing axes."""


def packing_bounds(mesh):
    """Compare approximate oriented bounds with the mesh's own axis-aligned box.

    Search-generated compounds already carry a useful intrinsic packing frame.
    Adding a part entirely inside their bounds must not force a worse approximate
    OBB simply because its convex hull changed. No external frame is accepted.
    """
    import numpy as np
    import trimesh

    frame, _ = trimesh.bounds.oriented_bounds(mesh)
    extents = np.ptp(trimesh.transform_points(mesh.vertices,frame),axis=0)
    existing = mesh.extents
    if float(np.prod(existing)) <= float(np.prod(extents))*(1+1e-10):
        return np.eye(4), existing.copy()
    return frame, extents
