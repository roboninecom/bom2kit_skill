"""Assemble current102 geometry and declared purchased-item envelopes without resizing solids."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_validation import validate_mesh_layout
from bom2kit.validation import validate
from bom2kit.assessment import assess_mesh_kit


def read(path):
    return json.loads(path.read_text())


def main():
    out = ROOT / "packaging-results/so-arm-102/complete-kit"
    out.mkdir(parents=True, exist_ok=True)
    items, poses, sources, cartons, carton_poses = [], [], [], [], []
    groups = [
        ("LOWER", ROOT / "packaging-results/so-arm-102/lower-usb-fasteners", "layout.json", [1.5, 1.5, 1.5], False),
        ("UPPER_ARMS", ROOT / "packaging-results/so-arm-102/current-four-arm-top", "compact-65-layout.json", [0.05, 0.05, 75.05], True),
        ("CLAMPS_SERVOS_EXTRAS", ROOT / "packaging-results/so-arm-102/upper-clamps-servos", "layout.json", [204.15, 0.05, 75.05], True),
    ]
    group_bounds = {}

    def append_group(group_id, problem, layout, position, normalize=True):
        meshes = {i["id"]: np.asarray(read(Path(i["mesh"]["path"]))["vertices_mm"]) for i in problem["items"]}
        points = np.concatenate([trimesh.transform_points(meshes[p["item_id"]], p["transform"]) for p in layout["placements"]])
        minimum, maximum = points.min(axis=0), points.max(axis=0)
        delta = np.asarray(position) - (minimum if normalize else np.zeros(3))
        for item in deepcopy(problem["items"]):
            item["packing_group"] = group_id
            if item["id"] == "custom_106mm_clamp_proxy":
                item["dimension_basis"] = "User-confirmed custom106 mm frame; unchanged historical140x40x52 proxy; other dimensions remain assumptions."
            items.append(item)
        for pose in deepcopy(layout["placements"]):
            transform = np.asarray(pose["transform"], dtype=float)
            transform[:3, 3] += delta + 15
            pose["transform"] = transform.tolist()
            poses.append(pose)
        group_bounds[group_id] = (maximum - minimum).tolist()
        if normalize:
            dimensions = maximum - minimum + .1
            base = np.asarray(position) - .05
        else:
            dimensions, base = np.array([332, 246, 75]), np.zeros(3)
        cartons.append({"id": group_id, "quantity": 1, "dimensions_mm": dimensions.tolist(), "allowed_rotations": [[0, 1, 2]]})
        carton_poses.append({"item_id": group_id, "unit_id": group_id + "#1", "position_mm": (base + 15).tolist(), "dimensions_mm": dimensions.tolist(), "rotation": [0, 1, 2]})

    for group_id, directory, filename, position, normalize in groups:
        problem_path, layout_path = directory / "input.json", directory / filename
        append_group(group_id, read(problem_path), read(layout_path), position, normalize)
        sources.append({"group": group_id, "input": str(problem_path), "input_sha256": sha256(problem_path.read_bytes()).hexdigest(), "layout": str(layout_path), "layout_sha256": sha256(layout_path.read_bytes()).hexdigest()})
    directory = ROOT / "packaging-results/so-arm-102/box7-independent-wrists"
    box7_y = .05 + group_bounds["UPPER_ARMS"][1] + .1
    append_group("BOX7", read(directory / "input.json"), read(directory / "layout.json"), [.05, box7_y, 75.05])
    sources.append({"group": "BOX7", "input": str(directory / "input.json"), "input_sha256": sha256((directory / "input.json").read_bytes()).hexdigest(), "layout": str(directory / "layout.json"), "layout_sha256": sha256((directory / "layout.json").read_bytes()).hexdigest()})
    catalogue_path = ROOT / "packaging-inputs/benchmarks/purchased-assumptions/102-regional-cords-flat.json"
    catalogue = read(catalogue_path)
    cord = next(deepcopy(i) for i in catalogue["items"] if i["id"] == "regional_AC_cord_packet")
    cord["dimensions_mm"] = [100, 27, 60]
    cord["packing_state_change"] = "Flexible folded packet100x27x60 preserves162cm3 previous135x40x30 packet volume. Primary plug bounds and supplier/folding uncertainty retained from the referenced catalogue. No measured complete packet is claimed."
    cord["catalogue_path"] = str(catalogue_path)
    cord["catalogue_sha256"] = sha256(catalogue_path.read_bytes()).hexdigest()
    mesh = trimesh.creation.box(extents=cord["dimensions_mm"])
    mesh.apply_translation(-mesh.bounds[0])
    path = out / "cord-envelope.json"
    path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist(), "assumption": cord}, indent=2))
    cord["mesh"] = {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}
    cord_y = box7_y + group_bounds["BOX7"][1] + .1
    cord_layout = {"placements": [{"item_id": cord["id"], "unit_id": cord["id"] + f"#{n+1}", "transform": [[1, 0, 0, n * 100.1], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]} for n in range(2)]}
    append_group("AC_CORDS", {"items": [cord]}, cord_layout, [.05, cord_y, 75.05])
    container = {"inner_mm": [362, 276, 170], "wall_mm": 7, "protection_mm": 15, "reserved_top_mm": .8}
    problem = {"units": "mm", "container": container, "reference": {"external_mm": [376, 290, 184]}, "clearance_mm": .1,
               "custom_frame_length_mm": 106, "items": items, "provenance": sources,
               "scope": "Complete canonical BOM under explicit purchased-item envelope assumptions. Physical qualification remains unverified.",
               "assumptions": ["Lower carton retains1.5mm walls and75mm outer height.", "Upper groups replace inner rigid cartons with0.05mm film per face; the15mm outer EPE liner remains.", "Ten upper servos use1mm EPE envelopes; two lower servos retain2mm EPE envelopes. Cushioning equivalence unverified.", "Booklet thickness assumed0.8mm; a reserved slab is not a measured booklet model."]}
    mapping_path = ROOT / "packaging-inputs/benchmarks/so-arm-102-canonical-mapping.json"
    mapping = read(mapping_path)
    for item in items:
        item["contents"] = deepcopy(mapping["mesh_item_contents"][item["id"]])
    bom = deepcopy(mapping["expected_bom"])
    problem["canonical_mapping"] = {"path": str(mapping_path), "sha256": sha256(mapping_path.read_bytes()).hexdigest(), "authority": mapping["authority"]}
    layout = {"units": "mm", "placements": poses}
    outer = {"units": "mm", "container": container, "reference": problem["reference"], "items": cartons, "gap_mm": 0}
    outer_layout = {"units": "mm", "placements": carton_poses}
    started = perf_counter()
    certificate = validate_mesh_layout(problem, layout)
    outer_certificate = validate(outer, outer_layout)
    assessment = assess_mesh_kit(bom, problem, layout)
    for name, value in (("input", problem), ("layout", layout), ("validation", certificate), ("bom", bom), ("assessment", assessment), ("outer-input", outer), ("outer-layout", outer_layout), ("outer-validation", outer_certificate), ("timing", {"validation_seconds": perf_counter() - started})):
        (out / f"{name}.json").write_text(json.dumps(value, indent=2))
    print(json.dumps({"computational_acceptance": assessment["computational_acceptance"], "bom_complete": assessment["coverage"]["complete"], "mesh_valid": certificate["valid"], "mesh_errors": certificate["errors"], "units": len(poses), "outer": outer_certificate, "group_bounds": group_bounds}, indent=2))


if __name__ == "__main__":
    main()
