"""Evaluate frozen transport results against prior layouts and separate references."""
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
from bom2kit.carton_tiling import carton_size_key
from render_transport_review import render_transport


def signature(result):
    return sorted([(i["id"],i["quantity"],i["mesh"]["sha256"],i.get("contents"),i.get("revision"),i.get("contents_revisions"))
                   for i in result["input"]["items"]],key=lambda row:row[0])


def metrics(result):
    candidate=result.get("envelope_candidate",result)["envelope_design"]["candidate"]
    layers=candidate["layout"]["layers"]
    sizes=[tuple(v+2*layer["wall_mm"] for v in layer["inner_mm"]) for layer in layers]
    return {"external_mm":candidate["external_mm"],"volume_l":math.prod(candidate["external_mm"])/1e6,
            "cartons":len(layers),"types":len({carton_size_key(size) for size in sizes})}


def check_comparable(before,after):
    if signature(before)!=signature(after):raise ValueError("Before/after source geometry or quantities differ")
    for field in ("wall_mm","protection_mm","reserved_top_mm"):
        if before["input"]["container"].get(field)!=after["input"]["container"].get(field):
            raise ValueError("Before/after protection differs")
    # Family assignments may deliberately change; physical allowances may not.
    if "logistics" in before and "logistics" in after:
        old,new=before["logistics"]["policy"],after["logistics"]["policy"]
        for field in ("item_padding_mm","clearance_mm"):
            if old.get(field)!=new.get(field):raise ValueError(f"Before/after {field} differs")
        for field in ("inner_wall_mm","gap_mm","dimension_increment_mm"):
            if old["carton"].get(field)!=new["carton"].get(field):raise ValueError(f"Before/after {field} differs")


