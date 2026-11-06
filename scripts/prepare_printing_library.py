"""Build a neutral part library from a three-column printing BOM and source STLs.

This source adapter reads no packaging references or previously generated poses.
Part numbers, names and quantities come from the input Markdown table, never
from kit-specific constants. Ambiguous filenames are errors, not guesses.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def read_rows(text):
    rows = []
    for line in text.splitlines():
        columns = [column.strip() for column in line.strip().strip("|").split("|")]
        if not line.strip().startswith("|") or len(columns) != 3 or not columns[2].isdigit():
            continue
        number, name, quantity = columns
        if int(quantity) < 1:
            raise ValueError("Printing quantity must be positive")
        stem = name if number in ("—", "-", "") else f"{number} {name}"
        rows.append({"id": name if number in ("—", "-", "") else number,
                     "name": name, "quantity": int(quantity), "source_stem": stem})
    if not rows or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Expected a nonempty printing table with unique identities")
    return rows


def prepare(document, models, output, step_models=None):
    from bom2kit.mesh_preparation import load_print_mesh

    started = perf_counter()
    document, models, output = Path(document).resolve(), Path(models).resolve(), Path(output).resolve()
    raw = document.read_bytes()
    rows = read_rows(raw.decode("utf-8-sig"))
    files = {}
    for path in models.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".stl":
            files.setdefault(path.stem.casefold(), []).append(path)
    sources = []
    for row in rows:
        matches = files.get(row["source_stem"].casefold(), [])
        if len(matches) != 1:
            raise ValueError(f"Expected one exact STL for {row['source_stem']}; found {len(matches)}")
        sources.append(matches[0])
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for row, path in zip(rows, sources):
        # STL has no units: this adapter's explicit contract is source mm.
        # Merge shared vertices for topology checks; never rescale dimensions.
        step_matches = [p for p in Path(step_models).rglob("*")
                        if p.is_file() and p.suffix.lower() in (".stp", ".step")
                        and p.stem.casefold() == path.stem.casefold()] if step_models else []
        if len(step_matches) > 1:
            raise ValueError(f"Ambiguous STEP source for {path.stem}")
        mesh, audit = load_print_mesh(path, step_matches[0] if step_matches else None)
        translation = -mesh.bounds[0]
        mesh.apply_translation(translation)
        geometry = {"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist()}
        source_hash = sha256(path.read_bytes()).hexdigest()
        destination = output / (source_hash + ".json")
        destination.write_text(json.dumps(geometry, separators=(",", ":"), allow_nan=False), encoding="utf8")
        records.append({**row, "source": str(path), "source_sha256": source_hash,
                        "mesh": {"path": str(destination), "sha256": sha256(destination.read_bytes()).hexdigest()},
                        "source_to_local_translation_mm": translation.tolist(),
                        "dimensions_mm": mesh.extents.tolist(), "volume_mm3": float(mesh.volume),
                        "watertight_positive_volume": bool(mesh.is_volume),
                        "preparation_audit": audit,
                        "frame_policy": "Source orientation retained; source translation removed; no packing pose"})
    result = {"units": "mm", "scope": "Printed parts only; not a complete shipping BOM",
              "source_bom": str(document), "source_bom_sha256": sha256(raw).hexdigest(),
              "stl_units_assumption": "mm", "items": records,
              "part_types": len(records), "part_count": sum(row["quantity"] for row in records),
              "preparation_seconds": perf_counter() - started,
              "all_meshes_valid_volumes": all(row["watertight_positive_volume"] for row in records)}
    (output / "library.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("models", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--step-models", type=Path, help="Matching STEP sources for invalid STL topology")
    args = parser.parse_args()
    result = prepare(args.document, args.models, args.output, args.step_models)
    print(json.dumps({key: result[key] for key in ("part_types", "part_count", "preparation_seconds", "all_meshes_valid_volumes")}))
    raise SystemExit(0 if result["all_meshes_valid_volumes"] else 1)
