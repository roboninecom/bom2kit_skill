"""Publication views of source CAD; explosion offsets never alter packing data."""
from pathlib import Path

CARTON=(.70,.49,.29)
FOAM=(.79,.81,.81)
PART=(.76,.78,.80)
STATE_COLORS={'source_part':PART,'factory_carton':(.84,.68,.44),
              'protective_packet':(.53,.72,.81),'declared_envelope':(.73,.66,.81)}


def state_color(item):
    from .packing_states import declared_state
    return STATE_COLORS[declared_state(item)['kind']]


def cuboid(origin,size):
    import numpy as np
    import trimesh
    mesh=trimesh.creation.box(size)
    mesh.apply_translation(np.asarray(origin)+np.asarray(size)/2)
    return mesh


def carton_shell(origin,size,wall,*,cutaway=False):
    """Keep the rear walls full height; cut only the camera-facing display walls."""
    x,y,z=origin;w,d,h=size
    sides=max(wall+.01,min(18,h*.18)) if cutaway else h
    return [(cuboid([x,y,z],[w,d,wall]),CARTON),
            (cuboid([x,y,z+wall],[wall,d,h-wall]),CARTON),
            (cuboid([x+w-wall,y,z+wall],[wall,d,sides-wall]),CARTON),
            (cuboid([x+wall,y,z+wall],[w-2*wall,wall,sides-wall]),CARTON),
            (cuboid([x+wall,y+d-wall,z+wall],[w-2*wall,wall,h-wall]),CARTON)]


def exploded_scene(result,ordered_modules,meshes):
    """One rigid display translation per carton, with the actual CAD inside."""
    import numpy as np
    info=result['logistics'];policy=info['policy'];inner=result['input']['container']['inner_mm']
    wall=policy['carton']['wall_mm'];t=policy['carton']['inner_wall_mm']
    outer=[v+2*wall for v in inner]
    objects=carton_shell([-wall]*3,outer,wall,cutaway=True)
    for panel in info['foam_panels']:
        if panel['id']=='foam-top':continue
        # Near panels are shortened only in this display to reveal the cavity.
        size=list(panel['dimensions_mm'])
        if panel['id'] in ('foam-front','foam-right'):size[2]=min(size[2],inner[2]*.18)
        objects.append((cuboid(panel['origin_mm'],size),FOAM))
    levels=sorted({m['position_mm'][2] for m in ordered_modules})
    gap=max(info['block_mm'][:2])*.25
    offsets={z:inner[2]+gap+index*gap for index,z in enumerate(levels)}
    labels=[];display=[]
    items={i['id']:i for i in result['input'].get('items',[])}
    uid_items={p['unit_id']:items[p['item_id']] for p in result.get('layout',{}).get('placements',[]) if p['item_id'] in items}
    for number,module in enumerate(ordered_modules,1):
        offset=np.array([0.,0.,offsets[module['position_mm'][2]]])
        origin=np.asarray(module['position_mm'])+offset
        objects.extend(carton_shell(origin,module['external_mm'],t,cutaway=True))
        for uid in module['unit_ids']:
            mesh=meshes[uid].copy();mesh.apply_translation(offset)
            objects.append((mesh,state_color(uid_items[uid]) if uid in uid_items else PART))
        for panel in [*result.get('practical',{}).get('floor_liners',[]),*result.get('practical',{}).get('protective_separators',[])]:
            if panel['carton_id']==module['id']:
                objects.append((cuboid(np.asarray(panel['origin_mm'])+offset,panel['dimensions_mm']),FOAM))
        labels.append((str(number),origin+np.array([module['external_mm'][0]/2,-1,8])))
        display.append({'carton_id':module['id'],'label':number,'translation_mm':offset.tolist(),
                        'unit_ids':module['unit_ids']})
    top=next(p for p in info['foam_panels'] if p['id']=='foam-top')
    origin=list(top['origin_mm']);origin[2]=max(m['position_mm'][2]+m['external_mm'][2]+offsets[m['position_mm'][2]] for m in ordered_modules)+gap
    objects.append((cuboid(origin,top['dimensions_mm']),FOAM))
    labels.append(('Foam lid',np.asarray(origin)+np.array([top['dimensions_mm'][0]/2,0,top['dimensions_mm'][2]/2])))
    return objects,labels,display


