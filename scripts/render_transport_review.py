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


def carton_layers_svg(modules):
    """Exact horizontal carton sections; labels follow the assembly list."""
    low=[min(m["position_mm"][k] for m in modules) for k in range(3)]
    high=[max(m["position_mm"][k]+m["external_mm"][k] for m in modules) for k in range(3)]
    levels=sorted({m["position_mm"][2] for m in modules}|{m["position_mm"][2]+m["external_mm"][2] for m in modules})
    width,depth=high[0]-low[0],high[1]-low[1];scale=min(300/width,230/depth)
    panels=[];colors=["#d8e8f0","#96b7ce","#f5e4b4","#b6cabe","#d6bfd1","#dbc3a4"]
    for panel,(bottom,top) in enumerate(zip(levels,levels[1:])):
        ox=panel*360+30;oy=55;pieces=[]
        for index,m in enumerate(modules,1):
            if not m["position_mm"][2]<=bottom+1e-7<m["position_mm"][2]+m["external_mm"][2]-1e-7:continue
            x=ox+(m["position_mm"][0]-low[0])*scale;y=oy+(depth-(m["position_mm"][1]-low[1])-m["external_mm"][1])*scale
            w,h=m["external_mm"][0]*scale,m["external_mm"][1]*scale
            pieces.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{colors[(index-1)%len(colors)]}" stroke="#263541"/><text x="{x+w/2}" y="{y+h/2}" text-anchor="middle" dominant-baseline="middle">{index}</text>')
        panels.append(f'<text x="{ox}" y="25">Height {bottom-low[2]:g}–{top-low[2]:g} mm</text>{"".join(pieces)}<text x="{ox}" y="315">Footprint {width:g} × {depth:g} mm</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {360*(len(levels)-1)} 340" style="width:100%;height:auto;max-height:420px"><rect width="100%" height="100%" fill="white"/><g font-family="sans-serif" font-size="18" fill="#18202a">{"".join(panels)}</g></svg>'


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
    ordered_modules=[next(m for m in info["modules"] if m["id"]==c["id"]) for c in plan["cartons_in_outer_insertion_order"]]
    (output/"outer-layers.svg").write_text(carton_layers_svg(ordered_modules),encoding="utf8")
    for index,module in enumerate(ordered_modules,1):
        parts.append((box(module["position_mm"],module["external_mm"]),index))
    # Camera-facing panels and lid are hidden for visibility only. The six
    # complete panels are retained in the manifest and shown in an exploded view.
    for index,panel in enumerate(info["foam_panels"],len(parts)+1):
        if panel["id"] in ("foam-bottom","foam-left","foam-back"):
            parts.append((box(panel["origin_mm"],panel["dimensions_mm"]),index))
    wall=policy["carton"]["wall_mm"]
    render_solid_views(parts,output/"outer-cutaway.png",title="Closed cartons inside protective foam",
                       cavity=container["inner_mm"],wall=wall,
                       caption="Nominal packaging geometry; front/right foam and lid hidden",label_numbers=set(range(1,len(ordered_modules)+1)))
    exploded=[];directions={"bottom":[0,0,-1],"top":[0,0,1],"left":[-1,0,0],"right":[1,0,0],"front":[0,-1,0],"back":[0,1,0]}
    distance=max(container["inner_mm"])*.18
    for index,panel in enumerate(info["foam_panels"],1):
        origin=np.asarray(panel["origin_mm"])+np.asarray(directions[panel["id"].removeprefix("foam-")])*distance
        exploded.append((box(origin,panel["dimensions_mm"]),index))
    render_solid_views(exploded,output/"foam-exploded.png",title="Six foam panels - exploded view",
                       caption="Display offsets only; actual assembly uses butt joints")
    items={i["id"]:i for i in result["input"]["items"]}
    poses={p["unit_id"]:p["item_id"] for p in result["layout"]["placements"]}
    def unit_label(uid):
        item=items[poses[uid]]
        name=item.get("name") or item.get("source_name") or item.get("source_evidence",{}).get("source_item") or item["id"]
        count=sum(item.get("contents",{}).values())
        packet=f"; {count} pieces in packet" if count>1 else ""
        return f"{name} ({uid}{packet})"
    sections=[]
    for index,carton in enumerate(plan["cartons_in_outer_insertion_order"],1):
        module=next(m for m in info["modules"] if m["id"]==carton["id"])
        label=policy.get("family_labels",{}).get(module["family"],module["family"])
        # Older policies used this label even for declared protective sleeves.
        # Keep the frozen policy intact; do not imply factory cartons in prose.
        if label=="Factory-boxed servos, protected electronics and cables":
            label="Protected servos, electronics and cables"
        rows=[];contents=[];unit_slots={}
        slots=[p for p in candidate["layout"]["placements"] if p["layer_id"]==carton["id"]]
        for number,slot in enumerate(slots,1):
            members=result.get("groups",{}).get("assembly-"+slot["unit_id"],[slot["unit_id"]])
            unit_slots.update({uid:number for uid in members})
            contents.append(f"<tr><td>{number}</td><td>{escape('; '.join(unit_label(uid) for uid in members))}</td></tr>")
        for step,entry in enumerate(carton["packing_sequence"],1):
            numbers=", ".join(str(n) for n in sorted({unit_slots[uid] for uid in entry["unit_ids"]}))
            labels=[unit_label(uid) for uid in entry["unit_ids"]]
            rows.append(f"<li>Slot {numbers}: {escape('; '.join(labels))}</li>")
        sections.append(f"<section><h2>{index}. {escape(label)}</h2><p>{escape(str(module['external_mm']))} mm outside; "
                        f"{len(module['unit_ids'])} source packing units.</p><img src='carton-{index}-solid.png'>"
                        f"<details><summary>Numbered contents and insertion order</summary><table><tr><th>Picture slot</th><th>Contents</th></tr>{''.join(contents)}</table>"
                        f"<h3>Insertion steps</h3><ol>{''.join(rows)}</ol></details></section>")
    materials="".join(f"<tr><td>{index}. {escape(p['id'])}</td><td>{escape(str(p['dimensions_mm']))}</td></tr>" for index,p in enumerate(info["foam_panels"],1))
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
<img src='outer-cutaway.png'><p>Numbers match the carton list below. Stacked cartons share projected positions. Cartons retain their actual checked coordinates; the cutaway hides the lid, two near walls and matching foam panels.</p>
<h2>Carton layers</h2><img src='outer-layers.svg'><p>Horizontal sections through the exact carton block, bottom to top. Heights are above its base, excluding the surrounding foam and outer walls. Numbers match the carton list.</p>
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
