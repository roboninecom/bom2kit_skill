"""Catalogue optimization must preserve protection and independent validity."""

import unittest

from bom2kit.optimization import optimize
from bom2kit.validation import validate


def problem():
    return {"container": {"inner_mm": [30, 10, 10], "wall_mm": 2},
            "items": [{"id": "A", "quantity": 2, "dimensions_mm": [10, 10, 10]}]}


class OptimizationTests(unittest.TestCase):
    def test_smaller_verified_candidate_selected(self):
        data = problem()
        data["container_candidates"] = [{"id": "compact", "inner_mm": [20, 10, 10]}]
        result = optimize(data)
        self.assertEqual(result["optimization"]["selected_id"], "compact")
        self.assertLess(result["optimization"]["volume_delta_l"], 0)
        self.assertTrue(validate({**data, "container": result["container"]}, result)["valid"])
        self.assertFalse(result["optimization"]["global_optimum_proven"])

    def test_no_improvement_preserves_incumbent(self):
        data = problem()
        data["container_candidates"] = [{"id": "too-small", "inner_mm": [10, 10, 10]}]
        result = optimize(data)
        self.assertEqual(result["optimization"]["selected_id"], "base")
        self.assertEqual(result["optimization"]["volume_delta_l"], 0)

    def test_no_candidate_exceeding_reference_can_win(self):
        data = problem()
        data["reference"] = {"external_mm": [10, 10, 10]}
        result = optimize(data)
        self.assertEqual(result["status"], "no_verified_candidate")
        self.assertEqual(result["placements"], [])

    def test_protection_reductions_rejected(self):
        data = problem()
        data["container_candidates"] = [{"id": "thin-wall", "wall_mm": 0}]
        result = optimize(data)
        self.assertEqual(result["optimization"]["selected_id"], "base")
        self.assertTrue(any(a["status"] == "reduced_protection_rejected" for a in result["optimization"]["attempts"]))

    def test_invalid_candidate_is_reported(self):
        data = problem()
        data["container_candidates"] = [{"id": "bad", "inner_mm": [0, 10, 10]}]
        result = optimize(data)
        self.assertTrue(result["validation"]["valid"])
        self.assertTrue(any(a["status"] == "invalid_candidate" for a in result["optimization"]["attempts"]))

    def test_budget_is_bounded_and_cannot_claim_success(self):
        result = optimize(problem(), time_limit=1e-12)
        self.assertEqual(result["status"], "no_verified_candidate")

    def test_invalid_budget_fails(self):
        for budget in (float("nan"), float("inf"), 0, True, "1"):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                optimize(problem(), time_limit=budget)


if __name__ == "__main__":
    unittest.main()
