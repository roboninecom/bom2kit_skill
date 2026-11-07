"""Classify declared BOM descriptions into explicit, reviewable kitting families.

Printed provenance is supplied explicitly. No reference box assignments or poses
are read. Unknown purchased descriptions fail instead of defaulting to a family.
"""
import argparse
import json
from pathlib import Path
import re


def classify(library, printed, combine_printed=False, combine_electronics=False):
    families={};evidence={}
    for item in library["items"]:
        iid=item["id"]
        name=" ".join(str(v) for v in (item.get("name",""),item.get("source_name",""),
                       item.get("source_evidence",{}).get("source_item",""),iid))
        if iid in printed:
            family="printed-parts" if combine_printed else "printed-learning" if re.search(r"aruco|cube_cylinder|cone",name,re.I) else "printed-structure"
            basis="Declared printed source library; source description distinguishes learning objects"
        elif re.search(r"\bSTS?32\d+|servo.*factory box",name,re.I):
            protected=" ".join(str(item.get(k,"")) for k in ("dimension_basis","packing_state"))
            positive=re.search(r"\bprotect(?:ed|ive)\b|\b(?:EPE|foam)\b|\bfactory\s+(?:carton|box(?:es)?)\b",protected,re.I)
            negative=re.search(r"\bunprotected\b|\bbare servo\b|\b(?:no|without|not in a)\s+(?:protective packing|protection|factory box|factory carton)\b",protected,re.I)
            if combine_electronics and (not positive or negative):
                raise ValueError(f"Servo protective packing needs evidence before sharing a carton: {iid}")
            family="electronics-cables" if combine_electronics else "servo-drives"
            basis="Servo description; preserve declared factory/protective packing state"
        elif re.search(r"clamp|bearing|steel.*rod|screw|nut|o-ring|hex-key|driver|servo-extras|socket head|countersunk|set screw",name,re.I):
            family="mechanics-fasteners";basis="Mechanical component/monotype fastener packet description"
        elif re.search(r"power|cable|adapter|waveshare|camera|usb|cord",name,re.I):
            family="electronics-cables";basis="Electronics/accessory description; preserve declared protective envelope"
        else:
            raise ValueError(f"Needs explicit classification: {iid}: {name}")
        families[iid]=family;evidence[iid]={"description":name,"basis":basis,"classification":"rule_inference_requires_review"}
    return families,evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library",type=Path)
    parser.add_argument("--printed-library",type=Path,action="append",required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--combine-printed",action="store_true",help="Allow structural printed parts and learning objects in one printed-only family")
    parser.add_argument("--combine-protected-electronics",action="store_true",help="Allow explicitly protected servos with protected electronics and cables; keep bare mechanics separate")
    args=parser.parse_args()
    library=json.loads(args.library.read_bytes());printed=set()
    for path in args.printed_library:printed.update(i["id"] for i in json.loads(path.read_bytes())["items"])
    families,evidence=classify(library,printed,args.combine_printed,args.combine_protected_electronics)
    result={"schema_version":1,"families":families,"classification_evidence":evidence,
            "family_labels":{"printed-structure":"Printed structure and gripper parts","printed-learning":"Learning objects and disassembled ArUco",
                             "printed-parts":"Printed parts and learning objects",
                             "servo-drives":"Servos in declared protective packaging","mechanics-fasteners":"Mechanical parts and labeled fastener packets",
                             "electronics-cables":"Protected electronics, power supplies and cables"},
            "item_padding_mm":1,"clearance_mm":.2,"allow_all_rotations":True,"max_inner_cartons":6,"max_carton_types":5,
            "carton":{"wall_mm":7,"protection_mm":15,"inner_wall_mm":1.5,"reserved_top_mm":.8,
                      "gap_mm":.2,"dimension_increment_mm":1}}
    if args.combine_protected_electronics:
        result["family_labels"]["electronics-cables"]="Protected servos, electronics and cables"
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding="utf8")
    print(json.dumps({"families":sorted(set(families.values())),"classified_skus":len(families)}))


if __name__=="__main__":main()
