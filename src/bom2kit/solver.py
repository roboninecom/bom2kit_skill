"""Bounded deterministic extreme-coordinate search; no optimality claim."""

from itertools import product
from itertools import combinations
import math
import time

from .models import normalize, number
from .validation import validate

EPS = 1e-7


def _intersects(a, b, gap=0):
    if a.get("kind") == "dunnage" or b.get("kind") == "dunnage":
        gap = 0
    p, d = a["position_mm"], a["dimensions_mm"]
    q, e = b["position_mm"], b["dimensions_mm"]
    return all(p[k] < q[k] + e[k] + (gap if k < 2 else 0) - EPS and
               q[k] < p[k] + d[k] + (gap if k < 2 else 0) - EPS for k in range(3))


def _support_pads(candidate, placements, floor):
    """Partition a footprint into disjoint columns and fill voids below it."""
    p, d = candidate["position_mm"], candidate["dimensions_mm"]
    if abs(p[2] - floor) < EPS:
        return []
    cuts = []
    for k in (0, 1):
        cuts.append(sorted({p[k], p[k] + d[k]} | {
            edge for other in placements for edge in
            (other["position_mm"][k], other["position_mm"][k] + other["dimensions_mm"][k])
            if p[k] < edge < p[k] + d[k]}))
    pads = []
    for x0, x1 in zip(cuts[0], cuts[0][1:]):
        for y0, y1 in zip(cuts[1], cuts[1][1:]):
            top = floor
            for other in placements:
                q, e = other["position_mm"], other["dimensions_mm"]
                if q[0] < x1 - EPS and q[0] + e[0] > x0 + EPS and q[1] < y1 - EPS and q[1] + e[1] > y0 + EPS:
                    if q[2] + e[2] > p[2] + EPS:
                        return None
                    top = max(top, q[2] + e[2])
            if top < p[2] - EPS:
                pads.append({"position_mm": [x0, y0, top], "dimensions_mm": [x1 - x0, y1 - y0, p[2] - top]})
    return pads


