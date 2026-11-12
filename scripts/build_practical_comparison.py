"""Replay frozen results and render a concise CAD comparison in PDF and HTML."""
import argparse
import base64
from hashlib import sha256
from html import escape
import json
import math
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bom2kit.assembly_plan import build_assembly_plan
from bom2kit.mesh_validation import validate_mesh_layout
from bom2kit.practical_validation import complexity_metrics
from bom2kit.transport_validation import validate_transport
from bom2kit.packing_illustrations import exploded_scene,render_scene
from build_visual_packing_guide import load_geometry


def dimensions(values):
    return ' x '.join(f'{v:g}' for v in values)


def render(config_path,output):
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph,Table,TableStyle
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4,landscape
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
    config=json.loads(Path(config_path).read_text(encoding='utf-8-sig'))
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    pdf=canvas.Canvas(str(output/'comparison.pdf'),pagesize=landscape(A4))
    width,height=landscape(A4);margin=24;available=width-2*margin
    style=ParagraphStyle('note',fontName='Helvetica',fontSize=8,leading=11,textColor=colors.HexColor('#334155'))
    records=[];sections=[]
    for case in config['cases']:
        print(json.dumps({'stage':'comparison_replay','kit':case['kit']}),flush=True)
        directory=output/case['kit'];directory.mkdir(exist_ok=True)
        before=json.loads(Path(case['before_result']).read_bytes());after=json.loads(Path(case['after_result']).read_bytes())
        expected=json.loads(Path(case['bom']).read_bytes())
        if sorted(before['input']['items'],key=lambda i:i['id'])!=sorted(after['input']['items'],key=lambda i:i['id']):
            raise ValueError('Before/after source manifests must match exactly')
        protection=lambda r:{k:v for k,v in r['logistics']['policy'].items() if k in ('carton','item_padding_mm','clearance_mm','families')}
        if protection(before)!=protection(after):raise ValueError('Before/after protection or family policy differs')
        if 'practical' not in after:raise ValueError('A practical candidate is required')
        images=[];metrics=[];plans=[];checks=[]
        for label,result in (('before',before),('after',after)):
            geometry=validate_mesh_layout(result['input'],result['layout'])
            transport=validate_transport(result,result['logistics']['policy'])
            if not geometry['valid'] or not transport['valid']:raise ValueError(f'{label} geometry/transport failed')
            plan=build_assembly_plan(result,expected);plans.append(plan)
            metrics.append(complexity_metrics(result))
            (directory/(label+'-assembly-plan.json')).write_text(json.dumps(plan,indent=2),encoding='utf8')
            _,meshes=load_geometry(result)
            modules=[next(m for m in result['logistics']['modules'] if m['id']==entry['id']) for entry in plan['cartons_in_outer_insertion_order']]
            scene,labels,_=exploded_scene(result,modules,meshes)
            image=directory/(label+'.png');render_scene(scene,image,labels=labels,size=(1000,1200),trim=True)
            images.append(image);checks.append({'geometry':geometry['valid'],'transport':transport['valid'],'assembly':plan['status']})
        reference=case['reference'];reference_image=Path(reference['image']).resolve()
        images.append(reference_image)
        ref_volume=math.prod(reference['external_mm'])/1e6
        delta=(metrics[1]['external_volume_l']/ref_volume-1)*100
        status='Nominal volume target met' if delta<=0 else 'Volume target NOT MET'
        exterior=[plans[0]['outer_external_mm'],plans[1]['outer_external_mm'],reference['external_mm']]
        after_seconds=None
        if case.get('after_run'):
            run=json.loads(Path(case['after_run']).read_bytes());after_seconds=run.get('seconds')
        rows=[['Metric','Before: matching current inputs','After: practical candidate','Alan: illustrated reference'],
              ['Exterior, mm',*[dimensions(v) for v in exterior]],
              ['Shipping volume, L',*[f"{m['external_volume_l']:.3f}" for m in metrics],f'{ref_volume:.3f}'],
              ['Inner cartons / sizes',*[f"{m['cartons']} / {m['carton_types']}" for m in metrics],f"{reference.get('cartons','Unknown')} / not audited"],
              ['Source + compound placements',*[str(m['total_counted_placements']) for m in metrics],'Not counted'],
              ['Contact sheets / floor liners',
               f"{metrics[0]['protective_sheet_placements']} / {metrics[0]['floor_liner_placements']}" if 'practical' in before else 'Not specified',
               f"{metrics[1]['protective_sheet_placements']} / {metrics[1]['floor_liner_placements']}",'Not counted'],
              ['Compound copies / templates',*[f"{m['compound_preassemblies']} / {m['compound_templates']}" for m in metrics],'Not audited'],
              ['Actual support / finger replay','Not checked by old engine','Pass / pass','Not replayed'],
              ['Recorded run, seconds',str(case.get('before_seconds','Not recorded')),f'{after_seconds:.1f}' if after_seconds is not None else 'Partial run; see audit','Not measured']]
        pdf.setFillColor(colors.HexColor('#0f172a'));pdf.setFont('Helvetica-Bold',18)
        pdf.drawString(margin,height-32,case['kit']+' | Practical packing comparison')
        pdf.setFont('Helvetica-Bold',10);pdf.setFillColor(colors.HexColor('#9a3412') if delta>0 else colors.HexColor('#166534'))
        pdf.drawString(margin,height-50,f'{status}: {delta:+.1f}% versus Alan. Complete matching before/after source BOM.')
        column=available/3
        captions=['Before: original CAD','After: original CAD',reference.get('label','Alan: supplied reference')]
        for index,(image,caption) in enumerate(zip(images,captions)):
            x=margin+index*column
            pdf.setFillColor(colors.HexColor('#334155'));pdf.setFont('Helvetica-Bold',9)
            pdf.drawString(x+4,height-69,caption)
            pdf.drawImage(ImageReader(str(image)),x+4,282,width=column-8,height=height-362,preserveAspectRatio=True,anchor='c',mask='auto')
        table=Table(rows,colWidths=[160]+[(available-160)/3]*3,rowHeights=16)
        table.setStyle(TableStyle([('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),
                                   ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e2e8f0')),
                                   ('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#cbd5e1')),
                                   ('TEXTCOLOR',(0,0),(-1,-1),colors.HexColor('#0f172a')),
                                   ('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
        _,table_height=table.wrap(available,200);table.drawOn(pdf,margin,278-table_height)
        spec=after['logistics']['policy']['carton'];grip=after['practical']['hand_access']['parameters']
        notes=[
            'Gray = source CAD; tan = declared factory carton; blue = packet; purple = declared envelope, not an extra box. Views use independent camera scales.',
            f"Before/after keep the same sources, {spec['protection_mm']:g} mm six-face foam, {spec['wall_mm']:g} mm outer wall, {spec['inner_wall_mm']:g} mm inner walls and declared part protection. Finger model: {grip['radius_mm']:g} mm radius, up to {grip['insertion_depth_mm']:g} mm engagement, vertical paths.",
            'Placements are counted operations, not measured labor. Carton forming, closure, outer insertion and protective material handling add work. Purchased dimensions, strength and shipping restraint remain unqualified.',
            'Run times use prepared source meshes; practical runs reuse the stable-pose cache and may share CPU time. They are not a controlled speed comparison.',
            case.get('note','')]
        paragraph=Paragraph('<br/>'.join(escape(n) for n in notes if n),style)
        _,ph=paragraph.wrap(available,100);paragraph.drawOn(pdf,margin,278-table_height-8-ph)
        pdf.setFont('Helvetica',7);pdf.drawString(margin,14,'Computational draft. No physical transport qualification. Evidence and hashes: comparison.json.')
        pdf.showPage()
        hashes={label:sha256(Path(case[key]).read_bytes()).hexdigest() for label,key in [('before','before_result'),('after','after_result'),('bom','bom')]}
        record={'kit':case['kit'],'metrics':{'before':metrics[0],'after':metrics[1]},'reference':reference,
                'reference_l':ref_volume,'delta_percent':delta,'nominal_volume_target_met':delta<=0,
                'same_before_after_sources_and_protection':True,'checks':checks,'file_sha256':hashes,
                'reference_image_sha256':sha256(reference_image.read_bytes()).hexdigest(),
                'illustration_sha256':{label:sha256(path.read_bytes()).hexdigest() for label,path in zip(('before','after','reference'),images)},
                'after_seconds':after_seconds,'note':case.get('note'),'physical_qualification':False}
        records.append(record)
        def picture(path):return 'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()
        figures=''.join(f'<figure><img src="{picture(p)}" alt="{escape(c)}"><figcaption>{escape(c)}</figcaption></figure>' for p,c in zip(images,captions))
        table_html='<table>'+''.join('<tr>'+''.join(f'<td>{escape(str(cell))}</td>' for cell in row)+'</tr>' for row in rows)+'</table>'
        sections.append(f'<section><h2>{escape(case["kit"])}</h2><p><b>{status}: {delta:+.1f}% versus Alan.</b></p><div class="images">{figures}</div>{table_html}'+''.join(f'<p>{escape(n)}</p>' for n in notes if n)+'</section>')
    pdf.save()
    (output/'comparison.json').write_text(json.dumps(records,indent=2),encoding='utf8')
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Practical packing comparison</title><style>body{font:15px/1.5 system-ui;color:#172033;max-width:1300px;margin:24px auto;padding:20px}h1,h2{line-height:1.2}.images{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}figure{margin:0}img{width:100%;height:420px;object-fit:contain}table{border-collapse:collapse;width:100%}td{padding:8px;border-bottom:1px solid #cbd5e1}tr:first-child{background:#e2e8f0;font-weight:600}section{margin:32px 0 50px}p{max-width:1100px}@media(max-width:700px){.images{grid-template-columns:1fr}table{font-size:11px}}</style><h1>Practical packing: measured comparison</h1><p>Frozen layouts, independent replay and unchanged before/after inputs. Nominal reference volumes are evaluation data only.</p>'''+''.join(sections)+'</html>'
    (output/'report.html').write_text(html,encoding='utf8')
    print(json.dumps({'output':str(output),'nominal_target_met':all(r['nominal_volume_target_met'] for r in records)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('config',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();render(args.config,args.output)
