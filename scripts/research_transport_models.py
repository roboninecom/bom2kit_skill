"""Research-only probes: synthetic SKU selection and nominal six-panel foam.

Not a packaging designer or a shipping certificate. OR-Tools is optional and is
only imported by the synthetic selection probe. No engine behavior is changed.
"""
import argparse
from itertools import combinations, product
import json
import math
from pathlib import Path


def panels(inner, t):
    x, y, z = inner
    if t <= 0 or min(inner) <= 2*t:
        raise ValueError("Invalid foam enclosure")
    # Full bottom/top, then Y walls, then shorter X walls: disjoint interiors.
    return [
        {"id": "bottom", "origin": [0, 0, 0], "size": [x, y, t]},
        {"id": "top", "origin": [0, 0, z-t], "size": [x, y, t]},
        {"id": "front", "origin": [0, 0, t], "size": [x, t, z-2*t]},
        {"id": "back", "origin": [0, y-t, t], "size": [x, t, z-2*t]},
        {"id": "left", "origin": [0, t, t], "size": [t, y-2*t, z-2*t]},
        {"id": "right", "origin": [x-t, t, t], "size": [t, y-2*t, z-2*t]},
    ]


def check_panels(inner, t, pieces):
    """Exact axis-aligned nominal checks, allowing intended face contact."""
    for p in pieces:
        if any(s <= 0 or o < 0 or o+s > bound+1e-8
               for o, s, bound in zip(p["origin"], p["size"], inner)):
            return False
        # Each piece must stay outside the protected central cavity.
        if all(min(o+s, bound-t)-max(o, t) > 1e-8
               for o, s, bound in zip(p["origin"], p["size"], inner)):
            return False
    for a, b in combinations(pieces, 2):
        if all(min(a["origin"][k]+a["size"][k], b["origin"][k]+b["size"][k])
               - max(a["origin"][k], b["origin"][k]) > 1e-8 for k in range(3)):
            return False
    shell_volume = math.prod(inner)-math.prod(v-2*t for v in inner)
    return math.isclose(sum(math.prod(p["size"]) for p in pieces), shell_volume,
                        rel_tol=1e-12, abs_tol=1e-8)


def synthetic_selection():
    from ortools.sat.python import cp_model
    patterns = []
    # Each atom represents a synthetic complete family, not real 101/102 CAD.
    for kit in ("A", "B"):
        for family in ("printed", "metal"):
            for shared in (False, True):
                patterns.append({"kit": kit, "members": [kit+":"+family],
                                 "families": [family],
                                 "sku": family if shared else kit+":"+family,
                                 "cost": 120 if shared else 100})
        patterns.append({"kit": kit, "members": [kit+":printed", kit+":metal"],
                         "families": ["printed", "metal"], "sku": "unsafe-mixed", "cost": 1})
    approved = [p for p in patterns if len(p["families"]) == 1]
    atoms = sorted({a for p in approved for a in p["members"]})
    skus = sorted({p["sku"] for p in approved})

    def solve(setup, cap):
        model = cp_model.CpModel()
        x = [model.new_bool_var(f"pattern_{i}") for i in range(len(approved))]
        y = {s: model.new_bool_var("sku_"+s) for s in skus}
        for atom in atoms:
            model.add(sum(x[i] for i, p in enumerate(approved) if atom in p["members"]) == 1)
        for sku in skus:
            relevant = [x[i] for i, p in enumerate(approved) if p["sku"] == sku]
            for selected in relevant:
                model.add(selected <= y[sku])
            model.add(y[sku] <= sum(relevant))
        model.add(sum(y.values()) <= cap)
        model.minimize(sum(p["cost"]*x[i] for i, p in enumerate(approved)) + setup*sum(y.values()))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 3
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return {"status": solver.status_name(status)}
        selected = [p for i, p in enumerate(approved) if solver.value(x[i])]
        objective = int(solver.objective_value)
        # Independent exhaustive check of this tiny finite pattern pool.
        costs = []
        for mask in product((0, 1), repeat=len(approved)):
            subset = [p for p, chosen in zip(approved, mask) if chosen]
            used = {p["sku"] for p in subset}
            if len(used) <= cap and all(sum(a in p["members"] for p in subset) == 1 for a in atoms):
                costs.append(sum(p["cost"] for p in subset)+setup*len(used))
        assert objective == min(costs)
        return {"status": solver.status_name(status), "objective_synthetic_units": objective,
                "box_count": len(selected), "sku_count": len({p["sku"] for p in selected}),
                "selected": selected, "exhaustive_check": True}

    result = {"scope": "Synthetic algebra only; no CAD, freight or real supplier cost",
              "purchase_only": solve(0, 6), "with_sku_setup": solve(200, 6),
              "one_sku_cap": solve(200, 1), "forbidden_patterns_filtered": len(patterns)-len(approved)}
    assert result["purchase_only"]["sku_count"] == 4
    assert result["with_sku_setup"]["sku_count"] == 2
    assert result["one_sku_cap"]["status"] == "INFEASIBLE"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"selection_probe": synthetic_selection(), "nominal_foam_probes": []}
    for path in args.result:
        result = json.loads(path.read_bytes())
        carton = result.get("envelope_candidate", result)["envelope_design"]["candidate"]
        container = carton["input"]["container"]
        inner, thickness = container["inner_mm"], container["protection_mm"]
        if len(set(thickness)) != 1:
            raise ValueError("This research probe only supports equal face thicknesses")
        pieces = panels(inner, thickness[0])
        assert check_panels(inner, thickness[0], pieces)
        assert not check_panels(inner, thickness[0], pieces[:-1])
        for layer in carton["layout"]["layers"]:
            for o, s, p, bound in zip(layer["position_mm"], layer["inner_mm"], thickness, inner):
                assert o >= p and o+s+2*layer["wall_mm"] <= bound-p+1e-8
        report["nominal_foam_probes"].append({
            "result": str(path.resolve()), "panels": pieces,
            "nominal_shell_complete": True, "missing_panel_rejected": True,
            "existing_cartons_fit_central_cavity": True,
            "outer_dimensions_unchanged": carton["external_mm"],
            "scope": "Nominal geometry only; no material, compression or tolerance qualification"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps({"selection": {k: {a: b for a, b in v.items() if a != "selected"}
                                  if isinstance(v, dict) else v
                                  for k, v in report["selection_probe"].items()},
                      "foam_cases": len(report["nominal_foam_probes"])}))


if __name__ == "__main__":
    main()
