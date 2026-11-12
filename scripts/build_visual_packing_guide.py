"""Create an R3-style illustrated packing PDF from a checked transport result."""
import argparse
from collections import Counter
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bom2kit.assembly_plan import build_assembly_plan
from bom2kit.transport_validation import validate_transport
from bom2kit.packing_illustrations import render_scene,carton_shell,cuboid,exploded_scene,PART,CARTON,FOAM,state_color
from bom2kit.packing_states import declared_state
from bom2kit.report import fingerprint


def name(item):
    return str(item.get('name') or item.get('source_name') or item.get('source_evidence',{}).get('source_item') or item['id'])


def bound_property_cards(result,properties_path=None):
    if properties_path is None:return {}
    properties=json.loads(Path(properties_path).read_bytes())
    if properties.get('source_library_fingerprint')!=result.get('source_library_sha256'):
        raise ValueError('Property cards do not match the frozen source library')
    if fingerprint(properties)!=result.get('concept',{}).get('properties_fingerprint'):
        raise ValueError('Property cards do not match the selected concept')
    if set(properties['cards'])!={i['id'] for i in result['input']['items']}:
        raise ValueError('Property cards must cover every source SKU')
    return properties['cards']


def check_manual_materials(result):
    """Recompute the declared cutting screen; never trust a stored pass flag."""
    from bom2kit.concept_patterns import manual_pattern_screen
    declared=result.get('concept',{}).get('manual_material_screen',{})
    checked=manual_pattern_screen(result.get('practical',{}),declared.get('minimum_contact_sheet_side_mm',10.))
    if declared.get('valid') is False or not checked['valid']:
        raise ValueError('Failed manual-material screen: use a diagnostic mesh report instead of an operator guide')
    return checked


def load_geometry(result):
    import trimesh
    sources={}
    for item in result['input']['items']:
        raw=Path(item['mesh']['path']).read_bytes()
        if sha256(raw).hexdigest()!=item['mesh']['sha256']:raise ValueError('Source changed before illustration')
        data=json.loads(raw);sources[item['id']]=trimesh.Trimesh(data['vertices_mm'],data['triangles'],process=False)
    meshes={}
    for pose in result['layout']['placements']:
        mesh=sources[pose['item_id']].copy();mesh.apply_transform(pose['transform']);meshes[pose['unit_id']]=mesh
    return sources,meshes


def carton_records(result,plan):
    """One shared numbering scheme for drawings, contents and insertion steps."""
    candidate=result['envelope_design']['candidate'];records=[];seen=[]
    poses={p['unit_id']:p for p in result['layout']['placements']}
    for index,entry in enumerate(plan['cartons_in_outer_insertion_order'],1):
        module=next(m for m in result['logistics']['modules'] if m['id']==entry['id'])
        layer=next(l for l in candidate['layout']['layers'] if l['id']==entry['id'])
        slots=[];mapping={}
        for number,slot in enumerate([p for p in candidate['layout']['placements'] if p['layer_id']==entry['id']],1):
            members=result.get('groups',{}).get('assembly-'+slot['unit_id'],[slot['unit_id']])
            slots.append({'number':number,'members':members,'pose':slot})
            mapping.update({uid:number for uid in members});seen.extend(members)
        counts=Counter(poses[uid]['item_id'] for slot in slots for uid in slot['members'])
        item_slots={iid:sorted({s['number'] for s in slots if any(poses[uid]['item_id']==iid for uid in s['members'])}) for iid in counts}
        order=[sorted({mapping[uid] for uid in step['unit_ids']}) for step in entry['packing_sequence']]
        records.append({'number':index,'module':module,'layer':layer,'slots':slots,'counts':counts,'item_slots':item_slots,'order':order,
                        'operator_steps':entry.get('operator_steps',[]),'unit_to_slot':mapping})
    if Counter(seen)!=Counter(poses.keys()):raise ValueError('Illustrated cartons must cover every original unit exactly once')
    return records


