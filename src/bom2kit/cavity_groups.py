"""Propose dense parts inside actual voxel voids, then verify original meshes."""
from collections import Counter
from hashlib import sha256
from itertools import permutations
import json
import math
from pathlib import Path
from .mesh_frames import packing_bounds
from time import perf_counter


def empty_windows(prefix, size, limit=6):
    """Find empty axis-aligned windows using a padded 3D occupancy prefix sum."""
    import numpy as np
    if type(limit) is not int or limit < 1:
        raise ValueError("Positive integer candidate limit required")
    size = tuple(int(v) for v in size)
    if len(size) != 3 or min(size) < 1:
        raise ValueError("Three positive window sizes required")
    if any(n >= bound for n,bound in zip(size,prefix.shape)):
        return []
    x,y,z = size
    sums = (prefix[x:,y:,z:] - prefix[:-x,y:,z:] - prefix[x:,:-y,z:] - prefix[x:,y:,:-z]
            + prefix[:-x,:-y,z:] + prefix[:-x,y:,:-z] + prefix[x:,:-y,:-z] - prefix[:-x,:-y,:-z])
    locations = np.argwhere(sums == 0)
    if not len(locations):
        return []
    # Keep separated alternatives rather than many adjacent points in one void.
    selected = [locations[0]]
    while len(selected) < min(limit,len(locations)):
        distances = np.min([np.sum((locations-p)**2,axis=1) for p in selected],axis=0)
        selected.append(locations[int(np.argmax(distances))])
    return [p.tolist() for p in selected]


