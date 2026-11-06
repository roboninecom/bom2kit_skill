"""Input normalization for rigid, axis-aligned packaged groups (millimetres)."""

import math


def number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} exceeds numeric range") from error
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return result


def vector(value, name, positive=False):
    if isinstance(value, (int, float)):
        value = [value] * 3
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} must contain three numbers")
    return tuple(number(v, name, positive) for v in value)


def normalize(problem):
    if not isinstance(problem, dict):
        raise ValueError("Problem must be an object")
    if problem.get("units", "mm") != "mm":
        raise ValueError("Only mm units are supported")
    container = problem.get("container")
    if not isinstance(container, dict):
        raise ValueError("container must be an object")
    inner = vector(container.get("inner_mm"), "inner_mm", True)
    protection = vector(container.get("protection_mm", 0), "protection_mm")
    wall = vector(container.get("wall_mm", 0), "wall_mm")
    external = tuple(a + 2 * b for a, b in zip(inner, wall))
    if not math.isfinite(math.prod(external)) or math.prod(inner) == 0:
        raise ValueError("Container dimensions exceed supported numeric volume range")
    reserved_top = number(container.get("reserved_top_mm", 0), "reserved_top_mm")
    gap = number(problem.get("gap_mm", 0), "gap_mm")
    if any(2 * p >= size for p, size in zip(protection, inner)):
        raise ValueError("Protection consumes the container")
    upper = tuple(size - p - (reserved_top if k == 2 else 0) for k, (size, p) in enumerate(zip(inner, protection)))
    if upper[2] <= protection[2]:
        raise ValueError("Top reservation consumes the usable height")
    if not isinstance(problem.get("allow_dunnage", False), bool):
        raise ValueError("allow_dunnage must be boolean")
    if not isinstance(problem.get("items"), list):
        raise ValueError("items must be an array")
    units, ids = [], set()
    for item in problem["items"]:
        if not isinstance(item, dict):
            raise ValueError("Each item must be an object")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id or item_id in ids or item_id.startswith("__support__"):
            raise ValueError("Item IDs must be nonempty unique strings")
        ids.add(item_id)
        quantity = item.get("quantity", 1)
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError(f"Invalid quantity for {item_id}")
        dimensions = vector(item.get("dimensions_mm"), item_id, True)
        if not math.isfinite(math.prod(dimensions)) or math.prod(dimensions) == 0:
            raise ValueError(f"Item dimensions exceed supported numeric volume range: {item_id}")
        rotations = item.get("allowed_rotations", "upright")
        if rotations == "upright":
            rotations = [(0, 1, 2), (1, 0, 2)]
        elif rotations == "fixed":
            rotations = [(0, 1, 2)]
        if not isinstance(rotations, (list, tuple)) or not rotations:
            raise ValueError(f"Invalid allowed_rotations for {item_id}")
        orientations = []
        for rotation in rotations:
            if (not isinstance(rotation, (list, tuple)) or len(rotation) != 3 or
                    any(type(axis) is not int for axis in rotation) or sorted(rotation) != [0, 1, 2]):
                raise ValueError(f"Invalid rotation for {item_id}")
            size = tuple(dimensions[i] for i in rotation)
            if (tuple(rotation), size) not in orientations:
                orientations.append((tuple(rotation), size))
        for index in range(quantity):
            units.append({"item_id": item_id, "unit_id": f"{item_id}#{index + 1}",
                          "orientations": orientations, "dimensions": dimensions})
    if not units:
        raise ValueError("BOM is empty")
    return {"inner": inner, "protection": protection, "wall": wall, "gap": gap,
            "upper": upper, "reserved_top": reserved_top,
            "units": units, "external": external}