def solve(problem, max_nodes=100000, time_limit=5, seed=0):
    """Find one complete supported layout within a bounded search budget.

    gap_mm is lateral clearance. seed is accepted for CLI compatibility;
    search is deliberately deterministic. Exhaustion is not an impossibility proof.
    """
    del seed
    data = normalize(problem)
    start = time.perf_counter()
    if type(max_nodes) is not int or max_nodes < 1:
        raise ValueError("max_nodes must be a positive integer")
    time_limit = number(time_limit, "time_limit", True)
    low, high = data["protection"], data["upper"]
    nodes, budget_hit = 0, False
    available = math.prod(b - a for a, b in zip(low, high))
    required = sum(math.prod(u["dimensions"]) for u in data["units"])
    base = {"placements": [], "container": problem["container"],
            "external_mm": list(data["external"]), "external_volume_l": math.prod(data["external"]) / 1e6}
    if required > available + EPS or any(not any(all(d <= b - a + EPS for d, a, b in zip(size, low, high))
           for _, size in u["orientations"]) for u in data["units"]):
        return {**base, "status": "infeasible", "reason": "Volume or individual size lower bound",
                "stats": {"nodes": 0, "elapsed_seconds": time.perf_counter() - start}}
    remaining = sorted(data["units"], key=lambda u: (-max(o[1][2] for o in u["orientations"]), -math.prod(u["dimensions"]), u["unit_id"]))
    failed = set()

    def layer_search(todo, placed, z):
        """Try equal-height layer partitions before general 3-D branching."""
        nonlocal nodes, budget_hit
        if not todo:
            return placed
        if len(todo) > 14:
            return None
        heights = sorted({size[2] for unit in todo for _, size in unit["orientations"]
                          if z + size[2] <= high[2] + EPS})
        groups = []
        area = (high[0] - low[0]) * (high[1] - low[1])
        for height in heights:
            eligible = [u for u in todo if any(abs(s[2] - height) < EPS for _, s in u["orientations"])]
            for count in range(len(eligible), 0, -1):
                for group in combinations(eligible, count):
                    footprint = sum(math.prod(u["dimensions"]) / height for u in group)
                    if footprint <= area + EPS:
                        groups.append((-footprint / area, -len(group), height, group))
        groups.sort(key=lambda g: g[:3])
        for _, _, height, group in groups:
            if time.perf_counter() - start >= time_limit or nodes >= max_nodes:
                budget_hit = True
                return None
            ids = {u["unit_id"] for u in group}

            def tile(pending, layer):
                nonlocal nodes, budget_hit
                if not pending:
                    return layer_search([u for u in todo if u["unit_id"] not in ids], placed + layer, z + height)
                for index, unit in enumerate(pending):
                    for rotation, size in unit["orientations"]:
                        if abs(size[2] - height) > EPS:
                            continue
                        xs, ys = {low[0], high[0] - size[0]}, {low[1], high[1] - size[1]}
                        for other in layer:
                            q, d = other["position_mm"], other["dimensions_mm"]
                            xs.update((q[0] + d[0] + data["gap"], q[0], q[0] + d[0] - size[0]))
                            ys.update((q[1] + d[1] + data["gap"], q[1], q[1] + d[1] - size[1]))
                        for y, x in product(sorted(ys), sorted(xs)):
                            nodes += 1
                            if nodes >= max_nodes or (nodes % 256 == 0 and time.perf_counter() - start >= time_limit):
                                budget_hit = True
                                return None
                            if x < low[0] - EPS or y < low[1] - EPS or x + size[0] > high[0] + EPS or y + size[1] > high[1] + EPS:
                                continue
                            candidate = {"item_id": unit["item_id"], "unit_id": unit["unit_id"], "position_mm": [x, y, z],
                                         "dimensions_mm": list(size), "rotation": list(rotation)}
                            if any(_intersects(candidate, other, data["gap"]) for other in layer):
                                continue
                            pads = _support_pads(candidate, placed, low[2])
                            if pads is None or pads:
                                continue
                            found = tile(pending[:index] + pending[index + 1:], layer + [candidate])
                            if found is not None:
                                return found
                            if budget_hit:
                                return None
                return None

            found = tile(sorted(group, key=lambda u: -math.prod(u["dimensions"])), [])
            if found is not None:
                return found
            if budget_hit:
                return None
        return None

    def visit(todo, placed):
        nonlocal nodes, budget_hit
        if not todo:
            return placed
        if nodes >= max_nodes or time.perf_counter() - start >= time_limit:
            budget_hit = True
            return None
        key = (tuple(u["unit_id"] for u in todo), tuple(sorted((p["item_id"], tuple(p["position_mm"]), tuple(p["dimensions_mm"])) for p in placed)))
        if key in failed:
            return None
        considered = set()
        for index, unit in enumerate(todo):
            if unit["item_id"] in considered:
                continue
            considered.add(unit["item_id"])
            for rotation, size in unit["orientations"]:
                axes = []
                for k in range(3):
                    coords = {low[k]}
                    if k < 2:
                        coords.add(high[k] - size[k])
                    for other in placed:
                        edge = other["position_mm"][k] + other["dimensions_mm"][k]
                        coords.add(edge + (data["gap"] if k < 2 else 0))
                        if k < 2:
                            coords.update((other["position_mm"][k], edge - size[k], other["position_mm"][k] - size[k] - data["gap"]))
                    axes.append(sorted(c for c in coords if low[k] - EPS <= c <= high[k] - size[k] + EPS))
                for z, y, x in product(axes[2], axes[1], axes[0]):
                    nodes += 1
                    if nodes > max_nodes or (nodes % 256 == 0 and time.perf_counter() - start >= time_limit):
                        budget_hit = True
                        return None
                    candidate = {"item_id": unit["item_id"], "unit_id": unit["unit_id"],
                                 "position_mm": [x, y, z], "dimensions_mm": list(size), "rotation": list(rotation)}
                    if any(_intersects(candidate, other, data["gap"]) for other in placed):
                        continue
                    pads = _support_pads(candidate, placed, low[2])
                    if pads is None or (pads and not problem.get("allow_dunnage", False)):
                        continue
                    pad_placements = []
                    for number, pad in enumerate(pads):
                        pad_id = f"__support__{unit['unit_id']}__{number}"
                        pad_placements.append({**pad, "kind": "dunnage", "item_id": pad_id,
                                               "unit_id": pad_id, "rotation": [0, 1, 2]})
                    # Pads are structural support, not packed products; apply collision
                    # checks but no product-to-product handling clearance to pads.
                    if any(_intersects(pad, other) for pad in pad_placements for other in placed):
                        continue
                    found = visit(todo[:index] + todo[index + 1:], placed + pad_placements + [candidate])
                    if found is not None:
                        return found
                    if budget_hit:
                        return None
        failed.add(key)
        return None

    placements = layer_search(remaining, [], low[2])
    if placements is None and not budget_hit:
        placements = visit(remaining, [])
    result = {**base, "status": "feasible" if placements is not None else "search_exhausted",
              "placements": placements or [], "stats": {"nodes": nodes, "elapsed_seconds": time.perf_counter() - start,
              "budget_hit": budget_hit, "algorithm": "equal_height_layers_then_extreme_coordinates"}}
    if placements is not None:
        result["validation"] = validate(problem, result)
        if not result["validation"]["valid"]:
            result["status"] = "validation_failed"
    return result