def build(result_path,bom_path,output,*,kit='Kit',revision='Draft 1',properties_path=None):
    import numpy as np
    from reportlab.pdfgen import canvas
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Image,Table,TableStyle,PageBreak,KeepTogether
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from matplotlib import font_manager

    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    raw=Path(result_path).read_bytes();bom_raw=Path(bom_path).read_bytes()
    result=json.loads(raw);bom=json.loads(bom_raw)
    material_screen=check_manual_materials(result)
    property_cards=bound_property_cards(result,properties_path)
    from bom2kit.part_properties import check_accessory_set_cohesion,describe_parts
    cohesion_cards=property_cards or describe_parts(result['input'],result['logistics']['policy'])['cards']
    property_cards=cohesion_cards
    cohesion_screen=check_accessory_set_cohesion(result,cohesion_cards)
    if not cohesion_screen['valid']:
        raise ValueError('An accessory set is split between cartons; retain this result as diagnostic only')
    checks=validate_transport(result,result['logistics']['policy'])
    if not checks['valid']:raise ValueError(checks['errors'])
    plan=build_assembly_plan(result,bom)
    sources,meshes=load_geometry(result);records=carton_records(result,plan)
    items={i['id']:i for i in result['input']['items']}
    assets=output/'illustrations';assets.mkdir(exist_ok=True)
    def illustrate(*args,**kwargs):return render_scene(*args,trim=True,**kwargs)
    scene,labels,offsets=exploded_scene(result,[r['module'] for r in records],meshes)
    illustrate(scene,assets/'outer-exploded.png',labels=labels,size=(1300,1700))
    thumbnails={}
    for number,(iid,mesh) in enumerate(sources.items(),1):
        path=assets/f'part-{number}.png'
        illustrate([(mesh,state_color(items[iid]))],path,size=(360,260));thumbnails[iid]=path
    uid_items={p['unit_id']:items[p['item_id']] for p in result['layout']['placements']}
    for record in records:
        n=record['number'];layer=record['layer'];origin=np.asarray(layer['position_mm'])+layer['wall_mm']
        parts=[];slot_labels=[]
        for slot in record['slots']:
            local=[]
            for uid in slot['members']:
                mesh=meshes[uid].copy();mesh.apply_translation(-origin);parts.append((mesh,state_color(uid_items[uid])));local.append(mesh)
            bounds=np.asarray([m.bounds for m in local]);center=(bounds[:,0].min(0)+bounds[:,1].max(0))/2
            center[2]=layer['inner_mm'][2]+2;slot_labels.append((str(slot['number']),center))
        shell=carton_shell([-layer['wall_mm']]*3,record['module']['external_mm'],layer['wall_mm'],cutaway=True)
        for panel in [*result.get('practical',{}).get('floor_liners',[]),*result.get('practical',{}).get('protective_separators',[])]:
            if panel['carton_id']==layer['id']:
                parts.append((cuboid(np.asarray(panel['origin_mm'])-origin,panel['dimensions_mm']),FOAM))
        illustrate(parts+shell,assets/f'box-{n}-iso.png',size=(1400,800))
        illustrate(parts+shell,assets/f'box-{n}-top.png',view='top',labels=slot_labels,size=(1000,750))
        illustrate(parts,assets/f'box-{n}-side.png',view='side',size=(1000,750))
    # Workbench views preserve each certified internal group frame.
    template_images={}
    for index,template in enumerate(plan['templates'],1):
        parts=[];labels=[]
        sequence=[uid for step in template['packing_sequence'] for uid in step['unit_ids']]
        for pose in template['workbench_layout']['placements']:
            mesh=sources[pose['item_id']].copy();mesh.apply_transform(pose['transform']);parts.append((mesh,state_color(items[pose['item_id']])) )
            labels.append((str(sequence.index(pose['unit_id'])+1),mesh.bounds.mean(0)))
        path=assets/f'group-{index}.png';illustrate(parts,path,labels=labels,size=(700,450));template_images[template['id']]=path
    outer=result['envelope_design']['candidate']['external_mm']
    illustrate([(cuboid([0,0,0],outer),CARTON)],assets/'closed-carton.png',labels=[(kit,np.array(outer)*[.5,0,.5])],size=(1100,750))

    pdfmetrics.registerFont(TTFont('Guide',font_manager.findfont('DejaVu Sans')))
    pdfmetrics.registerFont(TTFont('GuideBold',font_manager.findfont(font_manager.FontProperties(family='DejaVu Sans',weight='bold'))))
    pdfmetrics.registerFontFamily('Guide',normal='Guide',bold='GuideBold',italic='Guide',boldItalic='GuideBold')
    styles=getSampleStyleSheet()
    for key in ('Normal','BodyText'):styles[key].fontName='Guide';styles[key].fontSize=9;styles[key].leading=13
    styles.add(ParagraphStyle('TitleGuide',fontName='GuideBold',fontSize=17,leading=22,spaceAfter=7))
    styles.add(ParagraphStyle('SubGuide',fontName='GuideBold',fontSize=11,leading=15,spaceAfter=6,spaceBefore=7))
    styles.add(ParagraphStyle('SmallGuide',fontName='Guide',fontSize=7.5,leading=10,textColor=colors.HexColor('#59636d')))
    styles.add(ParagraphStyle('CellGuide',fontName='Guide',fontSize=8,leading=10))
    W,H=A4;margin=32;width=W-2*margin
    def P(text,style='BodyText'):return Paragraph(text,styles[style])
    def pic(path,w,h):
        from PIL import Image as PILImage
        iw,ih=PILImage.open(path).size;scale=min(w/iw,h/ih)
        return Image(str(path),width=iw*scale,height=ih*scale)
    def dims(values):return ' x '.join(f'{v:g}' for v in values)
    def table(rows,widths,compact=False):
        t=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7edf3')),
                              ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f7f9')]),
                              ('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#d7dfe6')),('LEFTPADDING',(0,0),(-1,-1),7),
                              ('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),3 if compact else 6),('BOTTOMPADDING',(0,0),(-1,-1),3 if compact else 6)]))
        return t
    flow=[P('Where each box goes','TitleGuide'),P(f'{escape(kit)} | Visual packing guide | {escape(revision)}','SmallGuide'),Spacer(1,8)]
    levels=sorted({r['module']['position_mm'][2] for r in records})
    steps=['Prepare and close the numbered inner boxes using the following sheets.','Fit the bottom and four side foam panels in the outer carton.']
    for i,z in enumerate(levels,1):
        numbers=', '.join(str(r['number']) for r in records if r['module']['position_mm'][2]==z)
        steps.append(f'Insert level {i}: boxes {numbers}, in that order.')
    steps.append('Fit the foam lid and close the outer carton.')
    for i,step in enumerate(steps,1):flow.append(P(f'<b>{i}.</b> {step}'))
    flow.extend([Spacer(1,5),P(f'Exterior: {dims(outer)} mm | {np.prod(outer)/1e6:.3f} L | {len(records)} inner boxes','SmallGuide')])
    legend=[P('Colors: gray = source CAD; tan = factory carton; blue = protective packet; purple = declared envelope, not an extra box. Foam is pale gray. Shapes and dimensions are retained from the source evidence.','SmallGuide'),
                 P('Exploded display only: gaps are not packing clearances. Front/right walls are cut down and lids hidden; rear walls retain their specified height. Close all inner boxes before insertion.','SmallGuide'),
                 Spacer(1,5),P('Geometric draft. Source quantities and geometry checked; physical restraint and transport release still require a prototype.','SmallGuide')]
    # Reserve measured text height: a tall stack must not push only its legend
    # onto an otherwise empty page. Frame padding and paragraph spacing count.
    text_height=sum(f.wrap(width-12,H)[1]+f.getSpaceBefore()+f.getSpaceAfter() for f in [*flow,*legend])
    image_height=min(505,max(180,H-30-44-12-text_height-8))
    flow.extend([pic(assets/'outer-exploded.png',width,image_height),*legend])
    template_for_unit={uid:t['id'] for t in plan['templates'] for copy in t['copies'] for uid in copy['unit_mapping'].values()}
    for r in records:
        n=r['number'];label=result['logistics']['policy'].get('family_labels',{}).get(r['module']['family'],r['module']['family'])
        label=label.replace('Factory-boxed servos, protected electronics and cables','Protected servos, electronics and cables')
        compact_views=len(r['counts'])<=8
        flow.extend([PageBreak(),P(f'Box {n}: how the parts sit','TitleGuide'),P(escape(label)),
                     P(f'Outside {dims(r["module"]["external_mm"])} mm | Cavity {dims(r["layer"]["inner_mm"])} mm','SmallGuide'),
                     pic(assets/f'box-{n}-iso.png',width,200 if compact_views else 245),P('Isometric - rear walls full height; front/right walls cut; lid omitted','SmallGuide')])
        view_height=140 if compact_views else 180
        views=Table([[pic(assets/f'box-{n}-top.png',width/2-8,view_height),pic(assets/f'box-{n}-side.png',width/2-8,view_height)],
                     [P('Top - numbered slots','SmallGuide'),P('Side - carton walls omitted','SmallGuide')]],colWidths=[width/2]*2)
        flow.extend([views,Spacer(1,8)])
        order=' / '.join(', '.join(map(str,s)) for s in r['order'])
        flow.append(P(f'<b>Insertion order (slots):</b> {order}.'))
        sheets=[s for s in result.get('practical',{}).get('protective_separators',[]) if s['carton_id']==r['layer']['id']]
        if sheets:
            flow.append(P('Protective sheets: place each after its lower slot and before its upper slot. These are counted materials inside a box, not fillers between boxes. Sheet handling and material strength require a prototype.','SmallGuide'))
            rows=[[P('<b>After slot</b>','CellGuide'),P('<b>Before slot</b>','CellGuide'),P('<b>Sheet W x D x T (mm)</b>','CellGuide')]]
            for sheet in sheets:
                rows.append([P(str(r['unit_to_slot'][sheet['lower_unit_id']]),'CellGuide'),
                             P(str(r['unit_to_slot'][sheet['upper_unit_id']]),'CellGuide'),P(dims(sheet['dimensions_mm']),'CellGuide')])
            flow.append(table(rows,[85,85,width-170]))
        used=sorted({template_for_unit[uid] for s in r['slots'] for uid in s['members'] if uid in template_for_unit})
        if used:flow.append(P('Preassemble nested groups using the group cards at the end, then orient each group as shown here.','SmallGuide'))
        two_columns=len(r['counts'])>12
        if two_columns:flow.append(PageBreak())
        flow.extend([Spacer(1,8),P(f'Box {n}: count before closing','TitleGuide' if two_columns else 'SubGuide')])
        note=P('Qty counts packing units; packet contents are stated separately. Purchased shapes are declared envelopes where detailed CAD is unavailable.','SmallGuide')
        note.keepWithNext=True
        flow.extend([note,Spacer(1,4)])
        rows=[[P('<b>Part</b>','CellGuide'),P(f'<b>BOX {n} - source / packing state</b>','CellGuide'),P('<b>Qty</b>','CellGuide'),P('<b>Slots</b>','CellGuide')]]
        part_cards=[]
        entries=sorted(r['counts'].items(),key=lambda entry:(property_cards.get(entry[0],{}).get('part_type',{}).get('value',''),entry[0])) if property_cards else r['counts'].items()
        for iid,count in entries:
            item=items[iid];display_name=name(item)
            category=property_cards.get(iid,{}).get('part_type',{}).get('value')
            if category and category!='unclassified' and any(s in display_name.lower() for s in ('.stl','.3mf','.step')):
                display_name=str(category).replace('_',' ').capitalize()
            description=f'<b>{escape(display_name)}</b><br/>{escape(iid)}'
            if category and category!='unclassified' and display_name.lower()!=str(category).replace('_',' ').lower():
                description+='<br/>Group: '+escape(str(category).replace('_',' '))
            state=declared_state(item)
            state_label={'source_part':'Original CAD part','factory_carton':'Factory carton',
                         'protective_packet':'Protective packet',
                         'declared_envelope':'Declared envelope'}[state['kind']]
            if state['kind']!='source_part':
                evidence={'measured':'measured dimensions','supplier_verified':'supplier dimensions',
                          'declared_estimate':'estimated dimensions'}.get(state.get('measurement_status'),'dimension evidence requires review')
                state_label+=' - '+evidence
            if state['kind']!='source_part':description+='<br/>'+state_label
            confirmed_frame=item.get('source_geometry_definition',{}).get('confirmed_frame_length_mm')
            if confirmed_frame is not None:
                description+=f'<br/>Confirmed frame: {float(confirmed_frame):g} mm'
            elif str(item.get('dimension_basis','')).startswith('User-confirmed'):
                description+='<br/>'+escape(item['dimension_basis'].split('. ')[0])
            contents=item.get('contents',{})
            if state['kind']=='protective_packet' or (contents and contents!={iid:1}):
                description+='<br/>Contents per unit: '+escape('; '.join(f'{q} x {key}' for key,q in contents.items()))
            rows.append([pic(thumbnails[iid],48,30 if state['kind']=='source_part' else 32),P(description,'CellGuide'),P(str(count),'CellGuide'),P(', '.join(map(str,r['item_slots'][iid])),'CellGuide')])
            if two_columns:
                text=description+f'<br/><b>Qty: {count} | Slots:</b> '+', '.join(map(str,r['item_slots'][iid]))
                card=Table([[pic(thumbnails[iid],34,32),P(text,'CellGuide')]],colWidths=[42,width/2-54])
                card.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),2),
                    ('RIGHTPADDING',(0,0),(-1,-1),2),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
                part_cards.append(card)
        if two_columns:
            headings=[P(f'<b>BOX {n} - part / quantity / slots</b>','CellGuide') for _ in range(2)]
            grid=Table([headings,*[[part_cards[i],part_cards[i+1] if i+1<len(part_cards) else ''] for i in range(0,len(part_cards),2)]],colWidths=[width/2]*2,repeatRows=1)
            grid.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
                ('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0),
                ('ROWBACKGROUNDS',(0,0),(-1,-1),[colors.HexColor('#f5f7f9'),colors.white]),
                ('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#d7dfe6'))]))
            flow.append(grid)
        else:flow.append(table(rows,[62,width-62-36-90,36,90],compact=True))
    if plan['templates']:
        flow.extend([PageBreak(),P('Nested groups: workbench assembly','TitleGuide'),P('Build each group in numbered order, then rotate the completed group into its box slot. These are certified workbench frames, not extra packing boxes.','SmallGuide')])
        cards=[]
        for template in plan['templates']:
            refs=[]
            members={uid for copy in template['copies'] for uid in copy['unit_mapping'].values()}
            for r in records:
                for slot in r['slots']:
                    if members.intersection(slot['members']):refs.append(f'Box {r["number"]} / slot {slot["number"]}')
            lookup={p['unit_id']:p['item_id'] for p in template['workbench_layout']['placements']}
            sequence=[uid for step in template['packing_sequence'] for uid in step['unit_ids']]
            caption='<br/>'.join(f'{i}. {escape(lookup[uid])}' for i,uid in enumerate(sequence,1))
            card=[P(escape('; '.join(refs)),'SubGuide'),pic(template_images[template['id']],width/2-18,140),P(caption,'CellGuide')]
            cards.append(card)
        for i in range(0,len(cards),2):
            row=Table([[cards[i],cards[i+1] if i+1<len(cards) else '']],colWidths=[width/2]*2)
            row.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BOX',(0,0),(-1,-1),.3,colors.HexColor('#d7dfe6')),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
            flow.append(KeepTogether([row,Spacer(1,8)]))
    flow.extend([PageBreak(),P('Checklist before taping','TitleGuide')])
    checks_text=['Count every source SKU and packet against its box sheet.',f'Close all {len(records)} inner boxes and keep their numbers identifiable.',
                 'Preserve the declared protective packing of servos and electronics.','Fit all six foam panels, including the lid.',
                 'Confirm actual restraint and closure on a physical prototype before release.','Apply the approved kit identification label.']
    rows=[[P('<b>Check</b>','CellGuide'),P('<b>Done</b>','CellGuide')]]
    for text in checks_text:rows.append([P(text),P('[   ]')])
    flow.extend([table(rows,[width-50,50]),Spacer(1,15),pic(assets/'closed-carton.png',width,300),
                 P('Outer carton illustration; no production label or carton dieline is implied.','SmallGuide'),Spacer(1,10),
                 P('Evidence','SubGuide'),P(f'Result SHA256: {sha256(raw).hexdigest()}','SmallGuide'),
                 P(f'BOM SHA256: {sha256(bom_raw).hexdigest()}','SmallGuide'),
                 P('Full geometric assembly steps and display offsets are included in the companion JSON files. Foam grade, material strength, manufacturing tolerances and shipping performance are not certified by these drawings.','SmallGuide')])
    class NumberedCanvas(canvas.Canvas):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);self.states=[];self.setTitle(f'{kit} - Visual packing guide');self.setAuthor('BOM to Kit')
        def showPage(self):self.states.append(dict(self.__dict__));self._startPage()
        def save(self):
            total=len(self.states)
            for state in self.states:
                self.__dict__.update(state);self.setStrokeColor(colors.HexColor('#d7dfe6'));self.line(margin,32,W-margin,32)
                self.setFont('Guide',7);self.setFillColor(colors.HexColor('#65717d'))
                self.drawString(margin,20,f'{kit} | {revision} | Geometric packing guide')
                self.drawRightString(W-margin,20,f'{self._pageNumber} / {total}');super().showPage()
            super().save()
    pdf=output/'packing-guide.pdf'
    SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=margin,rightMargin=margin,topMargin=30,bottomMargin=44).build(flow,canvasmaker=NumberedCanvas)
    (output/'assembly-plan.json').write_text(json.dumps(plan,indent=2),encoding='utf8')
    manifest={'result_sha256':sha256(raw).hexdigest(),'bom_sha256':sha256(bom_raw).hexdigest(),'pdf_sha256':sha256(pdf.read_bytes()).hexdigest(),
              'kit':kit,'revision':revision,'source_units':len(meshes),'carton_numbering':[{ 'number':r['number'],'id':r['module']['id'],'unit_ids':r['module']['unit_ids']} for r in records],
              'display_offsets':offsets,'source_geometry_modified':False,'explosion_is_display_only':True,
              'physical_qualification':False,'transport_checks':checks,
              'manual_material_screen':material_screen,'accessory_set_cohesion':cohesion_screen,
              'properties_sha256':sha256(Path(properties_path).read_bytes()).hexdigest() if properties_path else None,
              'display_property_cards_fingerprint':fingerprint(property_cards),
              'illustrations_sha256':{p.name:sha256(p.read_bytes()).hexdigest() for p in assets.glob('*.png')}}
    (output/'guide-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    return {'pdf':str(pdf),'cartons':len(records),'source_units':len(meshes)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result',type=Path);parser.add_argument('bom',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--kit',default='Kit');parser.add_argument('--revision',default='Draft 1')
    parser.add_argument('--properties',type=Path,help='Property cards bound to the selected concept; groups the contents index')
    args=parser.parse_args();print(json.dumps(build(args.result,args.bom,args.output,kit=args.kit,revision=args.revision,properties_path=args.properties)))