def compare(config_path,output):
    config=json.loads(Path(config_path).read_bytes());output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    records=[];sections=[]
    def picture(path):
        return "data:image/png;base64,"+base64.b64encode(Path(path).read_bytes()).decode()
    for case in config["cases"]:
        name=case["name"]
        if not name.isalnum():raise ValueError("Alphanumeric case names required")
        after_raw=Path(case["result"]).read_bytes();after=json.loads(after_raw)
        before_raw=Path(case["before_result"]).read_bytes();before=json.loads(before_raw);bom=json.loads(Path(case["bom"]).read_bytes())
        check_comparable(before,after)
        build_assembly_plan(before,bom)
        directory=output/name
        render_transport(case["result"],case["bom"],directory)
        old,new=metrics(before),metrics(after)
        reference={"external_mm":case["reference_external_mm"],"volume_l":math.prod(case["reference_external_mm"])/1e6,
                   "cartons":case.get("reference_cartons"),"types":case.get("reference_types")}
        passed=new["volume_l"]<=reference["volume_l"]+1e-9
        delta=100*(new["volume_l"]/reference["volume_l"]-1)
        record={"case":name,"before":old,"after":new,"reference":reference,"volume_pass":passed,
                "delta_vs_reference_percent":delta,"same_sources_and_protection":True,
                "after_seconds":after["search"]["total_seconds"],"after_result_sha256":sha256(after_raw).hexdigest(),
                "physical_qualification":False,"reference_original_geometry_replayed":False}
        record["engine_files_unchanged_during_run"]=after.get("run_provenance",{}).get("engine_files_unchanged_during_run")
        record["before_engine_files_unchanged_during_run"]=before.get("run_provenance",{}).get("engine_files_unchanged_during_run")
        provenance_note=("Engine files remained unchanged during this run."
                         if record["engine_files_unchanged_during_run"] is True else
                         "Exploratory result: engine files changed during the run. The frozen layout is rechecked here, but this is not a frozen-code reproduction.")
        if record["before_engine_files_unchanged_during_run"] is False:
            provenance_note+=" The before layout is an exploratory changed-code run, independently replayed here."
        if before.get("revision_replay"):
            record["before_revision_replay"]=before["revision_replay"]
        records.append(record)
        rows=[]
        for label,value in (("Before",old),("After",new),("Alan reference",reference)):
            dimensions=" x ".join(f"{d:g}" for d in value["external_mm"])
            rows.append(f"<tr><td>{label}</td><td>{dimensions}</td><td>{value['volume_l']:.3f}</td>"
                        f"<td>{value['cartons'] if value['cartons'] is not None else 'Not verified'}</td>"
                        f"<td>{value['types'] if value['types'] is not None else 'Not verified'}</td></tr>")
        reference_image=""
        before_image=""
        if case.get("before_review"):
            before_review=Path(case["before_review"])
            binding=json.loads((before_review/"transport-checks.json").read_bytes())
            if binding["result_sha256"]!=sha256(before_raw).hexdigest():raise ValueError("Before illustration does not match the frozen before result")
            path=before_review/"outer-cutaway.png"
            before_image=f"<figure><img src='{picture(path)}'><figcaption>Before: previous transport carton block</figcaption></figure>"
            record["before_image_sha256"]=sha256(path.read_bytes()).hexdigest()
        if case.get("reference_image"):
            caption=case.get("reference_caption","Alan: supplied reference illustration")
            reference_image=f"<figure><img src='{picture(case['reference_image'])}'><figcaption>{escape(caption)}</figcaption></figure>"
            record["reference_caption"]=caption
            record["reference_image_sha256"]=sha256(Path(case["reference_image"]).read_bytes()).hexdigest()
        sections.append(f"<section><h2>SO-ARM{name}: {'volume target met' if passed else 'volume target NOT met'}</h2>"
                        f"<table><tr><th>Design</th><th>Exterior, mm</th><th>Litres</th><th>Cartons</th><th>Sizes</th></tr>{''.join(rows)}</table>"
                        f"<p>After vs Alan: {delta:+.1f}%. Search and verification: {record['after_seconds']:.1f} s. "
                        f"Complete matching source BOM and unchanged protection; compatibility and no-spacer block checks pass.</p><p>{provenance_note}</p>"
                        f"<div class='pair'>{before_image}<figure><img src='{picture(directory/'outer-cutaway.png')}'><figcaption>After: exact generated carton/foam geometry</figcaption></figure>{reference_image}</div>"
                        f"<p><a href='{name}/transport-review.html'>Contents, original CAD views, assembly order and foam panels</a></p></section>")
        carton_images="".join(f"<figure><img src='{picture(directory/f'carton-{i}-solid.png')}'><figcaption>Carton {i}: original CAD / declared purchased envelopes</figcaption></figure>" for i in range(1,new["cartons"]+1))
        sections.append(f"<details><summary>All {new['cartons']} internal carton CAD views</summary>{carton_images}</details>")
        if before.get("revision_replay"):
            sections.append("<p>The before layout was replayed on the current CAD revision without changing its packing coordinates. Original geometry, slot bounds and assembly were rechecked.</p>")
    (output/"comparison.json").write_text(json.dumps(records,indent=2),encoding="utf8")
    verdict="Both nominal volume targets met" if all(r["volume_pass"] for r in records) else "The requested no-worse target is not achieved"
    html=f"""<!doctype html><meta charset='utf-8'><title>Transport packaging comparison</title>
<style>body{{font:16px system-ui;max-width:1200px;margin:30px auto;color:#18202a}}table{{border-collapse:collapse;width:100%}}td,th{{padding:9px;border-bottom:1px solid #ddd;text-align:left}}section{{margin-top:32px;border-top:2px solid #ddd}}.pair{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));align-items:start}}figure{{margin:10px}}img{{max-width:100%}}figcaption{{font-size:14px}}@media(max-width:800px){{.pair{{display:block}}}}</style>
<h1>Transport packaging: before / after / Alan</h1><p><b>{verdict}.</b></p>
<p>After: compatible groups, bounded carton count and sizes, six-face protective foam and a nominally complete inner-carton block without spacers. Full source quantities and original CAD are checked.</p>
<p>Illustrations use separate display scales; compare the stated exterior dimensions and volumes.</p>
<p>Physical restraint, cushioning, material strength and manufacturing tolerances remain unqualified. The Alan volume is a supplied independent benchmark; its complete original placement geometry was not replayed here. No reference dimensions or placements enter the search.</p>
{''.join(sections)}<h2>Comparison limits</h2><p>Before is the previously frozen computational layout, not a transport-qualified design. Alan's engineering time and the frozen before-layout search time are not measured here. No supplier costs or physical test results are invented. Purchased-envelope estimates remain in force.</p>"""
    (output/"report.html").write_text(html,encoding="utf8")
    return {"report":str(output/"report.html"),"both_volume_targets_met":all(r["volume_pass"] for r in records)}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("config",type=Path)
    parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    print(json.dumps(compare(args.config,args.output)))