def discover_cavities(library, output, clearance_mm=2, pitch_mm=2, time_limit=120, max_groups=12,
                      host_item_ids=None, dense_item_ids=None, source_quantities=None):
    """Generate assembly-checked pair alternatives without enlarging host bounds.

    Voxel voids only nominate poses. Exact source triangles and workbench paths
    decide acceptance. This is a bounded dense-in-hollow strategy, not exhaustive
    arbitrary-shape nesting or a claim of physical support inside a cavity.
    """
    import numpy as np
    import trimesh
    from scipy.ndimage import binary_dilation
    from .mesh_groups import check_workbench_axes
    from .mesh_validation import validate_mesh_layout
    from .models import number

    started = perf_counter()
    pitch_mm = number(pitch_mm,"pitch_mm",True)
    clearance_mm = number(clearance_mm,"clearance_mm",True)
    time_limit = number(time_limit,"time_limit",True)
    if type(max_groups) is not int or max_groups < 1:
        raise ValueError("max_groups must be a positive integer")
    if library.get("units") != "mm" or not library.get("all_meshes_valid_volumes"):
        raise ValueError("Verified millimetre source library required")
    ids = [i["id"] for i in library["items"]]
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids)) != len(ids) or not ids:
        raise ValueError("Unique nonempty source identities required")
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    prepared = []
    for item in library["items"]:
        if type(item["quantity"]) is not int or item["quantity"] < 1:
            raise ValueError("Positive integer quantities required")
        raw = Path(item["mesh"]["path"]).read_bytes()
        if sha256(raw).hexdigest() != item["mesh"]["sha256"]:
            raise ValueError("Source hash mismatch")
        data = json.loads(raw)
        if data.get("units") != "mm":
            raise ValueError("Source units must be mm")
        mesh = trimesh.Trimesh(data["vertices_mm"],data["triangles"],process=False)
        if not mesh.is_volume or np.any(mesh.area_faces <= 0):
            raise ValueError("Invalid source mesh")
        frame,_ = packing_bounds(mesh)
        mesh.apply_transform(frame)
        shift = -mesh.bounds[0]
        mesh.apply_translation(shift)
        frame[:3,3] += shift
        box = float(np.prod(mesh.extents))
        prepared.append({"item":item,"mesh":mesh,"frame":frame,"box":box,"occupancy":float(mesh.volume/box)})
    hosts = sorted((p for p in prepared if p["occupancy"] < .75 and
                    (host_item_ids is None or p["item"]["id"] in host_item_ids)),key=lambda p:-p["box"]*(1-p["occupancy"]))
    dense = sorted((p for p in prepared if p["occupancy"] >= .8 and
                    (dense_item_ids is None or p["item"]["id"] in dense_item_ids)),key=lambda p:-p["box"])
    attempts, alternatives = [], []
    per_host_limit = max(1,math.ceil(max_groups/max(1,len(hosts))))
    radius = int(np.ceil(clearance_mm/pitch_mm))
    coordinates = np.indices((2*radius+1,)*3)-radius
    sphere = np.sum(coordinates**2,axis=0) <= radius**2
    for host in hosts:
        if perf_counter()-started >= time_limit or len(alternatives) >= max_groups:
            break
        voxel = host["mesh"].voxelized(pitch_mm).fill()
        grid = binary_dilation(voxel.matrix,structure=sphere)
        prefix = np.pad(grid.astype(np.int32),((1,0),)*3).cumsum(0).cumsum(1).cumsum(2)
        host_groups = 0
        for part in dense:
            if perf_counter()-started >= time_limit or len(alternatives) >= max_groups or host_groups >= per_host_limit:
                break
            if part["box"] > host["box"]*(1-host["occupancy"]):
                continue
            if source_quantities is not None:
                needed = Counter(host["item"].get("source_members",[host["item"]["id"]]))
                needed.update(part["item"].get("source_members",[part["item"]["id"]]))
                if any(count > source_quantities.get(iid,0) for iid,count in needed.items()):
                    continue
            accepted = False
            for perm in permutations(range(3)):
                size = part["mesh"].extents[list(perm)]
                if np.any(size+2*clearance_mm > host["mesh"].extents):
                    continue
                rotation = np.eye(3)[list(perm)]
                if np.linalg.det(rotation) < 0:
                    rotation[0] *= -1
                correction = -np.minimum(rotation,0) @ part["mesh"].extents
                for index in empty_windows(prefix,np.ceil(size/pitch_mm).astype(int)+1):
                    if perf_counter()-started >= time_limit:
                        break
                    position = voxel.transform[:3,3]+np.asarray(index)*pitch_mm
                    if np.any(position < 0) or np.any(position+size > host["mesh"].extents+1e-8):
                        continue
                    pose = np.eye(4)
                    pose[:3,:3],pose[:3,3] = rotation,position+correction
                    offset = np.eye(4)
                    offset[:3,3] = 1
                    entries = (host,part)
                    items = [{"id":p["item"]["id"],"quantity":1,"mesh":p["item"]["mesh"]} for p in entries]
                    problem = {"units":"mm","clearance_mm":clearance_mm,
                               "container":{"inner_mm":(host["mesh"].extents+2).tolist()},"items":items}
                    layout = {"units":"mm","placements":[
                        {"item_id":p["item"]["id"],"unit_id":p["item"]["id"]+"#1","transform":matrix.tolist()}
                        for p,matrix in zip(entries,(offset@host["frame"],offset@pose@part["frame"]))]}
                    record = {"members":[i["id"] for i in items],"status":"geometry_rejected"}
                    attempts.append(record)
                    if not validate_mesh_layout(problem,layout)["valid"]:
                        continue
                    assembly = check_workbench_axes(problem,layout)
                    if assembly is None:
                        record["status"] = "assembly_unverified"
                        continue
                    record["status"] = "validated_cavity_alternative"
                    alternatives.append({"members":record["members"],"input":problem,"layout":layout,"assembly":assembly,
                                         "envelope_mm":host["mesh"].extents.tolist(),"group_box_volume_mm3":host["box"],
                                         "separate_box_volume_mm3":host["box"]+part["box"]})
                    host_groups += 1
                    accepted = True
                    break
                if accepted:
                    break
    result = {"scope":"Voxel-cavity proposals with exact source and assembly checks; not a complete kit",
              "source_library_sha256":sha256(json.dumps(library,sort_keys=True).encode()).hexdigest(),
              "clearance_mm":clearance_mm,"pitch_mm":pitch_mm,"alternatives":alternatives,"attempts":attempts,
              "per_host_alternative_limit":per_host_limit,
              "elapsed_seconds":perf_counter()-started,"time_budget_seconds":time_limit,
              "deadline_scope":"Soft bound; source preparation and an individual exact check may overrun"}
    (output/"cavities.json").write_text(json.dumps(result))
    return result
