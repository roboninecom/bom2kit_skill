"""Geometric regression and deliberately invalid packing certificates."""

import copy
from itertools import permutations
import unittest

from bom2kit.solver import solve
from bom2kit.validation import validate


def benchmark(variant=101):
    sizes = [[246, 104, 75], [180, 164, 75], [246, 75, 52], [164, 75, 66],
             [246, 124, 64], [196, 168, 64], [196, 78, 64]]
    if variant == 102:
        sizes[0], sizes[1], sizes[3] = [246, 116, 75], [204, 164, 75], [164, 75, 42]
    return {"units": "mm", "container": {"inner_mm": [320 if variant == 101 else 332, 246, 140], "wall_mm": 22},
            "items": [{"id": f"BOX{i + 1}", "quantity": 1, "dimensions_mm": size,
                       "allowed_rotations": list(permutations(range(3)))} for i, size in enumerate(sizes)]}


def placement(item_id, pos, size, number=1):
    return {"unit_id": f"{item_id}#{number}", "item_id": item_id, "position_mm": pos,
            "dimensions_mm": size, "rotation": [0, 1, 2]}


class PackingTests(unittest.TestCase):
    def test_engineer_size_regressions(self):
        for variant, volume in ((101, 19.42304), (102, 20.06336)):
            with self.subTest(variant=variant):
                problem = benchmark(variant)
                result = solve(problem)
                self.assertEqual(result["status"], "feasible")
                self.assertTrue(validate(problem, result)["valid"])
                self.assertEqual(len(result["placements"]), 7)
                self.assertAlmostEqual(result["external_volume_l"], volume)
                self.assertEqual(result["validation"]["support_pads"], 0)

    def test_deterministic_geometry(self):
        problem = benchmark()
        self.assertEqual(solve(problem)["placements"], solve(problem)["placements"])

    def test_dropped_unit_rejected(self):
        problem = benchmark()
        result = solve(problem)
        result["placements"].pop()
        self.assertFalse(validate(problem, result)["valid"])

    def test_duplicate_unit_rejected(self):
        problem = benchmark()
        result = solve(problem)
        result["placements"][-1] = copy.deepcopy(result["placements"][0])
        self.assertFalse(validate(problem, result)["valid"])

    def test_collision_rejected(self):
        problem = benchmark()
        result = solve(problem)
        result["placements"][1]["position_mm"] = result["placements"][0]["position_mm"][:]
        self.assertTrue(any("Collision" in e for e in validate(problem, result)["errors"]))

    def test_changed_size_rejected(self):
        problem = benchmark()
        result = solve(problem)
        result["placements"][0]["dimensions_mm"][0] -= 1
        self.assertFalse(validate(problem, result)["valid"])

    def test_out_of_bounds_rejected(self):
        problem = benchmark()
        result = solve(problem)
        result["placements"][0]["position_mm"][0] = 500
        self.assertFalse(validate(problem, result)["valid"])

    def test_floating_and_insertion_order_rejected(self):
        problem = {"container": {"inner_mm": [10, 10, 20]},
                   "items": [{"id": "A", "quantity": 2, "dimensions_mm": [10, 10, 10]}]}
        floor = placement("A", [0, 0, 0], [10, 10, 10])
        upper = placement("A", [0, 0, 10], [10, 10, 10], 2)
        self.assertTrue(validate(problem, {"placements": [floor, upper]})["valid"])
        errors = validate(problem, {"placements": [upper, floor]})["errors"]
        self.assertTrue(any("support" in e for e in errors))
        self.assertTrue(any("insertion" in e for e in errors))

    def test_partial_base_support_rejected(self):
        problem = {"container": {"inner_mm": [10, 10, 20]}, "items": [
            {"id": "A", "dimensions_mm": [5, 10, 10]}, {"id": "B", "dimensions_mm": [10, 10, 10]}]}
        result = {"placements": [placement("A", [0, 0, 0], [5, 10, 10]), placement("B", [0, 0, 10], [10, 10, 10])]}
        self.assertFalse(validate(problem, result)["valid"])

    def test_clearance_rejected(self):
        problem = benchmark()
        result = solve(problem)
        problem["gap_mm"] = 1
        self.assertFalse(validate(problem, result)["valid"])

    def test_protection_and_quantity(self):
        problem = {"container": {"inner_mm": [22, 12, 12], "protection_mm": 1},
                   "items": [{"id": "A", "quantity": 2, "dimensions_mm": [10, 10, 10]}]}
        result = solve(problem)
        self.assertEqual(result["status"], "feasible")
        self.assertTrue(validate(problem, result)["valid"])

    def test_bound_is_proven_infeasible(self):
        problem = benchmark()
        problem["container"]["inner_mm"] = [100, 100, 100]
        self.assertEqual(solve(problem)["status"], "infeasible")

    def test_budget_exhaustion_is_not_infeasibility(self):
        result = solve(benchmark(), max_nodes=1)
        self.assertEqual(result["status"], "search_exhausted")
        self.assertEqual(result["placements"], [])

    def test_invalid_input(self):
        for quantity in (0, -1, 1.5, True):
            problem = benchmark()
            problem["items"][0]["quantity"] = quantity
            with self.assertRaises(ValueError):
                solve(problem)
        problem = benchmark()
        problem["items"][0]["dimensions_mm"][0] = float("nan")
        with self.assertRaises(ValueError):
            solve(problem)

    def test_malformed_budget_and_rotations(self):
        for value in (float("nan"), float("inf"), -1, 0, True, "5", None):
            with self.subTest(time_limit=value), self.assertRaises(ValueError):
                solve(benchmark(), time_limit=value)
        for value in (True, 1.5, "2", float("nan")):
            with self.subTest(max_nodes=value), self.assertRaises(ValueError):
                solve(benchmark(), max_nodes=value)
        for rotation in ([0, 1, 1], [False, 1, 2], [0.0, 1, 2], ["0", 1, 2], [0, 1]):
            problem = benchmark()
            problem["items"][0]["allowed_rotations"] = [rotation]
            with self.subTest(rotation=rotation), self.assertRaises(ValueError):
                solve(problem)

    def test_malformed_certificates_fail_closed(self):
        for result in (None, [], {"placements": None}, {"placements": [None]},
                       {"placements": [{"unit_id": []}]}):
            with self.subTest(result=result):
                self.assertFalse(validate(benchmark(), result)["valid"])

    def test_dunnage_spoof_cannot_bypass_clearance(self):
        problem = benchmark()
        result = solve(problem)
        problem["gap_mm"] = 1
        for entry in result["placements"]:
            entry["kind"] = "dunnage"
        self.assertFalse(validate(problem, result)["valid"])
        problem["allow_dunnage"] = True
        self.assertFalse(validate(problem, result)["valid"])

    def test_reserved_top_retains_external_dimensions(self):
        problem = benchmark()
        problem["container"]["reserved_top_mm"] = 1
        result = solve(problem)
        self.assertEqual(result["status"], "feasible")
        self.assertAlmostEqual(result["external_volume_l"], 19.42304)
        problem["container"]["reserved_top_mm"] = 2
        self.assertFalse(validate(problem, result)["valid"])
        problem["container"]["reserved_top_mm"] = 140
        with self.assertRaises(ValueError):
            solve(problem)

    def test_shared_support_uses_union_not_double_count(self):
        problem = {"container": {"inner_mm": [10, 10, 20]}, "items": [
            {"id": "A", "quantity": 2, "dimensions_mm": [5, 10, 10]},
            {"id": "B", "dimensions_mm": [10, 10, 10]}]}
        result = {"placements": [placement("A", [0, 0, 0], [5, 10, 10]),
                                 placement("A", [0, 0, 0], [5, 10, 10], 2),
                                 placement("B", [0, 0, 10], [10, 10, 10])]}
        errors = validate(problem, result)["errors"]
        self.assertTrue(any("Collision" in error for error in errors))
        self.assertTrue(any("support" in error for error in errors))
        result["placements"][1]["position_mm"][0] = 5
        self.assertTrue(validate(problem, result)["valid"])

    def test_tiny_positive_boxes_cannot_evade_collision_or_support(self):
        problem = {"container": {"inner_mm": [1, 1, 1]}, "items": [
            {"id": "A", "quantity": 2, "dimensions_mm": [1e-9, 1e-9, 1e-9]}]}
        result = {"placements": [placement("A", [0, 0, 0], [1e-9] * 3),
                                 placement("A", [0, 0, 0], [1e-9] * 3, 2)]}
        self.assertTrue(any("Collision" in e for e in validate(problem, result)["errors"]))
        result["placements"][1]["position_mm"] = [0, 0, .5]
        self.assertTrue(any("support" in e for e in validate(problem, result)["errors"]))

    def test_numeric_overflow_and_underflow_are_rejected(self):
        for dimension in (1e308, 1e-300, 10 ** 1000):
            problem = benchmark()
            problem["container"]["inner_mm"] = [dimension] * 3
            with self.assertRaises(ValueError):
                solve(problem)


if __name__ == "__main__":
    unittest.main()
