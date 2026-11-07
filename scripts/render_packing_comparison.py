"""Render a frozen-result comparison and geometric packing steps, never run search."""
import argparse
import base64
from hashlib import sha256
from html import escape
import json
import math
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from bom2kit.assembly_plan import build_assembly_plan
from bom2kit.report import fingerprint
from render_design_review import render


def picture(path, label):
    return f"<img alt='{escape(label,quote=True)}' src='data:image/png;base64,{base64.b64encode(Path(path).read_bytes()).decode()}'>"


def template_picture(template, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    import numpy as np
    import trimesh

    items = {i["id"]:i for i in template["workbench_input"]["items"]}
    order = {uid:index for index,step in enumerate(template["packing_sequence"],1) for uid in step["unit_ids"]}
    meshes = []
    for pose in template["workbench_layout"]["placements"]:
        data = json.loads(Path(items[pose["item_id"]]["mesh"]["path"]).read_text())
        mesh = trimesh.Trimesh(data["vertices_mm"],data["triangles"],process=False)
        mesh.apply_transform(pose["transform"])
        meshes.append((pose["unit_id"],mesh))
    fig,axes = plt.subplots(1,2,figsize=(11,4.3))
    for ax,projection,depth,title in zip(axes,((0,1),(0,2)),(2,1),("Top: X/Y","Side: X/Z; insertion downward")):
        faces,colors,depths = [],[],[]
        for uid,mesh in meshes:
            faces.extend(mesh.triangles[:,:,projection])
            depths.extend(mesh.triangles[:,:,depth].mean(axis=1))
            colors.extend([plt.get_cmap("tab10")((order[uid]-1)%10)]*len(mesh.faces))
            centre = mesh.bounds.mean(axis=0)
            ax.text(centre[projection[0]],centre[projection[1]],str(order[uid]),ha="center",va="center",
                    bbox={"facecolor":"white","alpha":.9,"edgecolor":"#888","pad":2},zorder=3)
        indices = np.argsort(depths,kind="stable")
        ax.add_collection(PolyCollection(np.asarray(faces)[indices],facecolors=np.asarray(colors)[indices],edgecolors="none"))
        ax.autoscale_view()
        ax.set_aspect("equal")
        ax.set_title(title)
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)" if projection[1]==1 else "Z (mm)")
    fig.suptitle(template["id"]+": numbered assembly order")
    fig.tight_layout()
    fig.savefig(output,dpi=130)
    plt.close(fig)


