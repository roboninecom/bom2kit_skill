"""Bounded whole-kit grouping configurations from discovered alternatives."""
from collections import Counter
from .report import fingerprint


def group_configurations(library, alternatives, limit):
    """Compare greedy groups, forced anchors with compatible groups, and singles.

    Skip pools that resolve to the same consumed source poses and quantities.
    No carton dimensions or comparison reference enter configuration generation.
    """
    ranked = sorted(alternatives,key=lambda a:a["group_box_volume_mm3"]-a["separate_box_volume_mm3"])
    pools = [ranked]
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
