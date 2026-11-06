"""Recheck the complete R3 kit in five cartons at Alan's external volume."""
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
from bom2kit.assessment import assess_mesh_kit
from bom2kit.validation import validate


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf8")


def rigid_permutation(permutation):
    rotation = np.eye(3)[permutation]
    if np.linalg.det(rotation) < 0:
        rotation[0] *= -1
    return rotation


def main():
    output = ROOT / "packaging-results/so-arm-101/complete-kit"
    outer = read("packaging-results/regrouping/so-arm-101/merged_box1_box2_box4_h75_2/input.json")
    mapping = read("packaging-inputs/benchmarks/so-arm-101-canonical-mapping.json")
    catalogue = {i["id"]: i for i in outer["items"]}
    specs = [("MERGED_BOX1_BOX2_BOX4_H75_2", [15, 15, 15], [0, 1, 2]),
             ("BOX3", [283, 15, 15], [2, 0, 1]),
             ("BOX6", [15, 15, 90.2], [0, 1, 2]),
             ("BOX5", [211, 15, 90.2], [1, 0, 2]),
             ("BOX7", [15, 183, 90.2], [0, 1, 2])]
    outer_layout = {"units": "mm", "placements": [
        {"item_id": iid, "unit_id": iid + "#1", "position_mm": pos,
         "rotation": rot, "dimensions_mm": np.array(catalogue[iid]["dimensions_mm"])[rot].tolist()}
        for iid, pos, rot in specs]}
    outer_validation = validate(outer, outer_layout)
    if not outer_validation["valid"]:
        raise ValueError(outer_validation)
    sources = {
        "MERGED_BOX1_BOX2_BOX4_H75_2": ("packaging-results/so-arm-101/regrouped-without-camera/problem.json", "packaging-results/so-arm-101/regrouped-without-camera/layout.json"),
        "BOX3": ("packaging-results/so-arm-101/box3-power/input.json", "packaging-results/so-arm-101/box3-power/layout.json"),
        "BOX6": ("packaging-results/so-arm-101/box6-custom-clamps-cords/input.json", "packaging-results/so-arm-101/box6-custom-clamps-cords/layout.json"),
        "BOX5": ("packaging-inputs/benchmarks/purchased-assumptions/101-box5.json", "packaging-results/evidence-audit/purchased-assumptions/101-box5-result.json"),
        "BOX7": ("packaging-results/so-arm-101/box7-with-camera-fasteners/input.json", "packaging-results/so-arm-101/box7-with-camera-fasteners/layout.json")}
    items, placements, provenance = [], [], []
    for carton, position, permutation in specs:
        input_path, layout_path = sources[carton]
        group, layout = read(input_path), read(layout_path)
        if carton == "BOX6" and group.get("custom_frame_length_mm") != 106:
            raise ValueError("User confirmed a custom 106 mm clamp frame; the 80 mm catalogue proxy is superseded")
        if carton == "BOX5":
            group, layout = group["problem"], layout["result"]
            if not validate(group, layout)["valid"]:
                raise ValueError("Invalid factory servo packing")
            for item in group["items"]:
                mesh = trimesh.creation.box(item["dimensions_mm"])
                path = output / "meshes" / (item["id"] + ".json")
                write(path, {"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist()})
                item["mesh"] = {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}
            poses = []
            for pose in layout["placements"]:
                transform = np.eye(4)
                transform[:3, :3] = rigid_permutation(pose["rotation"])
                transform[:3, 3] = np.array(pose["position_mm"]) + np.array(pose["dimensions_mm"]) / 2
                poses.append({"item_id": pose["item_id"], "unit_id": pose["unit_id"], "transform": transform.tolist()})
            layout = {"placements": poses}
        rotation = rigid_permutation(permutation)
        interior = np.array(catalogue[carton]["inner_dimensions_mm"])
        offset = np.minimum(rotation, 0) @ interior
        transform = np.eye(4)
        transform[:3, :3] = rotation
        transform[:3, 3] = np.array(position) + 1.5 - offset
        group_contents = {}
        for item in group["items"]:
            item = deepcopy(item)
            item["contents"] = mapping["mesh_item_contents"][item["id"]]
            item["packing_group"] = carton
            for sku, quantity in item["contents"].items():
                group_contents[sku] = group_contents.get(sku, 0) + quantity * item["quantity"]
            items.append(item)
        catalogue[carton]["contents"] = group_contents
        for pose in layout["placements"]:
            placed = deepcopy(pose)
            placed["transform"] = (transform @ np.array(pose["transform"])).tolist()
            placements.append(placed)
        provenance.append({"carton": carton, "transform": transform.tolist(),
                           "input_path": input_path, "input_sha256": sha256((ROOT / input_path).read_bytes()).hexdigest(),
                           "layout_path": layout_path, "layout_sha256": sha256((ROOT / layout_path).read_bytes()).hexdigest()})
    problem = {"units": "mm", "container": outer["container"], "clearance_mm": .1,
               "custom_frame_length_mm": 106,
               "items": items, "reference": {"external_mm": [364, 290, 184]},
               "provenance": provenance, "assumptions": [
                   "User-authorized R3 contents, disassembled ArUco and bagged bearings.",
                   "Rigid printed source meshes remain unscaled; purchased packets use declared envelopes.",
                   "Five cardboard groups, 1.5 mm walls; merged printed carton and clamp carton raised to 75.2 mm.",
                   "15 mm external protection, 0.8 mm booklet allowance, 0.1 mm separator between AC cords.",
                   "Custom 106 mm clamps retain the unchanged historical 140 x 40 x 52 mm proxy; packed in BOX6 with cords.",
                   "BOX3 contains both PSUs and two USB subbags, preserving the original packet contents and total estimated bag volume.",
                   "The independently supplied R3 ledger uses explicit factory-box and packet-level BOM identities."]}
    layout = {"units": "mm", "placements": placements}
    started = perf_counter()
    assessment = assess_mesh_kit(mapping["expected_bom"], problem, layout)
    elapsed = perf_counter() - started
    for name, value in (("input", problem), ("layout", layout), ("bom", mapping["expected_bom"]),
                        ("assessment", assessment), ("outer-input", outer), ("outer-layout", outer_layout),
                        ("outer-validation", outer_validation), ("timing", {"assessment_seconds": elapsed})):
        write(output / (name + ".json"), value)
    print(json.dumps({"accepted": assessment["computational_acceptance"], "units": len(placements),
                      "errors": assessment["geometry"]["errors"],
                      "bom_complete": assessment["coverage"]["complete"],
                      "volume_l": assessment["external_volume_l"], "seconds": elapsed}))
    return 0 if assessment["computational_acceptance"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
