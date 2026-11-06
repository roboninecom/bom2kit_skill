"""Check work-surface assembly directions for the two lower102 cyclic groups."""
from copy import deepcopy
from collections import Counter
import itertools
import json
from pathlib import Path
import sys

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_motion import check_vertical_sequence
from bom2kit.report import fingerprint


def main():
    directory = ROOT / "packaging-results/so-arm-102/complete-kit"
    problem = json.loads((directory / "input.json").read_text())
    layout = json.loads((directory / "layout.json").read_text())
    items = {item["id"]: item for item in problem["items"]}
    poses = {pose["unit_id"]: pose for pose in layout["placements"]}
    groups = {
        "lower-base-holder-cluster": ["adapter_protected_packet#2", "bottom#3", "bottom#4", "SO102.02.010 Base#1", "SO102.02.010 Base#2", "servo#1", "servo#2"],
        "lower-wrist-clamp-pair": ["RB9.01.062.025 Clamp (D6.1)#2", "SO102 Wrist roll#1"],
    }
    directions = [[0, 0, 1], [0, 0, -1], [1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0]]
    directions += [list(d) for d in itertools.product((-1, 0, 1), repeat=3) if sum(bool(x) for x in d) > 1]
    for name, members in groups.items():
        output = directory / "internal-motion" / name
        output.mkdir(parents=True, exist_ok=True)
        attempts = []
        preferred = [0, 1, 0] if name == "lower-base-holder-cluster" else [1, 0, 0]
        for direction in [preferred] + [d for d in directions if d != preferred]:
            rotation = trimesh.geometry.align_vectors(direction, [0, 0, 1])
            transformed, points, seen, mapping = [], [], Counter(), {}
            for uid in members:
                pose = deepcopy(poses[uid])
                iid = pose["item_id"]
                seen[iid] += 1
                pose["unit_id"] = iid + f"#{seen[iid]}"
                mapping[pose["unit_id"]] = uid
                transform = rotation @ np.asarray(pose["transform"])
                pose["transform"] = transform.tolist()
                mesh = json.loads(Path(items[iid]["mesh"]["path"]).read_text())
                points.append(trimesh.transform_points(np.asarray(mesh["vertices_mm"]), transform))
                transformed.append(pose)
            all_points = np.concatenate(points)
            lower, upper = all_points.min(axis=0), all_points.max(axis=0)
            for pose in transformed:
                t = np.asarray(pose["transform"])
                t[:3, 3] -= lower
                pose["transform"] = t.tolist()
            selected = [dict(deepcopy(items[iid]), quantity=count) for iid, count in seen.items()]
            subset = {"units": "mm", "container": {"inner_mm": (upper - lower + .01).tolist()}, "clearance_mm": .1, "items": selected,
                      "source_input_sha256": fingerprint(problem), "source_layout_sha256": fingerprint(layout),
                      "source_unit_mapping": mapping, "source_rotation": rotation.tolist(), "source_rotated_minimum_mm": lower.tolist()}
            subset_layout = {"units": "mm", "placements": transformed}
            certificate = check_vertical_sequence(subset, subset_layout, time_limit=40)
            attempts.append({"original_removal_direction": direction, "certificate": certificate})
            (output / "attempts.json").write_text(json.dumps(attempts, indent=2))
            print(name, direction, certificate["valid"], certificate.get("unresolved_groups"), flush=True)
            if certificate["valid"]:
                for filename, value in (("input", subset), ("layout", subset_layout), ("motion-validation", certificate)):
                    (output / f"{filename}.json").write_text(json.dumps(value, indent=2))
                break


if __name__ == "__main__":
    main()
