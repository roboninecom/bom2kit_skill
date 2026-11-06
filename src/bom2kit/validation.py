"""Independent verification of complete axis-aligned packing certificates."""

import math

from .models import normalize, vector

EPS = 1e-7


def _overlap(a, da, b, db):
    tolerance = min(EPS, min(da, db) * 1e-9)
    return min(a + da, b + db) - max(a, b) > tolerance


def _covered_area(rectangles):
    if not rectangles:
        return 0.0
    xs = sorted({x for rectangle in rectangles for x in (rectangle[0], rectangle[2])})
    area = 0.0
    for left, right in zip(xs, xs[1:]):
        intervals = sorted((r[1], r[3]) for r in rectangles if r[0] < right and r[2] > left)
        low = high = None
        length = 0.0
        for start, end in intervals:
            if high is None:
                low, high = start, end
            elif start <= high:
                high = max(high, end)
            else:
                length += high - low
                low, high = start, end
        if high is not None:
            length += high - low
        area += (right - left) * length
    return area


def validate(problem, result):
    """Return errors, never trusting solver status, quantities or claimed bounds."""
    data = normalize(problem)
    tolerance = min(EPS, min(min(u['dimensions']) for u in data['units']) * 1e-9)
    errors, checked = [], []
    expected = {u["unit_id"]: u for u in data["units"]}
    seen = set()
    placements = result.get("placements", []) if isinstance(result, dict) else None
    if not isinstance(placements, list):
        errors.append("placements must be an array")
        placements = []
    for placement in placements:
        if not isinstance(placement, dict):
            errors.append("Each placement must be an object")
            continue
        uid = placement.get("unit_id")
        if not isinstance(uid, str):
            errors.append("unit_id must be a string")
            continue
        is_pad = placement.get("kind") == "dunnage"
        if is_pad and not problem.get("allow_dunnage", False):
            errors.append(f"Dunnage is not authorized: {uid}")
            continue
        if placement.get("kind") not in (None, "product", "dunnage"):
            errors.append(f"Unknown placement kind: {uid}")
            continue
        if is_pad and problem.get("allow_dunnage", False):
            if uid in expected or not isinstance(uid, str) or not uid.startswith("__support__"):
                errors.append(f"Invalid support identity: {uid}")
                continue
            try:
                pad_size = vector(placement["dimensions_mm"], "support dimensions", True)
            except (KeyError, TypeError, ValueError) as error:
                errors.append(f"Malformed support: {error}")
                continue
            unit = {"item_id": uid, "orientations": [((0, 1, 2), pad_size)]}
        elif uid in expected:
            unit = expected[uid]
        else:
            errors.append(f"Unknown unit: {uid}")
            continue
        if uid in seen:
            errors.append(f"Duplicate unit: {uid}")
        seen.add(uid)
        try:
            pos = vector(placement["position_mm"], "position_mm")
            size = vector(placement["dimensions_mm"], "dimensions_mm", True)
            rotation = tuple(placement["rotation"])
            if len(rotation) != 3 or any(type(axis) is not int for axis in rotation):
                raise ValueError("rotation must contain three integer axes")
        except (KeyError, TypeError, ValueError) as error:
            errors.append(f"Malformed placement {uid}: {error}")
            continue
        if placement.get("item_id") != unit["item_id"]:
            errors.append(f"Wrong item ID: {uid}")
        if any(not math.isfinite(p + d) or p + d <= p for p, d in zip(pos, size)):
            errors.append(f"Unrepresentable numeric extent: {uid}")
        if (rotation, size) not in unit["orientations"]:
            errors.append(f"Forbidden orientation or changed dimensions: {uid}")
        if any(p < margin - tolerance or p + d > bound + tolerance
               for p, d, bound, margin in zip(pos, size, data["upper"], data["protection"])):
            errors.append(f"Outside usable cavity: {uid}")
        for other_id, other_pos, other_size in checked:
            if all(_overlap(pos[k], size[k], other_pos[k], other_size[k]) for k in range(3)):
                errors.append(f"Collision: {uid}, {other_id}")
            elif not is_pad and not other_id.startswith("__support__") and _overlap(pos[2], size[2], other_pos[2], other_size[2]):
                if not any(pos[k] + size[k] + data["gap"] <= other_pos[k] + tolerance or
                           other_pos[k] + other_size[k] + data["gap"] <= pos[k] + tolerance
                           for k in (0, 1)):
                    errors.append(f"Lateral clearance violated: {uid}, {other_id}")
            if all(_overlap(pos[k], size[k], other_pos[k], other_size[k]) for k in (0, 1)):
                if other_pos[2] + other_size[2] > pos[2] + tolerance:
                    errors.append(f"Top insertion blocked: {uid} by {other_id}")
        if abs(pos[2] - data["protection"][2]) > tolerance:
            rectangles = []
            for _, other_pos, other_size in checked:
                if abs(other_pos[2] + other_size[2] - pos[2]) <= tolerance:
                    left, bottom = max(pos[0], other_pos[0]), max(pos[1], other_pos[1])
                    right = min(pos[0] + size[0], other_pos[0] + other_size[0])
                    top = min(pos[1] + size[1], other_pos[1] + other_size[1])
                    if right > left and top > bottom:
                        rectangles.append((left, bottom, right, top))
            if _covered_area(rectangles) < size[0] * size[1] * (1 - 1e-10):
                errors.append(f"Incomplete base support: {uid}")
        checked.append((uid, pos, size))
    for uid in sorted(expected.keys() - seen):
        errors.append(f"Missing unit: {uid}")
    return {"valid": not errors, "errors": errors,
            "checks": ["quantities", "identity", "orientation", "bounds", "collisions",
                       "lateral_clearance", "full_base_support", "top_insertion"],
            "expected_units": len(expected), "placed_units": sum(uid in expected for uid, _, _ in checked),
            "support_pads": sum(uid not in expected for uid, _, _ in checked),
            "scope": "Rigid box geometry only; material strength, loads and transit performance are unverified"}
