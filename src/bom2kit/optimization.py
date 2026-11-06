"""Budgeted catalogue search with independently verified packing certificates."""

import copy
import math
import time

from .models import normalize, number, vector
from .solver import solve
from .validation import validate


def optimize(problem, time_limit=5):
    """Find the smallest verified candidate without exceeding reference volume.

    Candidates are explicit container dictionaries merged over the base container.
    The base is always included. Existing wall, protection and top reservation
    cannot be reduced. This searches a catalogue, not the continuous design space.
    """
    start = time.perf_counter()
    time_limit = number(time_limit, "time_limit", True)
    base = normalize(problem)
    reference = problem.get("reference", {})
    if not isinstance(reference, dict):
        raise ValueError("reference must be an object")
    reference_size = vector(reference.get("external_mm", base["external"]), "reference.external_mm", True)
    reference_volume = math.prod(reference_size) / 1e6
    candidates = problem.get("container_candidates", [])
    if not isinstance(candidates, list) or any(not isinstance(c, dict) for c in candidates):
        raise ValueError("container_candidates must be an array of container objects")
    attempts, eligible, seen = [], [], set()
    for index, candidate in enumerate([problem["container"], *candidates]):
        container = {**problem["container"], **candidate}
        candidate_problem = {**problem, "container": container}
        label = candidate.get("id", "base" if index == 0 else f"candidate-{index}")
        try:
            data = normalize(candidate_problem)
        except (ValueError, TypeError, KeyError) as error:
            attempts.append({"id": label, "status": "invalid_candidate", "reason": str(error)})
            continue
        key = (data["inner"], data["wall"], data["protection"], data["reserved_top"])
        if key in seen:
            continue
        seen.add(key)
        volume = math.prod(data["external"]) / 1e6
        if volume > reference_volume + 1e-9:
            attempts.append({"id": label, "status": "above_reference_volume", "external_volume_l": volume})
            continue
        if (any(a < b for a, b in zip(data["wall"], base["wall"])) or
                any(a < b for a, b in zip(data["protection"], base["protection"])) or
                data["reserved_top"] < base["reserved_top"]):
            attempts.append({"id": label, "status": "reduced_protection_rejected"})
            continue
        eligible.append((volume, index, label, candidate_problem))
    # Solve base first to preserve an incumbent, then seek smaller alternatives.
    eligible.sort(key=lambda entry: (entry[1] != 0, entry[0], entry[1]))
    best, best_id = None, None
    for order, (volume, _, label, candidate_problem) in enumerate(eligible):
        if best is not None and volume >= best["external_volume_l"] - 1e-9:
            attempts.append({"id": label, "status": "not_smaller_than_verified_incumbent", "external_volume_l": volume})
            continue
        remaining = time_limit - (time.perf_counter() - start)
        if remaining <= 0:
            attempts.append({"id": label, "status": "budget_exhausted"})
            continue
        # Reserve a fair share for remaining candidates; one hard instance must
        # not consume the complete catalogue budget.
        per_candidate = remaining / (len(eligible) - order)
        result = solve(candidate_problem, time_limit=per_candidate)
        certificate = validate(candidate_problem, result)
        attempts.append({"id": label, "status": result["status"], "external_volume_l": volume,
                         "validation_valid": certificate["valid"], "stats": result["stats"]})
        if result["status"] == "feasible" and certificate["valid"]:
            best, best_id = copy.deepcopy(result), label
            best["validation"] = certificate
    metadata = {"method": "explicit_container_catalogue", "selected_id": best_id,
                "reference_external_mm": list(reference_size), "reference_volume_l": reference_volume,
                "attempts": attempts, "elapsed_seconds": time.perf_counter() - start,
                "time_budget_seconds": time_limit, "global_optimum_proven": False,
                "scope": "Nominal geometric volume only; packaging cost and transport performance are not assessed"}
    if best is None:
        return {"status": "no_verified_candidate", "placements": [], "optimization": metadata}
    best["optimization"] = metadata
    best["optimization"]["volume_delta_l"] = best["external_volume_l"] - reference_volume
    best["optimization"]["not_worse_volume"] = best["external_volume_l"] <= reference_volume + 1e-9
    return best
