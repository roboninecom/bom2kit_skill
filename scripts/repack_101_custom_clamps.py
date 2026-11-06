"""Regroup unchanged custom clamps, PSUs and AC cords in BOX3 and BOX6."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
import trimesh
from bom2kit.mesh_validation import validate_mesh_layout

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text())


def write_group(name, problem, layout):
    result = validate_mesh_layout(problem, layout)
    output = ROOT / "packaging-results/so-arm-101" / name
    output.mkdir(exist_ok=True)
    for key, value in (("input", problem), ("layout", layout), ("validation", result)):
        (output / f"{key}.json").write_text(json.dumps(value, indent=2))
    print(name, result["valid"], result["errors"], flush=True)
    if not result["valid"]:
        raise ValueError(result)


def box_pose(item, number, corner):
    transform = np.eye(4)
    transform[:3, 3] = np.array(corner) + np.array(item["dimensions_mm"]) / 2
    return {"item_id": item["id"], "unit_id": f'{item["id"]}#{number}', "transform": transform.tolist()}


def main():
    power = read("packaging-results/so-arm-101/box6-folded-packets/input.json")
    items = {i["id"]: i for i in power["items"]}
    psus = [items["PSU12_with_DC_lead"], items["PSU5_with_DC_lead"]]
    problem = {"units": "mm", "container": {"inner_mm": [243, 72.2, 49]},
               "clearance_mm": .1, "items": psus}
    layout = {"units": "mm", "placements": [box_pose(psus[0], 1, [0, 0, 0]),
                                                box_pose(psus[1], 1, [120.1, 0, 0])]}
    # A flexible USB packet can be divided into two labelled bags without
    # shrinking its total declared envelope volume or changing its contents.
    usb = deepcopy(items["USB_packet"])
    parts = []
    for x in (0, 110.1):
        mesh = trimesh.creation.box([110, 20, 30])
        mesh.apply_translation([x + 55, 62.1, 15])
        parts.append(mesh)
    mesh = trimesh.util.concatenate(parts)
    path = ROOT / "packaging-results/so-arm-101/box3-power/usb-two-bags.json"
    path.parent.mkdir(exist_ok=True)
    basis = ("BOM-based flexible packing assumption: two labelled 110 x 30 x 20 mm bags, "
             "one 1.5 m USB cable and one adapter each. Total envelope volume 132 cm3 equals "
             "the former single 110 x 60 x 20 mm packet. Assumed 3.5 mm cable diameter gives "
             "14.4 cm3 wire per 66 cm3 bag; connectors, adapter and folding use the remainder. "
             "This is a packing-state estimate, not a measured bend or adapter envelope.")
    path.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(),
                                "triangles": mesh.faces.tolist(), "provenance": basis}, indent=2))
    usb["mesh"] = {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}
    usb.pop("dimensions_mm", None)
    usb["dimension_basis"] = basis
    usb["packing_state"] = "Two subbags form the original USB packet BOM identity; place beside the PSUs."
    problem["items"].append(usb)
    layout["placements"].append({"item_id": "USB_packet", "unit_id": "USB_packet#1", "transform": np.eye(4).tolist()})
    write_group("box3-power", problem, layout)
    clamps = read("packaging-results/evidence-audit/purchased-assumptions/clamp-custom106-historical-four-problem.json")
    layout = read("packaging-results/evidence-audit/purchased-assumptions/clamp-custom106-historical-four-layout.json")
    cord = items["regional_AC_cord_packet"]
    problem = deepcopy(clamps)
    problem["items"].append(cord)
    problem["items"][0]["dimension_basis"] = "User-confirmed custom 106 mm frame; unchanged historical 140 x 40 x 52 mm assembled proxy, including 110 mm shaft and 40 mm knob. Other dimensions are estimates."
    problem["dunnage_assumption"] = "A 135 x 40 x 0.1 mm separator between the two cord packets."
    layout["placements"] += [box_pose(cord, 1, [0, 122.1, 0]), box_pose(cord, 2, [0, 122.1, 30.1])]
    write_group("box6-custom-clamps-cords", problem, layout)


if __name__ == "__main__":
    main()
