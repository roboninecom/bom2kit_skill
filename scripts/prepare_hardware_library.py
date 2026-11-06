"""Create neutral purchased-part envelopes from source BOM rows and explicit assumptions."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bom2kit.models import vector, number
from bom2kit.bom import reconcile_bom


def packet_dimensions(cell, count, gap=.5, film=.2, seal=5):
    """A count-preserving regular grid, selected by surface area then volume."""
    cell = vector(cell, "cell_mm", True)
    if type(count) is not int or count < 1:
        raise ValueError("Positive integer packet count required")
    candidates = []
    for nx in range(1, count + 1):
        for ny in range(1, math.ceil(count / nx) + 1):
            nz = math.ceil(count / (nx * ny))
            dims = [(s + gap) * n - gap + 2*film for s,n in zip(cell,(nx,ny,nz))]
            dims[2] += seal
            surface = sum(dims[i]*dims[j] for i,j in ((0,1),(0,2),(1,2)))
            candidates.append(((surface, math.prod(dims), max(dims)), dims, [nx,ny,nz]))
    _, dimensions, grid = min(candidates)
    return dimensions, {"cell_mm": list(cell), "grid": grid, "occupied_cells": count,
                        "spacing_mm": gap, "film_per_face_mm": film, "seal_allowance_mm": seal}


def shape_mesh(spec):
    import trimesh

    kind = spec["kind"]
    if kind == "box":
        return trimesh.creation.box(vector(spec["dimensions_mm"], "dimensions_mm", True))
    if kind == "annulus":
        return trimesh.creation.annulus(r_min=number(spec["inner_radius_mm"], "inner_radius", True),
                                       r_max=number(spec["outer_radius_mm"], "outer_radius", True),
                                       height=number(spec["height_mm"], "height", True), sections=64)
    if kind == "cylinder":
        return trimesh.creation.cylinder(radius=number(spec["radius_mm"], "radius", True),
                                        height=number(spec["height_mm"], "height", True), sections=32)
    if kind == "solid_union":
        import cadquery as cq
        solids = []
        for primitive in spec["primitives"]:
            origin = cq.Vector(*primitive["origin_mm"])
            if primitive["kind"] == "box":
                solids.append(cq.Solid.makeBox(*vector(primitive["dimensions_mm"], "dimensions", True), origin))
            elif primitive["kind"] == "cylinder":
                solids.append(cq.Solid.makeCylinder(primitive["radius_mm"], primitive["height_mm"], origin, cq.Vector(*primitive["axis"])))
            else:
                raise ValueError("Unknown union primitive")
        shape = solids[0]
        for solid in solids[1:]:
            shape = shape.fuse(solid)
        shape = shape.clean()
        if not shape.isValid():
            raise ValueError("Invalid primitive union")
        vertices, faces = shape.tessellate(.05,.1)
        mesh = trimesh.Trimesh([v.toTuple() for v in vertices], faces, process=True)
        mesh.update_faces(mesh.area_faces > 0)
        return mesh
    raise ValueError(f"Unknown shape kind: {kind}")


def prepare(rows_path, spec_path, output):
    rows_path, spec_path, output = Path(rows_path), Path(spec_path), Path(output).resolve()
    raw = rows_path.read_bytes()
    rows_doc = json.loads(raw)
    spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    if spec["source_rows_sha256"] != sha256(raw).hexdigest():
        raise ValueError("Hardware specification belongs to different source rows")
    source = Path(rows_doc["source"])
    if sha256(source.read_bytes()).hexdigest() != rows_doc["source_sha256"]:
        raise ValueError("Source BOM changed after row extraction")
    rows = [r for r in rows_doc["rows"] if not r["optional_alternative"]]
    if set(spec["row_geometry"]) != {str(r["source_line"]) for r in rows}:
        raise ValueError("Every selected BOM row must have exactly one geometry specification")
    output.mkdir(parents=True, exist_ok=True)
    work = [("hardware-line-" + str(r["source_line"]), r["quantity"], spec["row_geometry"][str(r["source_line"])],
             {"source_line": r["source_line"], "source_item": r["item"]}) for r in rows]
    for extra in spec.get("additions", []):
        work.append((extra["id"], extra["quantity"], extra, {"addition_basis": extra["evidence"]}))
    if len({w[0] for w in work}) != len(work):
        raise ValueError("Duplicate hardware identity")
    items, expected = [], []
    for iid, quantity, definition, evidence in work:
        if type(quantity) is not int or quantity < 1 or not definition.get("evidence"):
            raise ValueError("Positive counts and dimension evidence required")
        expected.append({"id": iid, "quantity": quantity})
        grid = None
        if definition.get("batch_in_packet"):
            dimensions, grid = packet_dimensions(definition["shape"]["dimensions_mm"], quantity)
            mesh = shape_mesh({"kind": "box", "dimensions_mm": dimensions})
            packed_quantity, contents = 1, {iid: quantity}
        else:
            mesh = shape_mesh(definition["shape"])
            packed_quantity, contents = quantity, {iid: 1}
        if not mesh.is_volume or min(mesh.area_faces) <= 0:
            raise ValueError(f"Invalid purchased-item mesh: {iid}")
        mesh.apply_translation(-mesh.bounds[0])
        path = output / (sha256(iid.encode()).hexdigest() + ".json")
        path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist()}, allow_nan=False))
        items.append({"id": iid, "quantity": packed_quantity, "contents": contents,
                      "mesh": {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()},
                      "dimension_basis": definition["evidence"], "source_evidence": evidence,
                      "source_geometry_definition": definition,
                      "packing_state": definition.get("packing_state", "Declared purchased-item envelope"),
                      "packet_grid": grid, "dimensions_mm": mesh.extents.tolist(),
                      "watertight_positive_volume": True})
    library = {"units": "mm", "items": items, "all_meshes_valid_volumes": True,
               "scope": "Declared purchased hardware under explicit measured/estimated envelopes",
               "specification_sha256": sha256(spec_path.read_bytes()).hexdigest(),
               "specification_path": str(spec_path.resolve()),
               "source_rows_sha256": spec["source_rows_sha256"],
               "part_count": sum(i["quantity"] for i in items)}
    bom = {"components": expected}
    coverage = reconcile_bom(bom, library)
    if not coverage["complete"]:
        raise ValueError("Hardware packet counts do not match source BOM")
    for name, value in (("library",library),("bom",bom),("coverage",coverage)):
        (output / (name + ".json")).write_text(json.dumps(value, indent=2), encoding="utf8")
    return library


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rows", type=Path)
    parser.add_argument("specification", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.rows, args.specification, args.output)
    print(json.dumps({"packing_units": result["part_count"], "types": len(result["items"])}))
