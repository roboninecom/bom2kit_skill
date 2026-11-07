"""Render checked carton contents, nominal foam geometry and assembly steps."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from bom2kit.assembly_plan import build_assembly_plan
from bom2kit.report import fingerprint
from bom2kit.solid_views import render_solid_views
from bom2kit.transport_validation import validate_transport
from render_design_review import render
from render_packing_comparison import template_picture


def render_transport(result_path,bom_path,output):
    import numpy as np
    import trimesh
    result_path=Path(result_path);output=Path(output).resolve()
    raw=result_path.read_bytes();result=json.loads(raw);bom=json.loads(Path(bom_path).read_bytes())
    policy=result["logistics"]["policy"]
    checks=validate_transport(result,policy)
    if not checks["valid"]:raise ValueError(checks["errors"])
    plan=build_assembly_plan(result,bom)
    render(result_path,bom_path,output)
    info=result["logistics"];candidate=result["envelope_design"]["candidate"]
    container=result["input"]["container"]
    parts=[]
    def box(origin,dimensions):
        mesh=trimesh.creation.box(dimensions)
        mesh.apply_translation(np.asarray(origin)+np.asarray(dimensions)/2)
        return mesh
    for index,module in enumerate(info["modules"],1):
        parts.append((box(module["position_mm"],module["external_mm"]),index))
    # Camera-facing panels and lid are hidden for visibility only. The six
    # complete panels are retained in the manifest and shown in an exploded view.
    for index,panel in enumerate(info["foam_panels"],len(parts)+1):
        if panel["id"] in ("foam-bottom","foam-left","foam-back"):
            parts.append((box(panel["origin_mm"],panel["dimensions_mm"]),index))
    wall=policy["carton"]["wall_mm"]
    render_solid_views(parts,output/"outer-cutaway.png",title="Closed cartons inside protective foam",
                       cavity=container["inner_mm"],wall=wall,
                       caption="Nominal packaging geometry; front/right foam and lid hidden",label_slots=False)
    exploded=[];directions={"bottom":[0,0,-1],"top":[0,0,1],"left":[-1,0,0],"right":[1,0,0],"front":[0,-1,0],"back":[0,1,0]}
    distance=max(container["inner_mm"])*.18
    for index,panel in enumerate(info["foam_panels"],1):
        origin=np.asarray(panel["origin_mm"])+np.asarray(directions[panel["id"].removeprefix("foam-")])*distance
        exploded.append((box(origin,panel["dimensions_mm"]),index))
    render_solid_views(exploded,output/"foam-exploded.png",title="Six foam panels - exploded view",
                       caption="Display offsets only; actual assembly uses butt joints")
    items={i["id"]:i for i in result["input"]["items"]}
    poses={p["unit_id"]:p["item_id"] for p in result["layout"]["placements"]}
    sections=[]
    for index,carton in enumerate(plan["cartons_in_outer_insertion_order"],1):
        module=next(m for m in info["modules"] if m["id"]==carton["id"])
        label=policy.get("family_labels",{}).get(module["family"],module["family"])
        rows=[]
        for step,entry in enumerate(carton["packing_sequence"],1):
            labels=[]
            for uid in entry["unit_ids"]:
                item=items[poses[uid]];name=item.get("name") or item.get("source_name") or item["id"]
                labels.append(f"{name} ({uid})")
            rows.append(f"<li>{escape('; '.join(labels))}</li>")
        sections.append(f"<section><h2>{index}. {escape(label)}</h2><p>{escape(str(module['external_mm']))} mm outside; "
                        f"{len(module['unit_ids'])} source packing units.</p><img src='carton-{index}-solid.png'>"
                        f"<details><summary>Geometric insertion order</summary><ol>{''.join(rows)}</ol></details></section>")
    materials="".join(f"<tr><td>{escape(p['id'])}</td><td>{escape(str(p['dimensions_mm']))}</td></tr>" for p in info["foam_panels"])
    templates=[]
    for template in plan["templates"]:
        filename=template["id"]+"-assembly.png"
        template_picture(template,output/filename)
        sequence="; ".join(f"{index}: {', '.join(step['unit_ids'])}" for index,step in enumerate(template["packing_sequence"],1))
        templates.append(f"<section><h3>{escape(template['id'])}</h3><img src='{escape(filename)}'><p>{escape(sequence)}</p></section>")
    dimensions=" x ".join(str(v) for v in candidate["external_mm"])
    html=f"""<!doctype html><meta charset='utf-8'><title>Transport packaging review</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:30px auto;color:#18202a}}img{{width:100%}}section{{border-top:1px solid #ccc;margin-top:24px}}td,th{{padding:6px;text-align:left}}details{{background:#f4f5f7;padding:12px}}small{{overflow-wrap:anywhere}}</style>
<h1>Transport packaging review</h1><p><b>{dimensions} mm · {candidate['volume_mm3']/1e6:.3f} L · {info['carton_count']} cartons · {info['carton_types']} sizes</b></p>
<p>Complete BOM, original CAD, geometric assembly, compatible families, exact carton block and six-face foam checks pass. No spacers.</p>
<p><b>Not transport-qualified.</b> Part restraint, hand access, foam grade, carton strength and manufacturing tolerances require prototype checks. Estimated purchased envelopes remain estimates.</p>
<img src='outer-cutaway.png'><p>Cartons retain their actual checked coordinates. The cutaway hides the outer lid and two near walls, and matching foam panels.</p>
<h2>Assembly sequence</h2><ol><li>Prepare labeled parts and packets from the complete BOM.</li><li>Pack each carton in the order shown below. Assemble nested groups on the workbench using the generated assembly plan.</li><li>Close each carton. Fit the bottom and side foam panels; insert cartons in the numbered order.</li><li>Fit the top foam and close the outer carton. Confirm restraint and closure on a physical prototype before shipping.</li></ol>
{''.join(sections)}<h2>Nested-group workbench assembly</h2>{''.join(templates) or '<p>No nested groups.</p>'}<h2>Protection panels</h2><img src='foam-exploded.png'><table><tr><th>Panel</th><th>Dimensions, mm</th></tr>{materials}</table>
<p>Outer corrugated wall: {wall:g} mm. Foam thickness: {policy['carton']['protection_mm']:g} mm. Material grade and compression are not qualified.</p>
<small>Result SHA256: {sha256(raw).hexdigest()}</small>"""
    (output/"transport-review.html").write_text(html,encoding="utf8")
    (output/"assembly-plan.json").write_text(json.dumps(plan,indent=2),encoding="utf8")
    (output/"transport-checks.json").write_text(json.dumps({"result_sha256":sha256(raw).hexdigest(),"result_fingerprint":fingerprint(result),"checks":checks},indent=2),encoding="utf8")
    return {"report":str(output/"transport-review.html")}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result",type=Path);parser.add_argument("bom",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();print(json.dumps(render_transport(args.result,args.bom,args.output)))
