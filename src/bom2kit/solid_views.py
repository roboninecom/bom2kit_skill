"""Offline CAD illustrations of unchanged meshes, using a depth-buffered renderer."""
from pathlib import Path


PALETTE = ((.78, .82, .86), (.45, .57, .66), (.85, .80, .68),
           (.61, .70, .68), (.70, .67, .76), (.80, .69, .59))


def render_solid_views(parts, output, *, title, cavity=None, wall=1.5,
                       caption="Original CAD triangles / simplified supplied envelopes", label_slots=True):
    """Render (mesh, slot number) pairs in their existing local coordinates.

    Left: open carton cutaway (two camera-facing walls omitted for visibility).
    Right: true top view with slot labels. No source geometry is simplified.
    """
    import numpy as np
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray

    parts = list(parts)
    if not parts:
        raise ValueError("At least one original mesh is required")
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(900, 1000)
    images = []
    window.SetMultiSamples(4)
    points = np.concatenate([mesh.vertices for mesh, _ in parts])
    low, high = points.min(axis=0), points.max(axis=0)
    if cavity is not None:
        low = np.minimum(low, [-wall, -wall, -wall])
        high = np.maximum(high, np.asarray(cavity)+wall)
    centre = (low+high)/2
    span = max(high-low)

    def actor(poly, color, edges=False):
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(poly)
        mapper.ScalarVisibilityOff()
        obj = vtk.vtkActor()
        obj.SetMapper(mapper)
        prop = obj.GetProperty()
        prop.SetColor(*color)
        prop.SetAmbient(.24)
        prop.SetDiffuse(.76)
        prop.SetSpecular(.18)
        prop.SetSpecularPower(30)
        prop.SetInterpolationToPhong()
        if edges:
            prop.EdgeVisibilityOn()
            prop.SetEdgeColor(.30, .25, .19)
        return obj

    def text(renderer, value, x, y, size=23):
        obj = vtk.vtkTextActor()
        obj.SetInput(value)
        obj.SetPosition(x, y)
        prop = obj.GetTextProperty()
        prop.SetFontSize(size)
        prop.SetColor(.12, .16, .20)
        renderer.AddViewProp(obj)

    try:
        for view in range(2):
            renderer = vtk.vtkRenderer()
            renderer.SetViewport(0, 0, 1, 1)
            renderer.SetBackground(1, 1, 1)
            window.AddRenderer(renderer)
            # Ambient occlusion emphasizes holes, recesses and close surfaces.
            basic = vtk.vtkRenderStepsPass()
            ao = vtk.vtkSSAOPass()
            ao.SetDelegatePass(basic)
            ao.SetRadius(span*.07)
            ao.SetBias(span*.0005)
            ao.SetKernelSize(64)
            ao.BlurOn()
            renderer.SetPass(ao)
            for mesh, number in parts:
                vertices = vtk.vtkPoints()
                vertices.SetData(numpy_to_vtk(np.asarray(mesh.vertices), deep=True))
                cells = vtk.vtkCellArray()
                packed = np.column_stack((np.full(len(mesh.faces), 3), mesh.faces)).astype(np.int64)
                cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(packed.ravel(), deep=True))
                poly = vtk.vtkPolyData()
                poly.SetPoints(vertices)
                poly.SetPolys(cells)
                normals = vtk.vtkPolyDataNormals()
                normals.SetInputData(poly)
                normals.SetFeatureAngle(45)
                normals.SplittingOn()
                normals.Update()
                renderer.AddActor(actor(normals.GetOutput(), PALETTE[(number-1)%len(PALETTE)]))
                features = vtk.vtkFeatureEdges()
                features.SetInputData(poly)
                features.SetFeatureAngle(40)
                features.ManifoldEdgesOff()
                features.NonManifoldEdgesOff()
                features.Update()
                outline = actor(features.GetOutput(), (.20, .24, .27))
                outline.GetProperty().LightingOff()
                outline.GetProperty().SetLineWidth(1)
                renderer.AddActor(outline)
            if cavity is not None:
                w, d, h = cavity
                # Far walls and floor only: no transparent solids or hidden parts moved.
                for bounds in ((-wall, w+wall, -wall, d+wall, -wall, 0),
                               (-wall, 0, -wall, d+wall, 0, h),
                               (-wall, w+wall, d, d+wall, 0, h)):
                    cube = vtk.vtkCubeSource()
                    cube.SetBounds(*bounds)
                    cube.Update()
                    renderer.AddActor(actor(cube.GetOutput(), (.74, .57, .37), edges=True))
            camera = renderer.GetActiveCamera()
            camera.SetFocalPoint(*centre)
            direction = np.asarray((1, -1.35, 1.35) if view == 0 else (0, 0, 3))
            camera.SetPosition(*(centre+direction*span*3))
            camera.SetViewUp(0, 0, 1) if view == 0 else camera.SetViewUp(0, 1, 0)
            camera.ParallelProjectionOn()
            renderer.ResetCamera()
            camera.SetParallelScale(camera.GetParallelScale()*1.14)
            renderer.ResetCameraClippingRange()
            text(renderer, title, 28, 948, 25)
            text(renderer, "3D cutaway - front/right walls hidden" if cavity is not None and view == 0
                 else "3D assembly" if view == 0 else "Top view - numbered slots" if label_slots else "Top view", 28, 910, 20)
            text(renderer, caption, 28, 28, 18)
            window.Render()
            labels = []
            if view == 1 and label_slots:
                for number in sorted({n for _, n in parts}):
                    bounds = np.asarray([m.bounds for m, n in parts if n == number])
                    p = (bounds[:, 0].min(axis=0)+bounds[:, 1].max(axis=0))/2
                    p[2] = high[2]+span*.01
                    renderer.SetWorldPoint(*p, 1)
                    renderer.WorldToDisplay()
                    x, y, _ = renderer.GetDisplayPoint()
                    labels.append((str(number), x, y))
            window.Render()
            capture = vtk.vtkWindowToImageFilter()
            capture.SetInput(window)
            capture.ReadFrontBufferOff()
            capture.Update()
            from vtk.util.numpy_support import vtk_to_numpy
            from PIL import Image
            pixels = vtk_to_numpy(capture.GetOutput().GetPointData().GetScalars())
            picture = Image.fromarray(pixels.reshape(1000, 900, -1)[::-1].copy())
            if labels:
                _draw_labels(picture, labels)
            images.append(picture)
            window.RemoveRenderer(renderer)
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        combined = Image.new("RGB", (1800, 1000), "white")
        for index, picture in enumerate(images):
            combined.paste(picture, (index*900, 0))
        combined.save(output)
    finally:
        window.Finalize()


