"""Discover small assembly-checked groups from individual geometry, without recipes."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter


def rank_pair_proposals(proposals, limit):
    """Balance potential void savings against repeatedly explored part types.

    Each proposal is (negative empty volume, first index, second index).
    This is a search heuristic, not a geometric savings bound. Repeated types
    receive diminishing priority so a short budget explores different shapes.
    """
    remaining = list(proposals)
    exposure = {}
    selected = []
    while remaining and len(selected) < limit:
        proposal = min(remaining, key=lambda p: (
            p[0] / (1 + sum(exposure.get(i, 0) for i in set(p[1:]))), p))
        remaining.remove(proposal)
        selected.append(proposal)
        for index in set(proposal[1:]):
            exposure[index] = exposure.get(index, 0) + 1
    return selected


def check_workbench_axes(problem, layout):
    """Check straight assembly along six source-frame axes on an open workbench."""
    import numpy as np
    import trimesh
    from .mesh_motion import check_vertical_sequence

    sources = {item["id"]: json.loads(Path(item["mesh"]["path"]).read_text()) for item in problem["items"]}
    points = np.concatenate([trimesh.transform_points(np.array(sources[p["item_id"]]["vertices_mm"]), p["transform"])
                             for p in layout["placements"]])
    for axis in (2, 0, 1):
        for sign in (1, -1):
            z = np.eye(3)[axis] * sign
            x = np.eye(3)[(axis + 1) % 3]
            rotation = np.array([x, np.cross(z, x), z])
            rotated = points @ rotation.T
            frame = np.eye(4)
            frame[:3, :3] = rotation
            frame[:3, 3] = -rotated.min(axis=0) + 1
            candidate = {"units": "mm", "placements": [
                {**p, "transform": (frame @ np.asarray(p["transform"])).tolist()} for p in layout["placements"]]}
            workbench = {**problem, "container": {"inner_mm": (np.ptp(rotated, axis=0) + 2).tolist()}}
            motion = check_vertical_sequence(workbench, candidate, time_limit=5)
            if motion["valid"]:
                return {"input": workbench, "layout": candidate, "certificate": motion,
                        "source_to_workbench": frame.tolist(), "source_removal_direction": z.tolist()}
    return None


def discover_pairs(library, output, clearance_mm, time_limit=60, pair_seconds=5, max_pairs=8):
    """Generate a bounded portfolio balancing empty volume and shape diversity.

    Returns alternatives, not an asserted best complete-kit grouping. Original
    quantities are not consumed: the global selector must resolve membership.
    Every accepted pair has an original-source assembly certificate.
    """
    import numpy as np
    import trimesh
    from .mesh_packing import solve_mesh_pair
    from .models import number

    started = perf_counter()
    clearance_mm = number(clearance_mm, "clearance_mm", True)
    time_limit = number(time_limit, "time_limit", True)
    pair_seconds = number(pair_seconds, "pair_seconds", True)
    if type(max_pairs) is not int or max_pairs < 1:
        raise ValueError("max_pairs must be positive")
    if library.get("units") != "mm" or not library.get("all_meshes_valid_volumes"):
        raise ValueError("Verified mm source library required")
    identities = [item.get("id") for item in library.get("items", [])]
    if not identities or any(not isinstance(i, str) or not i for i in identities) or len(set(identities)) != len(identities):
        raise ValueError("Unique nonempty part identities required")
    if any(type(item.get("quantity")) is not int or item["quantity"] < 1 for item in library["items"]):
        raise ValueError("Positive integer quantities required")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    def write(path, value):
        path.write_text(json.dumps(value, allow_nan=False), encoding="utf8")

    prepared = []
    for item in library["items"]:
        ref = item["mesh"]
        raw = Path(ref["path"]).read_bytes()
        if sha256(raw).hexdigest() != ref["sha256"]:
            raise ValueError("Source hash mismatch")
        data = json.loads(raw)
        if data.get("units") != "mm":
            raise ValueError("Source geometry must use mm")
        mesh = trimesh.Trimesh(data["vertices_mm"], data["triangles"], process=False)
        if not mesh.is_volume or np.any(mesh.area_faces <= 0):
            raise ValueError("Invalid source geometry")
        frame, _ = trimesh.bounds.oriented_bounds(mesh)
        mesh.apply_transform(frame)
        shift = -mesh.bounds[0]
        frame[:3, 3] += shift
        mesh.apply_translation(shift)
        path = output / (ref["sha256"] + "-oriented.json")
        write(path, {"units": "mm", "vertices_mm": mesh.vertices.tolist(), "triangles": mesh.faces.tolist()})
        prepared.append({"item": item, "mesh": mesh, "frame": frame,
                         "ref": {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()},
                         "box_volume": float(np.prod(mesh.extents))})
    proposals = []
    for i, a in enumerate(prepared):
        for j in range(i, len(prepared)):
            b = prepared[j]
            if i == j and a["item"]["quantity"] < 2:
                continue
            empty = a["box_volume"] + b["box_volume"] - a["mesh"].volume - b["mesh"].volume
            proposals.append((-float(empty), i, j))
    attempts, alternatives = [], []
    for _, i, j in rank_pair_proposals(proposals, max_pairs):
        remaining = time_limit - (perf_counter() - started)
        if remaining <= 0:
            break
        a, b = prepared[i], prepared[j]
        # An unconstraining cube derives solely from individual geometry. It
        # permits every separated orientation; it is not a shipping-box target.
        span = float(max(a["mesh"].extents) + max(b["mesh"].extents) + 4 * clearance_mm)
        problem = {"units": "mm", "clearance_mm": clearance_mm,
                   "container": {"inner_mm": [span] * 3}, "items": [
                       {"id": name, "quantity": 1, "mesh": entry["ref"]}
                       for name, entry in (("a", a), ("b", b))]}
        result = solve_mesh_pair(problem, time_limit=min(pair_seconds, remaining), pitch_mm=2)
        attempt = {"members": [a["item"]["id"], b["item"]["id"]], "search": result["search"],
                   "status": result["status"]}
        attempts.append(attempt)
        if result["status"] != "validated_static_layout":
            continue
        separate = a["box_volume"] + b["box_volume"]
        if result["envelope_volume_l"] * 1e6 >= separate - 1e-6:
            attempt["status"] = "no_envelope_saving"
            continue
        original_items, original_poses = [], []
        used = {}
        for entry, pose in zip((a, b), result["placements"]):
            item = entry["item"]
            uid = item["id"] + "#" + str(used.get(item["id"], 0) + 1)
            used[item["id"]] = used.get(item["id"], 0) + 1
            original_poses.append({"item_id": item["id"], "unit_id": uid,
                                   "transform": (np.asarray(pose["transform"]) @ entry["frame"]).tolist()})
        for entry in (a, b):
            iid = entry["item"]["id"]
            if not any(item["id"] == iid for item in original_items):
                original_items.append({"id": iid, "quantity": used[iid], "mesh": entry["item"]["mesh"]})
        original = {**problem, "items": original_items}
        layout = {"units": "mm", "placements": original_poses}
        assembly = check_workbench_axes(original, layout)
        if assembly is None:
            attempt["status"] = "assembly_unverified"
            continue
        alternatives.append({"members": deepcopy(attempt["members"]), "input": original, "layout": layout,
                             "assembly": assembly, "envelope_mm": result["envelope_mm"],
                             "separate_box_volume_mm3": separate,
                             "group_box_volume_mm3": result["envelope_volume_l"] * 1e6})
        attempt["status"] = "validated_pair_alternative"
    result = {"scope": "Independent pair alternatives, not a complete-kit result",
              "source_library_sha256": sha256(json.dumps(library, sort_keys=True).encode()).hexdigest(),
              "clearance_mm": clearance_mm, "alternatives": alternatives, "attempts": attempts,
              "elapsed_seconds": perf_counter() - started, "time_budget_seconds": time_limit,
              "deadline_scope": "Soft search deadline; geometry and motion verification may overrun"}
    write(output / "pairs.json", result)
    return result
