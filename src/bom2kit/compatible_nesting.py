"""Discover compound packing units strictly within declared compatible families."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter


def discover_compatible_units(library, policy, output, time_limit=60, workers=1):
    import numpy as np
    import trimesh
    from .parallel_nesting import discover_pair_shards

    started=perf_counter();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    search=[]
    candidates=[]
    # No reference grouping or poses enter discovery. All family members are
    # eligible; actual empty geometry decides whether nesting saves space.
    # Spend the search budget where source geometry has voids. Solid factory
    # envelopes cannot interpenetrate; repeatedly asking for their nesting only
    # consumes time. Ranking is a proposal heuristic, never a fit certificate.
    weights=Counter()
    for item in library["items"]:
        raw=Path(item["mesh"]["path"]).read_bytes()
        if sha256(raw).hexdigest()!=item["mesh"]["sha256"]:raise ValueError("Source mesh hash mismatch")
        data=json.loads(raw)
        mesh=trimesh.Trimesh(data["vertices_mm"],data["triangles"],process=False)
        weights[policy["families"][item["id"]]]+=max(0,float(np.prod(mesh.extents)-mesh.volume))*item["quantity"]
    family_ids=sorted((family for family,weight in weights.items() if weight>1e-4),key=lambda family:-weights[family])
    for index,family in enumerate(family_ids):
        budget=(time_limit-(perf_counter()-started))*weights[family]/sum(weights[f] for f in family_ids[index:])
        if budget<=0:break
        subset={**library,"items":[i for i in library["items"] if policy["families"][i["id"]]==family]}
        family_start=perf_counter()
        portfolio=discover_pair_shards(subset,output/family,workers=workers,clearance_mm=max(policy["clearance_mm"],2*policy["item_padding_mm"]),
                                 time_limit=budget*.65,pair_seconds=min(5,budget),max_pairs=min(48,max(12,int(budget/6))),pitch_mm=4,proposal_rank="overlap_bound")
        extension_attempts=[]
        for round_index in range(2):
            left=budget-(perf_counter()-family_start)
            if not portfolio["alternatives"] or left<=3:break
            from .nested_groups import extend_groups
            # Keep preparation bounded when parallel discovery produces many
            # alternatives. Diverse seeds avoid rebuilding dozens of compounds
            # which all consume the same dominant source shapes.
            from .mesh_groups import rank_pair_proposals
            alternatives=portfolio["alternatives"]
            members={i:set(a["members"]) for i,a in enumerate(alternatives)}
            ranked=rank_pair_proposals([(a["group_box_volume_mm3"]-a["separate_box_volume_mm3"],i,i)
                                       for i,a in enumerate(alternatives)],12,members)
            seeds={**portfolio,"alternatives":[alternatives[i] for _,i,_ in ranked]}
            extensions=extend_groups(subset,seeds,output/(family+f"-extensions-{round_index+1}"),
                                     time_limit=left/(2-round_index),pair_seconds=5,max_pairs=min(24,max(8,int(left/6))),pitch_mm=4,
                                     proposal_rank="overlap_bound")
            extension_attempts.extend(extensions["attempts"])
            if not extensions["alternatives"]:break
            portfolio["alternatives"].extend(extensions["alternatives"])
        search.append({"family":family,"attempts":portfolio["attempts"],"seconds":perf_counter()-family_start,
                       "extension_attempts":extension_attempts,"proposal_pitch_mm":4,"workers":workers})
        candidates.extend((family,a) for a in portfolio["alternatives"])
    return compose_compatible_units(library,policy,candidates,output,search,perf_counter()-started)


def compose_compatible_units(library, policy, candidates, output, search=(), discovery_seconds=0):
    """Compose one in-run grouping portfolio; replay remains mandatory downstream."""
    import numpy as np
    import trimesh
    from .report import fingerprint
    started=perf_counter();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    sources={i["id"]:i for i in library["items"]}
    remaining=Counter({i["id"]:i["quantity"] for i in library["items"]})
    assigned=Counter();items=[];expansion={};certificates=[];families={}
    for family,alternative in sorted(candidates,key=lambda pair:pair[1]["group_box_volume_mm3"]-pair[1]["separate_box_volume_mm3"]):
        if any(policy["families"][iid]!=family for iid in alternative["members"]):
            raise ValueError("Compound crosses compatible-family boundary")
        needed=Counter(alternative["members"])
        copies=min(remaining[iid]//q for iid,q in needed.items())
        requested=alternative.get("selected_copies",copies)
        if type(requested) is not int or requested<0:raise ValueError("Invalid selected group quantity")
        copies=min(copies,requested)
        if not copies:continue
        group_id=f"nested-{len(certificates)+1}"
        if group_id in sources:raise ValueError("Generated compound identity conflicts with a source")
        pieces=[]
        for pose in alternative["layout"]["placements"]:
            data=json.loads(Path(sources[pose["item_id"]]["mesh"]["path"]).read_bytes())
            mesh=trimesh.Trimesh(data["vertices_mm"],data["triangles"],process=False)
            mesh.apply_transform(pose["transform"]);pieces.append(mesh)
        combined=trimesh.util.concatenate(pieces)
        path=output/(group_id+".json")
        path.write_text(json.dumps({"units":"mm","vertices_mm":combined.vertices.tolist(),"triangles":combined.faces.tolist()}),encoding="utf8")
        items.append({"id":group_id,"quantity":copies,"mesh":{"path":str(path),"sha256":sha256(path.read_bytes()).hexdigest()}})
        families[group_id]=family
        for copy in range(copies):
            members=[]
            for pose in alternative["layout"]["placements"]:
                iid=pose["item_id"];assigned[iid]+=1;remaining[iid]-=1
                members.append({**pose,"unit_id":f"{iid}#{assigned[iid]}"})
            expansion[f"{group_id}#{copy+1}"]=members
        certificates.append({"group_id":group_id,"alternative":alternative})
    for iid,quantity in remaining.items():
        if not quantity:continue
        items.append({**sources[iid],"quantity":quantity});families[iid]=policy["families"][iid]
        for copy in range(quantity):
            assigned[iid]+=1
            expansion[f"{iid}#{copy+1}"]=[{"item_id":iid,"unit_id":f"{iid}#{assigned[iid]}","transform":np.eye(4).tolist()}]
    return {"library":{**deepcopy(library),"items":items},"families":families,"expansion":expansion,
            "certificates":certificates,"search":list(search),"elapsed_seconds":discovery_seconds+perf_counter()-started,
            "source_library_fingerprint":fingerprint(library),"policy_fingerprint":fingerprint(policy),
            "alternatives":candidates}
