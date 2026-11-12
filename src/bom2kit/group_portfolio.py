"""Bounded whole-kit grouping configurations from discovered alternatives."""
from collections import Counter
from .report import fingerprint


def optimized_group_pool(library, alternatives, time_limit=3):
    """Resolve competing group quantities with bounded integer set packing.

    This optimizes discovered envelope savings only, not shipping volume. The
    selected pool remains a proposal for independent complete carton search.
    """
    if not alternatives:return []
    import numpy as np
    from scipy.optimize import milp,Bounds,LinearConstraint
    quantities={i["id"]:i["quantity"] for i in library["items"]}
    ids=list(quantities);matrix=np.zeros((len(ids),len(alternatives)))
    savings=[];upper=[]
    for col,a in enumerate(alternatives):
        needed=Counter(a["members"])
        if not needed or set(needed)-set(quantities):raise ValueError("Unknown optimized group members")
        for row,iid in enumerate(ids):matrix[row,col]=needed[iid]
        upper.append(min(quantities[iid]//q for iid,q in needed.items()))
        savings.append(a["separate_box_volume_mm3"]-a["group_box_volume_mm3"])
    result=milp(-np.asarray(savings,dtype=float),integrality=np.ones(len(alternatives)),
                bounds=Bounds(np.zeros(len(alternatives)),upper),
                constraints=LinearConstraint(matrix,np.zeros(len(ids)),[quantities[iid] for iid in ids]),
                options={"time_limit":time_limit})
    if result.x is None:return []
    copies=np.rint(result.x).astype(int)
    if np.any(np.abs(result.x-copies)>1e-5) or np.any(copies<0) or np.any(matrix@copies>np.array([quantities[iid] for iid in ids])):
        raise ValueError("Invalid integer group selection")
    return [{**a,"selected_copies":int(n)} for a,n in zip(alternatives,copies) if n>0]


def group_configurations(library, alternatives, limit, *, optimize=False):
    """Compare greedy groups, leave-one-out neighbors, anchors and singles.

    Skip pools that resolve to the same consumed source poses and quantities.
    No carton dimensions or comparison reference enter configuration generation.
    """
    ranked = sorted(alternatives,key=lambda a:a["group_box_volume_mm3"]-a["separate_box_volume_mm3"])
    pools = ([optimized_group_pool(library,alternatives)] if optimize else [])+[ranked]
    # A locally efficient group can impose a poor layer height. Explore nearby
    # complete groupings before jumping to isolated single-group configurations.
    for index in range(len(ranked)):
        pools.append(ranked[:index]+ranked[index+1:])
    for anchor in ranked:
        members = set(anchor["members"])
        pools.append([anchor]+[a for a in ranked if members.isdisjoint(a["members"])])
        pools.append([anchor])
    configurations, seen = [],set()
    for pool in pools:
        remaining = {i["id"]:i["quantity"] for i in library["items"]}
        selected,signature = [],[]
        for alternative in sorted(pool,key=lambda a:a["group_box_volume_mm3"]-a["separate_box_volume_mm3"]):
            needed = Counter(alternative["members"])
            copies = min(remaining[iid]//count for iid,count in needed.items())
            copies = min(copies,alternative.get("selected_copies",copies))
            if not copies:
                continue
            selected.append(alternative)
            signature.append((fingerprint(alternative["layout"]),copies))
            for iid,count in needed.items():
                remaining[iid] -= count*copies
        key = tuple(sorted(signature))
        if selected and key not in seen:
            seen.add(key)
            configurations.append(selected)
        if len(configurations) >= limit:
            break
    return configurations
