"""Generate full-envelope-supported columns of repeated packing units."""
from collections import defaultdict


def make_columns(units, height, vertical_choice=0):
    """Return virtual columns and an exact expansion into original unit poses.

    Only copies of the same declared packing unit are stacked together. This
    establishes rectangular support, not actual contact of irregular parts.
    """
    by_item=defaultdict(list)
    for unit in units:by_item[unit["item_id"]].append(unit)
    columns=[];expansions={}
    for iid,copies in sorted(by_item.items()):
        source=copies[0]
        orientations=sorted(source["orientations"],key=lambda o:(o[1][2],o[1][0],o[1][1]))
        levels=sorted({s[2] for _,s in orientations if s[2]<=height+1e-8})
        if not levels:return None,None
        level=levels[min(vertical_choice,len(levels)-1)]
        rotation,size=next((r,s) for r,s in orientations if s[2]==level)
        count=max(1,int((height+1e-8)//size[2]))
        for start in range(0,len(copies),count):
            members=copies[start:start+count];uid=f"column-{len(columns)+1}"
            dims=[size[0],size[1],size[2]*len(members)]
            choices=[((0,1,2),tuple(dims))]
            swapped=(rotation[1],rotation[0],rotation[2])
            if all(swapped in [tuple(r) for r,_ in u["orientations"]] for u in members):
                choices.append(((1,0,2),(dims[1],dims[0],dims[2])))
            columns.append({"item_id":uid,"unit_id":uid,"dimensions":dims,
                            "orientations":choices})
            expansions[uid]=[{"item_id":u["item_id"],"unit_id":u["unit_id"],"rotation":list(rotation),
                              "dimensions_mm":list(size),"position_mm":[0,0,index*size[2]]}
                             for index,u in enumerate(members)]
    return columns,expansions


def expand_columns(packing, expansions):
    placements=[]
    for column in packing["placements"]:
        axes=column["rotation"]
        for member in expansions[column["unit_id"]]:
            placements.append({**member,"position_mm":[column["position_mm"][k]+member["position_mm"][axes[k]] for k in range(3)],
                               "dimensions_mm":[member["dimensions_mm"][k] for k in axes],
                               "rotation":[member["rotation"][k] for k in axes]})
    placements.sort(key=lambda p:(p["position_mm"][2],p["unit_id"]))
    return {"placements":placements}


def make_mixed_columns(units, height):
    """Stack progressively smaller envelopes within one compatible family.

    Each upper envelope lies fully on the immediately preceding envelope.
    Original CAD still needs independent validation; surface contact is not
    inferred from this rectangular proposal construction.
    """
    pending=list(units);columns=[];expansions={}
    while pending:
        options=[(u,r,s) for u in pending for r,s in u["orientations"] if s[2]<=height+1e-8]
        if not options:return None,None
        unit,rotation,size=max(options,key=lambda entry:(entry[2][0]*entry[2][1],-entry[2][2],entry[0]["unit_id"]))
        pending.remove(unit);base=size;z=0;members=[]
        while True:
            members.append({"item_id":unit["item_id"],"unit_id":unit["unit_id"],"rotation":list(rotation),
                            "dimensions_mm":list(size),"position_mm":[0,0,z]})
            z+=size[2]
            options=[(u,r,s) for u in pending for r,s in u["orientations"]
                     if s[0]<=size[0]+1e-8 and s[1]<=size[1]+1e-8 and s[2]<=height-z+1e-8]
            if not options:break
            unit,rotation,size=max(options,key=lambda entry:(entry[2][0]*entry[2][1],entry[2][2],entry[0]["unit_id"]))
            pending.remove(unit)
        uid=f"mixed-column-{len(columns)+1}";dims=[base[0],base[1],z]
        original={u["unit_id"]:u for u in units}
        choices=[((0,1,2),tuple(dims))]
        if all((m["rotation"][1],m["rotation"][0],m["rotation"][2]) in
               [tuple(r) for r,_ in original[m["unit_id"]]["orientations"]] for m in members):
            choices.append(((1,0,2),(dims[1],dims[0],dims[2])))
        columns.append({"item_id":uid,"unit_id":uid,"dimensions":dims,"orientations":choices})
        expansions[uid]=members
    return columns,expansions
