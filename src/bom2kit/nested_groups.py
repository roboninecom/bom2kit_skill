"""Extend independently discovered groups, then certify original source parts."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from .mesh_frames import packing_bounds
from time import perf_counter


def extend_groups(library, portfolio, output, time_limit=60, pair_seconds=8, max_pairs=8, cavities=False, pitch_mm=2, proposal_rank="void"):
    """Search group/part and group/group nesting without supplied carton targets.

    Existing groups are virtual rigid meshes only during proposal generation.
    Each retained extension is flattened and assembly-checked on original parts.
    Original quantities constrain proposals before the expensive geometric search.
    """
    import numpy as np
    import trimesh
    from .mesh_groups import discover_pairs, check_workbench_axes
    from .mesh_validation import validate_mesh_layout

    started = perf_counter()
    fingerprint = sha256(json.dumps(library,sort_keys=True).encode()).hexdigest()
    if portfolio["source_library_sha256"] != fingerprint:
        raise ValueError("Group portfolio belongs to a different source library")
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    sources = {i["id"]:i for i in library["items"]}
    quantities = {iid:i["quantity"] for iid,i in sources.items()}
    items = list(library["items"])
    expansions = {}
    for index,alternative in enumerate(portfolio["alternatives"]):
        counts = Counter(alternative["members"])
        if any(count > quantities.get(iid,0) for iid,count in counts.items()):
            raise ValueError("Group exceeds original source quantities")
        expected = {iid:{"id":iid,"quantity":count,"mesh":sources[iid]["mesh"]} for iid,count in counts.items()}
        if {i["id"]:i for i in alternative["input"]["items"]} != expected:
            raise ValueError("Group source manifest mismatch")
        if alternative["input"].get("clearance_mm",0) < portfolio["clearance_mm"]:
            raise ValueError("Group clearance is below portfolio requirement")
        if not validate_mesh_layout(alternative["input"],alternative["layout"])["valid"]:
            raise ValueError("Invalid original-source group")
        meshes = []
        for pose in alternative["layout"]["placements"]:
            data = json.loads(Path(sources[pose["item_id"]]["mesh"]["path"]).read_text())
            mesh = trimesh.Trimesh(data["vertices_mm"],data["triangles"],process=False)
            mesh.apply_transform(pose["transform"])
            meshes.append(mesh)
        mesh = trimesh.util.concatenate(meshes)
        iid = "discovered-compound-"+str(index)
        if iid in sources:
            raise ValueError("Generated compound identity conflicts with source identity")
        path = output/(iid+".json")
        path.write_text(json.dumps({"units":"mm","vertices_mm":mesh.vertices.tolist(),"triangles":mesh.faces.tolist()}))
        items.append({"id":iid,"quantity":min(quantities[k]//v for k,v in counts.items()),
                      "source_members":alternative["members"],
                      "mesh":{"path":str(path),"sha256":sha256(path.read_bytes()).hexdigest()}})
        expansions[iid] = alternative["layout"]["placements"]
    virtual = {"units":"mm","all_meshes_valid_volumes":True,"items":items}
    if cavities:
        from .cavity_groups import discover_cavities
        candidates = discover_cavities(virtual,output/"virtual-cavities",portfolio["clearance_mm"],
                                      time_limit=time_limit,max_groups=max_pairs,host_item_ids=set(expansions),
                                      dense_item_ids=set(sources),source_quantities=quantities)
    else:
        candidates = discover_pairs(virtual,output/"virtual-pairs",portfolio["clearance_mm"],
                                    time_limit=time_limit,pair_seconds=pair_seconds,max_pairs=max_pairs,
                                    required_item_ids=set(expansions),source_quantities=quantities,pitch_mm=pitch_mm,
                                    proposal_rank=proposal_rank)
    alternatives, attempts = [], []
    original_box_volumes = {}
    for candidate in candidates["alternatives"]:
        counts, poses = Counter(), []
        for parent in candidate["layout"]["placements"]:
            children = expansions.get(parent["item_id"],[{"item_id":parent["item_id"],"transform":np.eye(4).tolist()}])
            for child in children:
                iid = child["item_id"]
                counts[iid] += 1
                poses.append({"item_id":iid,"unit_id":iid+"#"+str(counts[iid]),
                              "transform":(np.asarray(parent["transform"])@np.asarray(child["transform"])).tolist()})
        problem = {**candidate["input"],"items":[{"id":iid,"quantity":count,"mesh":sources[iid]["mesh"]}
                                                  for iid,count in counts.items()]}
        layout = {"units":"mm","placements":poses}
        assembly = check_workbench_axes(problem,layout)
        attempts.append({"members":list(counts.elements()),"assembly_valid":assembly is not None})
        if assembly is None:
            continue
        # Compute the ranking baseline from original source envelopes, not the
        # virtual compounds (which may already contain substantial void savings).
        separate = 0.
        for iid,count in counts.items():
            # Ranking bounds depend on the source, not the candidate pose.
            # Exact source hashes and geometry are still checked per assembly.
            if iid not in original_box_volumes:
                data = json.loads(Path(sources[iid]["mesh"]["path"]).read_text())
                mesh = trimesh.Trimesh(data["vertices_mm"],data["triangles"],process=False)
                _,extents = packing_bounds(mesh)
                original_box_volumes[iid] = float(np.prod(extents))
            separate += count*original_box_volumes[iid]
        alternatives.append({"members":list(counts.elements()),"input":problem,"layout":layout,"assembly":assembly,
                             "envelope_mm":candidate["envelope_mm"],"separate_box_volume_mm3":separate,
                             "group_box_volume_mm3":candidate["group_box_volume_mm3"]})
    result = {"source_library_sha256":fingerprint,"clearance_mm":portfolio["clearance_mm"],
              "alternatives":alternatives,"attempts":attempts,"elapsed_seconds":perf_counter()-started,
              "scope":"Original-source assembly-checked extensions; complete-kit grouping still required"}
    (output/"groups.json").write_text(json.dumps(result,allow_nan=False))
    return result
