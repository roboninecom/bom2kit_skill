"""Reference-free carton generation for already protected rectangular units.

This is the outer-carton stage of the future hierarchical designer. It does not
infer meshes, groups, or protective materials. No layout/reference is accepted.
"""

from copy import deepcopy
from hashlib import sha256
import json
import math
from time import perf_counter

from .models import normalize, number, vector
from .solver import solve
from .validation import validate
from .strip_packing import pack_strip


def _fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def design_carton(request, time_limit=5):
    """Generate dimensions from item spans and retain independently valid layouts.

    Time is bounded between candidates; an individual legacy solver call has a
    soft deadline. The conservative shelf baseline guarantees a candidate when
    no manufacturing maximum excludes it, not an optimal candidate.
    """
    started = perf_counter()
    time_limit = number(time_limit, "time_limit", True)
    if not isinstance(request, dict) or set(request) - {"units", "items", "policy"}:
        raise ValueError("Only units, items and policy are allowed; reference/layout inputs are forbidden")
    if request.get("units") != "mm":
        raise ValueError("Explicit mm units required")
    policy = request.get("policy", {})
    allowed_policy = {"wall_mm", "protection_mm", "reserved_top_mm", "gap_mm",
                      "dimension_increment_mm", "max_external_mm", "inner_wall_mm", "refine_footprints", "placement_score", "item_order", "unequal_columns"}
    if not isinstance(policy, dict) or set(policy) - allowed_policy:
        raise ValueError("Unsupported packing policy field")
    if policy.get("item_order","area") not in ("area","volume"):
        raise ValueError("Unknown item order")
    if policy.get("placement_score","bottom_left") not in ("bottom_left","short_side","area"):
        raise ValueError("Unknown rectangle placement score")
    allowed_item = {"id", "quantity", "dimensions_mm", "allowed_rotations"}
    if not isinstance(request.get("items"), list) or any(
            not isinstance(item, dict) or set(item) - allowed_item for item in request["items"]):
        raise ValueError("Envelope items may contain only id, quantity, dimensions_mm and allowed_rotations")
    wall = vector(policy.get("wall_mm", 0), "wall_mm")
    protection = vector(policy.get("protection_mm", 0), "protection_mm")
    reserve = number(policy.get("reserved_top_mm", 0), "reserved_top_mm")
    gap = number(policy.get("gap_mm", 0), "gap_mm")
    increment = number(policy.get("dimension_increment_mm", 1), "dimension_increment_mm", True)
    maximum = vector(policy["max_external_mm"], "max_external_mm", True) if "max_external_mm" in policy else None
    items = deepcopy(request["items"])
    # Normalize identities/rotations using a temporary cavity derived solely
    # from item dimensions. It is not a target or a source of placement poses.
    span = sum(max(vector(i.get("dimensions_mm"), "dimensions_mm", True)) *
               number(i.get("quantity", 1), "quantity", True) for i in items) + gap * len(items) + 1
    shell = [2 * (wall[k] + protection[k]) + (reserve if k == 2 else 0) for k in range(3)]
    base = {"units": "mm", "items": items, "gap_mm": gap,
            "container": {"inner_mm": [span + shell[k] for k in range(3)]}}
    units = normalize(base)["units"]
    prepared = perf_counter()
    best, attempts, seen = None, [], set()
    validation_seconds = 0.0
    if "inner_wall_mm" in policy:
        from .layered_design import design_layers
        layered = design_layers(request, units, time_limit=time_limit*.5)
        best = layered["candidate"]
        attempts.extend({**a,"method":"generated_inner_carton_layers"} for a in layered["attempts"])

    def problem_for(usable):
        external = [math.ceil((usable[k] + shell[k]) / increment - 1e-10) * increment for k in range(3)]
        if maximum and any(a > b + 1e-8 for a, b in zip(external, maximum)):
            return None
        return {"units": "mm", "items": items, "gap_mm": gap,
                "container": {"inner_mm": [external[k] - 2 * wall[k] for k in range(3)],
                              "wall_mm": list(wall), "protection_mm": list(protection),
                              "reserved_top_mm": reserve}}

    def accept(problem, layout, method):
        nonlocal best, validation_seconds
        external = normalize(problem)["external"]
        volume = math.prod(external)
        if best is not None and volume >= best["volume_mm3"] - 1e-8:
            attempts.append({"method": method, "external_mm": list(external), "valid": None,
                             "status": "not_better_than_verified_incumbent"})
            return
        tick = perf_counter()
        certificate = validate(problem, layout)
        validation_seconds += perf_counter() - tick
        attempts.append({"method": method, "external_mm": list(external), "valid": certificate["valid"]})
        if certificate["valid"] and (best is None or volume < best["volume_mm3"] - 1e-8):
            best = {"input": deepcopy(problem), "layout": deepcopy(layout), "validation": certificate,
                    "volume_mm3": volume, "external_mm": list(external)}

    # Several shape-derived widths and orientation choices produce supported
    # shelves from empty space. No prior pose or kit-specific dimensions enter.
    volume_lb = sum(math.prod(u["dimensions"]) for u in units)
    side = volume_lb ** (1 / 3)
    widths = {side * factor for factor in (.5, .75, 1, 1.5, 2, 3)}
    widths.update(size[0] for u in units for _, size in u["orientations"])
    widths.add(span)
    width_values = sorted(widths)
    # Limit candidate generation even for very large heterogeneous manifests.
    if len(width_values) > 48:
        width_values = [width_values[round(i * (len(width_values) - 1) / 47)] for i in range(48)]
    for orientation_mode in range(3):
        selected = [(u, min(u["orientations"], key=lambda o: (o[1][orientation_mode], o[1]))) for u in units]
        selected.sort(key=lambda pair: (-pair[1][1][2], -pair[1][1][1], -pair[1][1][0], pair[0]["unit_id"]))
        for width in reversed(width_values):
            if perf_counter() - started >= time_limit:
                break
            poses, x, y, row_depth, max_x, height = [], 0.0, 0.0, 0.0, 0.0, 0.0
            for unit, (rotation, size) in selected:
                if x > 0 and x + size[0] > width + 1e-8:
                    x, y, row_depth = 0.0, y + row_depth + gap, 0.0
                poses.append({"item_id": unit["item_id"], "unit_id": unit["unit_id"],
                              "position_mm": [x + protection[0], y + protection[1], protection[2]],
                              "dimensions_mm": list(size), "rotation": list(rotation)})
                max_x, row_depth, height = max(max_x, x + size[0]), max(row_depth, size[1]), max(height, size[2])
                x += size[0] + gap
            problem = problem_for([max_x, y + row_depth, height])
            if problem:
                accept(problem, {"placements": poses, "status": "feasible"}, "generated_shelves")
    # Fill two-dimensional voids instead of reserving an entire row per depth.
    # Heights and widths are generated from geometry, with per-item rotations.
    heights = sorted({s[2] for u in units for _, s in u["orientations"]})
    heights = [h for h in heights if all(any(s[2] <= h + 1e-8 for _, s in u["orientations"]) for u in units)]
    if len(heights) > 12:
        heights = [heights[round(i*(len(heights)-1)/11)] for i in range(12)]
    strip_widths = sorted({side*f for f in (.75,1,1.25,1.5,2)} | {max(s[0] for u in units for _,s in u["orientations"])})
    for height in heights:
        for width in strip_widths:
            if perf_counter() - started >= time_limit * .65:
                break
            strip = pack_strip(units, width, height, gap,placement_score=policy.get("placement_score","bottom_left"),item_order=policy.get("item_order","area"))
            if strip is None:
                continue
            problem = problem_for(strip["usable_mm"])
            if problem:
                for pose in strip["placements"]:
                    pose["position_mm"] = [v + protection[k] for k,v in enumerate(pose["position_mm"])]
                accept(problem, {"placements": strip["placements"], "status": "feasible"}, "generated_maximal_rectangles")
    # Search a compact dimension lattice, including stacked configurations.
    # Candidate feasibility is not monotone for this bounded heuristic, so do
    # not treat a failed search as an infeasibility proof or binary-search bound.
    axes = []
    for axis in range(3):
        lengths = {side * factor for factor in (.5, .75, 1, 1.25, 1.5, 2)}
        lengths.update(size[axis] for u in units for _, size in u["orientations"])
        values = sorted(lengths)
        if len(values) > 20:
            values = [values[round(i * (len(values) - 1) / 19)] for i in range(20)]
        axes.append(values)
    candidates = []
    for x in axes[0]:
        for y in axes[1]:
            for z in axes[2]:
                if perf_counter() - started >= time_limit:
                    break
                if x * y * z + 1e-8 < volume_lb:
                    continue
                if any(not any(all(s[k] <= (x, y, z)[k] + 1e-8 for k in range(3))
                               for _, s in u["orientations"]) for u in units):
                    continue
                problem = problem_for([x, y, z])
                if not problem:
                    continue
                key = tuple(problem["container"]["inner_mm"])
                if key in seen:
                    continue
                seen.add(key)
                volume = math.prod(key[k] + 2 * wall[k] for k in range(3))
                if best is None or volume < best["volume_mm3"] - 1e-8:
                    candidates.append((volume, key, problem))
    for volume, _, problem in sorted(candidates):
        remaining = time_limit - (perf_counter() - started)
        if remaining <= 0:
            break
        if best and volume >= best["volume_mm3"] - 1e-8:
            continue
        layout = solve(problem, time_limit=min(.2, remaining))
        accept(problem, layout, "generated_carton_search")
    elapsed = perf_counter() - started
    return {"status": "validated_envelope_design" if best else "no_verified_candidate",
            "candidate": best, "request_sha256": _fingerprint(request),
            "search": {"attempts": attempts, "time_budget_seconds": time_limit,
                       "preparation_seconds": prepared - started,
                       "search_seconds": max(0, elapsed - (prepared - started) - validation_seconds),
                       "validation_seconds": validation_seconds, "total_seconds": elapsed,
                       "optimality_proven": False, "reference_used": False},
            "scope": "Outer carton design for supplied protected envelopes; grouping and mesh design are separate stages"}
