"""Extract neutral physical-part candidates from source 3MF manufacturing files.

Optional contact joining represents touching material shells of one printed part.
It is an explicit source interpretation, not a packing/grouping optimization.
Build translations and printer-plate placements are never used as packing poses.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bom2kit.mesh_geometry import inspect_3mf, load_instance_mesh
from bom2kit.mesh_preparation import remove_empty_faces


def contact_groups(parts, tolerance=1e-6):
    import numpy as np
    import trimesh

    parents = list(range(len(parts)))
    def root(index):
        while parents[index] != index:
            index = parents[index]
        return index
    for i, a in enumerate(parts):
        manager = trimesh.collision.CollisionManager()
        manager.add_object("a", a)
        for j in range(i + 1, len(parts)):
            b = parts[j]
            if np.any(a.bounds[0] > b.bounds[1] + tolerance) or np.any(b.bounds[0] > a.bounds[1] + tolerance):
                continue
            if manager.min_distance_single(b) <= tolerance:
                parents[root(j)] = root(i)
    groups = {}
    for i in range(len(parts)):
        groups.setdefault(root(i), []).append(i)
    return list(groups.values())


def prepare(paths, output, join_contacting=False, id_prefix="printed-figure"):
    import trimesh

    if not re.fullmatch(r"[A-Za-z0-9_-]+", id_prefix):
        raise ValueError("Identity prefix must contain only letters, digits, underscore or dash")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for source in paths:
        source = Path(source).resolve()
        inventory = inspect_3mf(source)
        for instance in inventory["instances"]:
            # Explicit exclusions are checked before decomposing a print object.
            if instance["classification"] == "excluded_nonpart":
                continue
            if instance["classification"] != "part_candidate":
                raise ValueError(f"Unreviewed source instance role: {source}: {instance['instance_id']}")
            data = load_instance_mesh(source, instance["instance_id"], "object")
            mesh = trimesh.Trimesh(data["vertices_mm"], data["triangles"], process=True)
            mesh, removed = remove_empty_faces(mesh)
            parts = list(mesh.split(only_watertight=False))
            groups = contact_groups(parts) if join_contacting else [[i] for i in range(len(parts))]
            for indices in groups:
                part = trimesh.util.concatenate([parts[i] for i in indices])
                part.apply_translation(-part.bounds[0])
                identity = f"{id_prefix}-{len(records)+1:02d}"
                geometry = {"units": "mm", "vertices_mm": part.vertices.tolist(), "triangles": part.faces.tolist()}
                path = output / (identity + ".json")
                path.write_text(json.dumps(geometry, allow_nan=False), encoding="utf8")
                records.append({"id": identity, "quantity": 1,
                                "source": str(source), "source_sha256": inventory["source_sha256"],
                                "source_instance": instance["instance_id"], "source_name": instance.get("name"),
                                "source_components": indices, "source_frame": "object",
                                "source_zero_area_faces_removed": removed,
                                "contact_shell_joining": join_contacting,
                                "mesh": {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()},
                                "dimensions_mm": part.extents.tolist(),
                                "watertight_positive_volume": bool(part.is_volume)})
    if not records:
        raise ValueError("No physical-part candidates found")
    result = {"units": "mm", "items": records, "part_count": len(records),
              "scope": "Source printed figure candidates; review part identities against the BOM",
              "all_meshes_valid_volumes": all(r["watertight_positive_volume"] for r in records)}
    (output / "library.json").write_text(json.dumps(result, indent=2), encoding="utf8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--join-contacting-shells", action="store_true")
    parser.add_argument("--id-prefix", default="printed-figure")
    args = parser.parse_args()
    result = prepare(args.sources, args.output, args.join_contacting_shells, args.id_prefix)
    print(json.dumps({"parts": result["part_count"], "valid_volumes": result["all_meshes_valid_volumes"]}))
    raise SystemExit(0 if result["all_meshes_valid_volumes"] else 1)