def render_scene(objects,output,*,view='iso',labels=(),size=(1200,900),trim=False):
    """Depth-buffered neutral CAD illustration, with no baked-in page typography."""
    import numpy as np
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray,vtk_to_numpy
    from PIL import Image,ImageDraw,ImageFont
    from matplotlib import font_manager
    objects=list(objects)
    if not objects:raise ValueError('An illustration needs source geometry')
    points=np.concatenate([m.vertices for m,_ in objects]);low=points.min(0);high=points.max(0)
    center=(low+high)/2;span=max(high-low)
    window=vtk.vtkRenderWindow();window.SetOffScreenRendering(1);window.SetSize(*size);window.SetMultiSamples(4)
    renderer=vtk.vtkRenderer();renderer.SetBackground(1,1,1);window.AddRenderer(renderer)
    def actor(poly,color):
        mapper=vtk.vtkPolyDataMapper();mapper.SetInputData(poly);mapper.ScalarVisibilityOff()
        obj=vtk.vtkActor();obj.SetMapper(mapper)
        prop=obj.GetProperty();prop.SetColor(*color);prop.SetAmbient(.28);prop.SetDiffuse(.72);prop.SetSpecular(.12);prop.SetSpecularPower(25)
        return obj
    try:
        basic=vtk.vtkRenderStepsPass();ao=vtk.vtkSSAOPass();ao.SetDelegatePass(basic)
        ao.SetRadius(span*.035);ao.SetBias(span*.0004);ao.SetKernelSize(32);ao.BlurOn();renderer.SetPass(ao)
        for mesh,color in objects:
            vertices=vtk.vtkPoints();vertices.SetData(numpy_to_vtk(np.asarray(mesh.vertices),deep=True))
            cells=vtk.vtkCellArray();packed=np.column_stack((np.full(len(mesh.faces),3),mesh.faces)).astype(np.int64)
            cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(packed.ravel(),deep=True))
            poly=vtk.vtkPolyData();poly.SetPoints(vertices);poly.SetPolys(cells)
            normals=vtk.vtkPolyDataNormals();normals.SetInputData(poly);normals.SetFeatureAngle(45);normals.SplittingOn();normals.Update()
            renderer.AddActor(actor(normals.GetOutput(),color))
            edges=vtk.vtkFeatureEdges();edges.SetInputData(poly);edges.SetFeatureAngle(40);edges.ManifoldEdgesOff();edges.NonManifoldEdgesOff();edges.Update()
            outline=actor(edges.GetOutput(),(.27,.28,.29));outline.GetProperty().LightingOff();renderer.AddActor(outline)
        camera=renderer.GetActiveCamera();camera.SetFocalPoint(*center)
        directions={'iso':(1,-1.5,1.15),'top':(0,0,3),'side':(0,-3,0)}
        camera.SetPosition(*(center+np.asarray(directions[view])*span*3));camera.SetViewUp(*( (0,1,0) if view=='top' else (0,0,1)))
        camera.ParallelProjectionOn();renderer.ResetCamera();camera.SetParallelScale(camera.GetParallelScale()*1.08);renderer.ResetCameraClippingRange()
        window.Render();anchors=[]
        for label,point in labels:
            renderer.SetWorldPoint(*point,1);renderer.WorldToDisplay();x,y,_=renderer.GetDisplayPoint()
            anchors.append((str(label),x,size[1]-y))
        capture=vtk.vtkWindowToImageFilter();capture.SetInput(window);capture.ReadFrontBufferOff();capture.Update()
        pixels=vtk_to_numpy(capture.GetOutput().GetPointData().GetScalars()).reshape(size[1],size[0],-1)[::-1].copy()
        picture=Image.fromarray(pixels);draw=ImageDraw.Draw(picture)
        font=ImageFont.truetype(font_manager.findfont('DejaVu Sans'),max(20,int(size[0]/30)))
        occupied=[]
        for label,x,y in sorted(anchors,key=lambda p:p[2]):
            bounds=draw.textbbox((0,0),label,font=font);w=bounds[2]-bounds[0]+14;h=bounds[3]-bounds[1]+12
            cx=max(w/2+4,min(size[0]-w/2-4,x));cy=max(h/2+4,min(size[1]-h/2-4,y))
            for attempt in range(80):
                box=(cx-w/2,cy-h/2,cx+w/2,cy+h/2)
                if all(box[2]+3<b[0] or box[0]-3>b[2] or box[3]+3<b[1] or box[1]-3>b[3] for b in occupied):break
                cy=min(size[1]-h/2-4,y+(attempt+1)*(h+3))
                if cy>=size[1]-h/2-4:cx=max(w/2+4,cx-w-5);cy=max(h/2+4,y)
            occupied.append(box)
            if abs(cx-x)+abs(cy-y)>5:draw.line((x,y,cx,cy),fill='#555555',width=2)
            draw.rounded_rectangle(box,radius=3,fill='white',outline='#9ca3aa');draw.text((cx,cy),label,font=font,anchor='mm',fill='#202832')
        if trim:
            visible=np.any(np.asarray(picture)[:,:,:3]<245,axis=2)
            yy,xx=np.where(visible);pad=max(8,int(max(size)*.015))
            picture=picture.crop((max(0,int(xx.min())-pad),max(0,int(yy.min())-pad),
                                  min(size[0],int(xx.max())+pad+1),min(size[1],int(yy.max())+pad+1)))
        Path(output).parent.mkdir(parents=True,exist_ok=True);picture.save(output)
    finally:window.Finalize()
