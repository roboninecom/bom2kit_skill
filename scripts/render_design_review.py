"""Render original source geometry by generated inner carton; not a production instruction."""
import argparse
from collections import Counter
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from bom2kit.solid_views import render_solid_views
from bom2kit.bom import reconcile_bom
from bom2kit.layered_design import validate_layered
from bom2kit.mesh_validation import validate_mesh_layout


def render(result_path,bom_path,output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from matplotlib.patches import Rectangle
    import numpy as np
    import trimesh

    raw = Path(result_path).read_bytes()
    result = json.loads(raw)
    if result.get("status") not in ("validated_grouped_geometry","validated_mesh_envelope_baseline"):
        raise ValueError("A selected verified design is required")
    envelope = result.get("envelope_candidate",result)
    carton = envelope["envelope_design"]["candidate"]
    if result["input"]["container"] != carton["input"]["container"]:
        raise ValueError("Mesh and carton containers differ")
    bom_raw = Path(bom_path).read_bytes()
    coverage = reconcile_bom(json.loads(bom_raw),result["input"])
    geometry = validate_mesh_layout(result["input"],result["layout"])
    hierarchy = validate_layered(carton["input"],carton["layout"])
    if not coverage["complete"] or not geometry["valid"] or not hierarchy["valid"]:
        raise ValueError("BOM, geometry and hierarchy must all pass fresh checks")
    items = {i["id"]:i for i in result["input"]["items"]}
    shapes = {}
    for iid,item in items.items():
        data = json.loads(Path(item["mesh"]["path"]).read_text())
        shapes[iid] = trimesh.Trimesh(data["vertices_mm"],data["triangles"],process=False)
    meshes = {}
    for pose in result["layout"]["placements"]:
        mesh = shapes[pose["item_id"]].copy()
        mesh.apply_transform(pose["transform"])
        meshes[pose["unit_id"]] = mesh
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    groups = result.get("groups",{})
    seen, sections = [],[]
    for index,layer in enumerate(sorted(carton["layout"]["layers"],key=lambda l:(l["position_mm"][2],l["position_mm"][0]))):
        origin = np.asarray(layer["position_mm"])+layer["wall_mm"]
        upper = origin+np.asarray(layer["inner_mm"])
        slots = [p for p in carton["layout"]["placements"] if p["layer_id"]==layer["id"]]
        fig,ax = plt.subplots(figsize=(8,6))
        triangles,depths,colors = [],[],[]
        rows = []
        solid_parts = []
        for number,slot in enumerate(slots,1):
            members = groups.get("assembly-"+slot["unit_id"],[slot["unit_id"]])
            seen.extend(members)
            color = plt.get_cmap("tab20")((number-1)%20)
            for uid in members:
                mesh = meshes[uid]
                if np.any(mesh.bounds[0]<origin-1e-6) or np.any(mesh.bounds[1]>upper+1e-6):
                    raise ValueError("Original source part lies outside its assigned inner carton")
                local_mesh = mesh.copy()
                local_mesh.apply_translation(-origin)
                solid_parts.append((local_mesh, number))
                faces = mesh.triangles-origin
                triangles.append(faces[:,:,[0,1]])
                depths.append(faces[:,:,2].mean(axis=1))
                colors.extend([color]*len(faces))
            p = np.asarray(slot["position_mm"])-origin
            dx,dy = slot["dimensions_mm"][:2]
            ax.add_patch(Rectangle(p[:2],dx,dy,fill=False,edgecolor="#555555",linewidth=.45,linestyle="--",zorder=3))
            ax.text(p[0]+dx/2,p[1]+dy/2,str(number),ha="center",va="center",fontsize=8,
                    bbox={"facecolor":"white","alpha":.85,"edgecolor":"none","pad":1},zorder=4)
            rows.append(f"<tr><td>{number}</td><td>{escape(', '.join(members))}</td></tr>")
        order = np.argsort(np.concatenate(depths),kind="stable")
        ax.add_collection(PolyCollection(np.concatenate(triangles)[order],facecolors=np.asarray(colors)[order],edgecolors="none"))
        width,depth,height = layer["inner_mm"]
        ax.set(xlim=(0,width),ylim=(0,depth),aspect="equal",xlabel="X (mm)",ylabel="Y (mm)")
        ax.set_title(f"{layer['id']}: cavity {width:g} x {depth:g} x {height:g} mm")
        fig.tight_layout()
        filename=f"carton-{index+1}.png"
        fig.savefig(output/filename,dpi=150)
        plt.close(fig)
        render_solid_views(solid_parts, output/f"carton-{index+1}-solid.png",
                           title=f"{layer['id']}: {width:g} x {depth:g} x {height:g} mm cavity",
                           cavity=layer["inner_mm"], wall=layer["wall_mm"])
        outside = " x ".join(f"{d+2*layer['wall_mm']:g}" for d in layer["inner_mm"])
        sections.append(f"<section><h2>{escape(layer['id'])}</h2><p>External: {outside} mm. Wall: {layer['wall_mm']:g} mm.</p>"
                        f"<img src='carton-{index+1}-solid.png' alt='Shaded original CAD cutaway and numbered top view'><details><summary>Contents by numbered slot</summary>"
                        f"<table><tr><th>Slot</th><th>Original units</th></tr>{''.join(rows)}</table></details></section>")
    if Counter(seen) != Counter(meshes.keys()):
        raise ValueError("Diagram membership does not cover each original unit exactly once")
    audit = {"result_sha256":sha256(raw).hexdigest(),"bom_sha256":sha256(bom_raw).hexdigest(),
             "bom":coverage,"mesh":geometry,"hierarchy":hierarchy,"diagram_unit_coverage":True,
             "scope":"Geometric carton review; assembly instructions and transport qualification are not certified by this report"}
    (output/"review-checks.json").write_text(json.dumps(audit,indent=2))
    dimensions = " x ".join(f"{d:g}" for d in carton["external_mm"])
    html = f"""<!doctype html><meta charset='utf-8'><title>Independent packing review</title>
<style>body{{font:16px system-ui;max-width:1000px;margin:32px auto;color:#18202a}}section{{break-inside:avoid;border-top:1px solid #ccc;margin-top:24px}}img{{max-width:100%;width:800px}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:6px;text-align:left}}small{{overflow-wrap:anywhere}}</style>
<h1>Independent packing review</h1><p><b>{dimensions} mm · {carton['volume_mm3']/1e6:.6f} L</b></p>
<p>{len(meshes)} packing units. Fresh BOM, source geometry, carton hierarchy and diagram membership checks pass.</p>
<p>Shaded views show original triangles in their validated poses. Two camera-facing walls are omitted in the cutaway. Slot numbers match the contents list. Purchased envelopes may be estimates.
This is a geometric review, not a production packing instruction or a transport test.</p>
<small>Frozen result SHA256: {audit['result_sha256']}</small>{''.join(sections)}"""
    (output/"review.html").write_text(html,encoding="utf8")
    return {"output":str(output/"review.html"),"cartons":len(sections),"units":len(meshes)}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result",type=Path)
    parser.add_argument("bom",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(render(args.result,args.bom,args.output)))