def stack_picture(plan, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import numpy as np
    fig = plt.figure(figsize=(9,6))
    ax = fig.add_axes([.26,0,.74,.88],projection="3d")
    all_points,legend = [],[]
    for index,layer in enumerate(plan["cartons_in_outer_insertion_order"]):
        low = np.asarray(layer["position_mm"],dtype=float)
        low[2] += index*25
        size = np.asarray(layer["inner_mm"])+2*layer["wall_mm"]
        x,y,z = low; w,d,h = size
        vertices = np.asarray([[x,y,z],[x+w,y,z],[x+w,y+d,z],[x,y+d,z],
                               [x,y,z+h],[x+w,y,z+h],[x+w,y+d,z+h],[x,y+d,z+h]])
        faces = [[vertices[i] for i in indices] for indices in ((0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))]
        ax.add_collection3d(Poly3DCollection(faces,facecolors=plt.get_cmap("tab10")(index%10),edgecolors="#334155",linewidths=.6,alpha=.45))
        label = f"{index+1}. {layer['id']}\n"+" x ".join(f"{v:g}" for v in size)+" mm"
        legend.append(Patch(facecolor=plt.get_cmap("tab10")(index%10),label=label))
        all_points.extend(vertices)
    pts=np.asarray(all_points); span=np.ptp(pts,axis=0)
    ax.set(xlim=(pts[:,0].min(),pts[:,0].max()),ylim=(pts[:,1].min(),pts[:,1].max()),zlim=(pts[:,2].min(),pts[:,2].max()))
    ax.set_box_aspect(span)
    ax.view_init(elev=23,azim=-65)
    ax.set_axis_off()
    fig.legend(handles=legend,loc="center left",fontsize=9,frameon=False)
    fig.suptitle("Generated inner cartons: bottom-to-top order\nExploded view; 25 mm display spacing added")
    fig.savefig(output,dpi=130)
    plt.close(fig)


def render_comparison(config_path, output):
    import fitz
    config = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    cards,rows,audits = [],[],[]
    for case in config["cases"]:
        name = case["name"]
        directory = output/name
        directory.mkdir(exist_ok=True)
        raw = Path(case["result"]).read_bytes()
        result = json.loads(raw)
        before = json.loads(Path(case["before_result"]).read_bytes())
        if result["input"]["items"] != before["input"]["items"]:
            raise ValueError("Before/after source manifests differ")
        policy = lambda r:{k:v for k,v in r["input"]["container"].items() if k!="inner_mm"}
        if policy(result)!=policy(before) or result["input"].get("clearance_mm")!=before["input"].get("clearance_mm"):
            raise ValueError("Before/after protection or clearance differs")
        expected = json.loads(Path(case["bom"]).read_bytes())
        plan = build_assembly_plan(result,expected)
        (directory/"assembly-plan.json").write_text(json.dumps(plan,indent=2),encoding="utf8")
        review = render(case["result"],case["bom"],directory)
        carton = result.get("envelope_candidate",result)["envelope_design"]["candidate"]
        old_carton = before.get("envelope_candidate",before)["envelope_design"]["candidate"]
        actual = math.prod(carton["external_mm"])/1e6
        reference = math.prod(case["reference_external_mm"])/1e6
        previous = math.prod(old_carton["external_mm"])/1e6
        delta = (actual/reference-1)*100
        status = "PASS: nominal volume" if actual<=reference else "NOT MET"
        rows.append(f"<tr><th>{escape(name)}</th><td>{reference:.5f}</td><td>{previous:.5f}</td><td>{actual:.5f}</td><td>{delta:+.2f}%</td><td>{status}</td></tr>")
        dims = " x ".join(f"{x:g}" for x in carton["external_mm"])
        refdims = " x ".join(f"{x:g}" for x in case["reference_external_mm"])
        clean_note = ""
        if case.get("clean_run"):
            clean = json.loads(Path(case["clean_run"]).read_bytes())
            if clean.get("status") != "validated_geometry_candidate" or not clean.get("declared_bom_complete"):
                raise ValueError("Clean-run status or declared BOM check failed")
            clean_note = (f"<p><b>Fresh search from prepared inputs:</b> {math.prod(clean['external_mm'])/1e6:.5f} L in "
                          f"{clean['total_seconds']/60:.2f} min. Source import is excluded; the two runs shared CPU time. "
                          "This run did not reproduce the smaller cached incumbent above.</p>")
        source_pdf = Path(case["reference_pdf"])
        pages = []
        with fitz.open(source_pdf) as pdf:
            for page in case["reference_pages"]:
                target = directory/f"reference-{page+1}.png"
                pdf[page].get_pixmap(matrix=fitz.Matrix(1.2,1.2)).save(target)
                pages.append(picture(target,f"Alan reference, page {page+1}"))
        stack_picture(plan,directory/"stack.png")
        views = [picture(directory/"stack.png","Exploded generated carton stack")]
        slot_numbers = {}
        for index,layer in enumerate(sorted(carton["layout"]["layers"],key=lambda l:(l["position_mm"][2],l["position_mm"][0]))):
            slots = [p for p in carton["layout"]["placements"] if p["layer_id"]==layer["id"]]
            content_rows = []
            for number,slot in enumerate(slots,1):
                members = result.get("groups",{}).get("assembly-"+slot["unit_id"],[slot["unit_id"]])
                slot_numbers.update({uid:number for uid in members})
                content_rows.append(f"<tr><td>{number}</td><td>{escape(', '.join(members))}</td></tr>")
            views.append(picture(directory/f"carton-{index+1}.png",f"Generated carton {index+1}")+
                         f"<details><summary>{escape(layer['id'])}: numbered contents</summary><table>{''.join(content_rows)}</table></details>")
        details = []
        for template in plan["templates"]:
            path = directory/(template["id"]+"-assembly.png")
            template_picture(template,path)
            steps = "".join(f"<li>Lower {escape(', '.join(s['unit_ids']))} along {escape(s['direction'])}.</li>" for s in template["packing_sequence"])
            details.append(f"<h4>{escape(template['id'])}: {len(template['copies'])} copies</h4>{picture(path,'Original group geometry and assembly order')}<ol>{steps}</ol>")
        carton_steps = []
        for layer in plan["cartons_in_outer_insertion_order"]:
            steps = "".join(f"<li>Slot {slot_numbers[s['unit_ids'][0]]}: {escape(', '.join(s['unit_ids']))} ({escape(s['direction'])}).</li>" for s in layer["packing_sequence"])
            outer = " x ".join(f"{d+2*layer['wall_mm']:g}" for d in layer["inner_mm"])
            carton_steps.append(f"<h4>{escape(layer['id'])}: closed size {outer} mm</h4><ol>{steps}</ol>")
        cards.append(f"<section><h2>{escape(name)}</h2><p><b>Generated:</b> {dims} mm, {review['cartons']} closed inner cartons; {review['units']} packing units. <b>Alan:</b> {refdims} mm.</p>{clean_note}"
                     f"<div class='comparison'><div><h3>Alan: supplied PDF</h3>{''.join(pages)}</div><div><h3>Generated: actual CAD top views</h3>{''.join(views)}</div></div>"
                     f"<details><summary>Geometric packing steps and group assembly</summary><p>Prepare the listed groups on an open workbench in numbered order. Orient each finished group as shown in its carton top view. Lower units into the open inner carton in the listed order, then close it. Put closed cartons into the outer box in the order below, preserving the configured protection and booklet space. Source IDs refer to the BOM; estimated purchased envelopes remain estimates.</p>"
                     f"{''.join(details)}<h3>Carton filling and outer insertion order</h3>{''.join(carton_steps)}</details>"
                     f"<small>Frozen result SHA-256: {sha256(raw).hexdigest()}</small></section>")
        audits.append({"name":name,"result_sha256":sha256(raw).hexdigest(),"result_fingerprint":fingerprint(result),
                       "reference_pdf_sha256":sha256(source_pdf.read_bytes()).hexdigest(),
                       "before_l":previous,"after_l":actual,"reference_l":reference,"delta_percent":delta,
                       "same_before_after_sources_and_protection":True,"nominal_volume_pass":actual<=reference,
                       "assembly_plan_status":plan["status"],"result_path":str(Path(case["result"]).resolve())})
        print(json.dumps({"case":name,"litres":actual,"status":status}),flush=True)
    html = """<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Packing: one-hour progress report</title>
<style>body{font:16px/1.5 system-ui,sans-serif;color:#1e293b;max-width:1180px;margin:32px auto;padding:0 20px}h1,h2,h3{line-height:1.2}table{border-collapse:collapse;width:100%}th,td{padding:9px;text-align:left;border-bottom:1px solid #cbd5e1}section{border-top:2px solid #334155;margin-top:32px;padding-top:10px}.comparison{display:grid;grid-template-columns:1fr 1fr;gap:20px}img{max-width:100%;height:auto}details{background:#f1f5f9;padding:16px;margin:20px 0}summary{cursor:pointer;font-weight:700}small{overflow-wrap:anywhere}li{overflow-wrap:anywhere}@media(max-width:700px){.comparison{display:block}table{font-size:12px}}@media print{details{display:block}.comparison{grid-template-columns:1fr 1fr}section{break-before:page}}</style>
<h1>Packing: one-hour progress report</h1>
<p>Complete declared kits, unchanged protection and source geometry. Both results pass BOM, original CAD, carton-wall, internal assembly and external insertion checks. The overall no-worse objective is still open.</p>
<table><tr><th>Kit</th><th>Alan, L</th><th>Before, L</th><th>After, L</th><th>vs Alan</th><th>Target</th></tr>"""+"".join(rows)+"</table>"
    html += "<p>These selected improvements start from independently generated cached results. Separate clean runs are reported in the repository progress note; do not treat replay time as cold-design time. Alan's dimensions are nominal source values. The diagrams are geometric instructions under documented purchased-part assumptions, not physical shipping qualification.</p>"
    html += "".join(cards)+"</html>"
    (output/"report.html").write_text(html,encoding="utf8")
    (output/"comparison-checks.json").write_text(json.dumps(audits,indent=2),encoding="utf8")
    return output/"report.html"


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(render_comparison(args.config,args.output))
