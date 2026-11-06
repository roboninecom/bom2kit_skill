"""Read-only 3MF inventory; printer coordinates are never packing coordinates.

Core transforms follow https://github.com/3MFConsortium/spec_core .
Production external components and Bambu part metadata are supported. This is
geometry inspection, not a complete 3MF manufacturing/conformance interpreter.
"""

from hashlib import sha256
import math
from pathlib import Path
import posixpath
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from zipfile import ZipFile

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
PRODUCTION = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"
UNITS = {"micron": .001, "millimeter": 1, "centimeter": 10, "inch": 25.4, "foot": 304.8, "meter": 1000}
IDENTITY = [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]


def _matrix(text):
    if text is None:
        return [row[:] for row in IDENTITY]
    values = [float(v) for v in text.split()]
    if len(values) != 12 or not all(math.isfinite(v) for v in values):
        raise ValueError("Invalid 3MF transform")
    return [values[i * 3:i * 3 + 3] + [float(i == 3)] for i in range(4)]


def _multiply(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _transform(vertices, matrix, scale):
    return [[scale * (sum(v[k] * matrix[k][j] for k in range(3)) + matrix[3][j])
             for j in range(3)] for v in vertices]


def _bounds(vertices):
    low = [min(v[k] for v in vertices) for k in range(3)]
    high = [max(v[k] for v in vertices) for k in range(3)]
    return {"bounds_mm": [low, high], "dimensions_mm": [b - a for a, b in zip(low, high)]}


def _member(target, parent=""):
    target = unquote(target).replace("\\", "/")
    name = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join(posixpath.dirname(parent), target))
    if name.startswith("../") or ":" in name or name == "..":
        raise ValueError("Invalid 3MF archive reference")
    return name


def _metadata(element):
    return {entry.get("key"): entry.get("value", "") for entry in element.findall("metadata") if entry.get("key")}


