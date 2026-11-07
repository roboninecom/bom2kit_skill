"""Independent compatibility, partition and material checks, not transit testing."""
from collections import Counter
from itertools import combinations
import math

from .protection_geometry import validate_foam_shell
from .report import fingerprint
from .carton_tiling import carton_size_key


def validate_transport(result, policy):
    errors=[]
    try:
        info=result["logistics"];candidate=result["envelope_design"]["candidate"]
        if info["policy_hash"]!=fingerprint(policy) or info["policy"]!=policy:
            errors.append("Policy fingerprint mismatch")
        if info["spacers"]:errors.append("Spacers are forbidden")
        modules=info["modules"];layers={l["id"]:l for l in candidate["layout"]["layers"]}
        if len(modules)!=len(layers) or {m["id"] for m in modules}!=set(layers):
            errors.append("Module/carton identity mismatch")
        actual={p["unit_id"]:p["item_id"] for p in result["layout"]["placements"]}
        source_ids={i["id"] for i in result["input"]["items"]}
        if set(policy["families"])!=source_ids:errors.append("Incomplete source family classification")
        seen=[]
        for m in modules:
            seen.extend(m["unit_ids"])
            if any(policy["families"].get(actual.get(uid))!=m["family"] for uid in m["unit_ids"]):
                errors.append("Incompatible family membership")
            layer=layers[m["id"]]
            expected=[v+2*layer["wall_mm"] for v in layer["inner_mm"]]
            if m["external_mm"]!=expected or m["position_mm"]!=layer["position_mm"]:
                errors.append("Module geometry differs from checked carton")
            slots={uid for p in candidate["layout"]["placements"] if p["layer_id"]==m["id"]
                   for uid in result.get("groups",{}).get("assembly-"+p["unit_id"],[p["unit_id"]])}
            if slots!=set(m["unit_ids"]):errors.append("Contents do not match carton assignment")
        if Counter(seen)!=Counter(actual.keys()):errors.append("Module unit coverage mismatch")
        distinct=len({carton_size_key(m["external_mm"]) for m in modules})
        if info.get("carton_count",len(modules))!=len(modules) or info.get("carton_types",distinct)!=distinct:
            errors.append("Reported carton counts differ from actual geometry")
        if len(modules)>policy["max_inner_cartons"] or distinct>policy["max_carton_types"]:
            errors.append("Carton count/type cap exceeded")
        block=info["block_mm"];offset=policy["carton"]["protection_mm"]
        for m in modules:
            if any(o<offset-1e-7 or o+d>offset+limit+1e-7 for o,d,limit in zip(m["position_mm"],m["external_mm"],block)):
                errors.append("Carton outside tiled block")
        for a,b in combinations(modules,2):
            if all(min(a["position_mm"][k]+a["external_mm"][k],b["position_mm"][k]+b["external_mm"][k])-
                   max(a["position_mm"][k],b["position_mm"][k])>1e-7 for k in range(3)):
                errors.append("Overlapping inner cartons")
        if not math.isclose(sum(math.prod(m["external_mm"]) for m in modules),math.prod(block),rel_tol=1e-10):
            errors.append("Unfilled block space: carton leaves must tile completely")
        shell=validate_foam_shell(result["input"]["container"]["inner_mm"],offset,info["foam_panels"])
        errors.extend(shell["errors"])
        if info.get("physical_qualification") or info.get("retention_verified"):
            errors.append("This geometric pipeline cannot issue physical retention/transit approval")
    except (KeyError,TypeError,ValueError) as error:
        errors.append(str(error))
    return {"valid":not errors,"errors":errors,"checks":["complete_family_assignment","compatible_carton_contents",
            "carton_count_and_type_caps","exact_no_spacer_partition","six_face_foam_geometry"],
            "retention_verified":False,"physical_qualification":False,
            "scope":"Declared family segregation and nominal carton/foam geometry only"}