def _draw_labels(picture, labels):
    """Separate nearby top-view labels; leader lines retain their true anchors."""
    from PIL import ImageDraw, ImageFont
    from matplotlib import font_manager
    font = ImageFont.truetype(font_manager.findfont("DejaVu Sans"), 22)
    draw = ImageDraw.Draw(picture)
    placed = []
    entries = []
    for text, x, vtk_y in sorted(labels, key=lambda row: (-row[2], row[1])):
        y = picture.height-vtk_y
        width = draw.textbbox((0, 0), text, font=font)[2]+10
        cx, cy = max(width/2+6, min(894-width/2, x)), y
        for attempt in range(100):
            bounds = (cx-width/2, cy-16, cx+width/2, cy+16)
            if all(bounds[2]+3 < b[0] or bounds[0]-3 > b[2] or
                   bounds[3]+3 < b[1] or bounds[1]-3 > b[3] for b in placed):
                break
            cy += 35
            if cy > 870:
                cy = max(140, y-35*(attempt+1))
        placed.append(bounds)
        entries.append((text, x, y, cx, cy, bounds))
    # Draw every leader before any text box. Later leaders must not cross
    # earlier numbers when vertically stacked slots share the same anchor.
    for text, x, y, cx, cy, bounds in entries:
        if abs(cx-x)+abs(cy-y) > 5:
            draw.line((x, y, cx, cy), fill=(45, 55, 65), width=2)
            draw.ellipse((x-3, y-3, x+3, y+3), fill=(45, 55, 65))
    for text, x, y, cx, cy, bounds in entries:
        draw.rounded_rectangle(bounds, radius=3, fill="white", outline=(155, 165, 175))
        draw.text((cx, cy), text, font=font, fill=(25, 35, 45), anchor="mm")