def _read(path):
    path = Path(path)
    meshes, instances, models = {}, [], {}
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        root_member = "3D/3dmodel.model"
        if "_rels/.rels" in names:
            relationships = ET.fromstring(archive.read("_rels/.rels"))
            targets = [r for r in relationships if r.get("Type", "").endswith("/3dmodel")]
            if targets:
                if len(targets) != 1 or targets[0].get("TargetMode") == "External":
                    raise ValueError("Unsupported external or ambiguous 3MF root")
                root_member = _member(targets[0].attrib["Target"])
        settings = {}
        if "Metadata/model_settings.config" in names:
            config = ET.fromstring(archive.read("Metadata/model_settings.config"))
            for obj in config.findall("object"):
                settings[obj.attrib["id"]] = {
                    "metadata": _metadata(obj),
                    "parts": {p.attrib["id"]: {**_metadata(p), "subtype": p.get("subtype", "unknown")}
                              for p in obj.findall("part")},
                }

        def model(member):
            if member not in models:
                element = ET.fromstring(archive.read(member))
                unit = element.get("unit", "millimeter")
                if unit not in UNITS:
                    raise ValueError(f"Unsupported 3MF unit: {unit}")
                objects = {}
                for obj in element.findall(f"{CORE}resources/{CORE}object"):
                    oid = obj.attrib["id"]
                    if oid in objects:
                        raise ValueError(f"Duplicate 3MF object: {member}#{oid}")
                    objects[oid] = obj
                models[member] = (element, unit, objects)
            return models[member]

        root, unit, _ = model(root_member)
        scale = UNITS[unit]

        def visit(member, oid, local, build, root_id, build_index, trail, printable):
            key = (member, oid)
            if key in trail or len(trail) > 100:
                raise ValueError("Cyclic or excessively deep 3MF components")
            _, child_unit, objects = model(member)
            if child_unit != unit:
                raise ValueError("Mixed-unit external 3MF components require explicit normalization")
            obj = objects[oid]
            mesh = obj.find(f"{CORE}mesh")
            if mesh is not None:
                mesh_id = f"{member}#{oid}"
                if mesh_id not in meshes:
                    vertices = [[float(v.attrib[k]) for k in ("x", "y", "z")]
                                for v in mesh.findall(f"{CORE}vertices/{CORE}vertex")]
                    triangles = [[int(t.attrib[k]) for k in ("v1", "v2", "v3")]
                                 for t in mesh.findall(f"{CORE}triangles/{CORE}triangle")]
                    if not vertices or not triangles or not all(math.isfinite(c) for v in vertices for c in v):
                        raise ValueError(f"Empty or nonfinite 3MF mesh: {mesh_id}")
                    if any(i < 0 or i >= len(vertices) for t in triangles for i in t):
                        raise ValueError(f"Out-of-range triangle index: {mesh_id}")
                    meshes[mesh_id] = {"vertices": vertices, "triangles": triangles}
                data = meshes[mesh_id]
                parent_info = settings.get(root_id, {})
                info = parent_info.get("parts", {}).get(oid, {})
                name = info.get("name") or obj.get("name") or parent_info.get("metadata", {}).get("name") or mesh_id
                subtype = info.get("subtype", "unknown")
                object_type = obj.get("type", "model")
                excluded = subtype not in ("normal_part", "unknown") or object_type != "model" or not printable
                suspicious_name = any(word in name.lower() for word in ("prime tower", "wipe tower", "support", "modifier", "purge tower"))
                classification = "excluded_nonpart" if excluded else ("requires_review" if suspicious_name or subtype == "unknown" else "part_candidate")
                world = _multiply(local, build)
                instances.append({
                    "instance_id": f"build-{build_index}/leaf-{len(instances) + 1}",
                    "build_index": build_index, "build_object_id": root_id,
                    "mesh_reference": {"member": member, "object_id": oid, "mesh_id": mesh_id},
                    "name": name, "source_file": info.get("source_file"),
                    "subtype": subtype, "object_type": object_type, "printable": printable,
                    "classification": classification, "bom_identity_verified": False,
                    "vertex_count": len(data["vertices"]), "triangle_count": len(data["triangles"]),
                    "local_mesh": _bounds(_transform(data["vertices"], IDENTITY, scale)),
                    "object_frame": _bounds(_transform(data["vertices"], local, scale)),
                    "printer_frame": _bounds(_transform(data["vertices"], world, scale)),
                    "component_transform_row_major": local,
                    "printer_transform_row_major": world,
                })
            components = obj.findall(f"{CORE}components/{CORE}component")
            if mesh is None and not components:
                raise ValueError(f"Object has no supported mesh/components: {key}")
            for component in components:
                child_member = _member(component.attrib[PRODUCTION + "path"], member) if PRODUCTION + "path" in component.attrib else member
                visit(child_member, component.attrib["objectid"], _multiply(_matrix(component.get("transform")), local),
                      build, root_id, build_index, trail + [key], printable)

        builds = root.findall(f"{CORE}build/{CORE}item")
        for index, item in enumerate(builds, 1):
            if PRODUCTION + "path" in item.attrib:
                member = _member(item.attrib[PRODUCTION + "path"], root_member)
            else:
                member = root_member
            visit(member, item.attrib["objectid"], IDENTITY, _matrix(item.get("transform")),
                  item.attrib["objectid"], index, [], item.get("printable", "1") not in ("0", "false"))
    inventory = {"source": str(path.resolve()), "source_sha256": sha256(path.read_bytes()).hexdigest(),
                 "format": "3mf", "source_unit": unit, "units": "mm", "root_member": root_member,
                 "build_item_count": len(builds), "mesh_count": len(meshes), "leaf_instance_count": len(instances),
                 "candidate_instance_count": sum(i["classification"] == "part_candidate" for i in instances),
                 "instances": instances, "packing_validated": False,
                 "limitations": ["Printer transforms are manufacturing poses, not packing poses.",
                                 "Build quantities and part names are not an approved BOM mapping.",
                                 "Bounds are mesh envelopes; no watertightness or transport validation is performed.",
                                 "Unknown part roles require review; explicit Bambu modifiers/support are excluded.",
                                 "Materials and manufacturing extensions are not interpreted."]}
    return inventory, meshes, scale


def inspect_3mf(path):
    """Return JSON-serializable inventory, preserving every build leaf and role."""
    return _read(path)[0]


def load_instance_mesh(path, instance_id, frame="object"):
    """Return vertices in mm and faces for one inventory instance, without files.

    frame='local' is raw mesh coordinates, 'object' includes component transforms,
    and 'printer' additionally includes the manufacturing build transform.
    """
    if frame not in ("local", "object", "printer"):
        raise ValueError("frame must be local, object, or printer")
    inventory, meshes, scale = _read(path)
    instance = next((i for i in inventory["instances"] if i["instance_id"] == instance_id), None)
    if instance is None:
        raise ValueError(f"Unknown instance: {instance_id}")
    mesh = meshes[instance["mesh_reference"]["mesh_id"]]
    matrix = IDENTITY if frame == "local" else instance["component_transform_row_major" if frame == "object" else "printer_transform_row_major"]
    return {"vertices_mm": _transform(mesh["vertices"], matrix, scale), "triangles": mesh["triangles"],
            "frame": frame, "instance": instance, "source_sha256": inventory["source_sha256"]}
