"""Reporting must independently verify claims and escape untrusted labels."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from bom2kit.report import comparison, fingerprint, render_report
from bom2kit.solver import solve


def problem():
    return {"container": {"inner_mm": [20, 10, 10], "wall_mm": 2},
            "reference": {"external_mm": [24, 14, 14]},
            "items": [{"id": "A", "quantity": 2, "dimensions_mm": [10, 10, 10]}]}


class ReportTests(unittest.TestCase):
    def test_nominal_equality_is_never_full_kit_acceptance(self):
        data = problem()
        result = comparison(data, solve(data))
        self.assertTrue(result["no_worse_nominal_carton_volume"])
        self.assertFalse(result["full_kit_acceptance"])

    def test_metrics_do_not_trust_layout_claims(self):
        data = problem()
        layout = solve(data)
        layout["external_volume_l"] = 0
        layout["external_mm"] = [1, 1, 1]
        layout["container"] = {"inner_mm": [1, 1, 1]}
        self.assertAlmostEqual(comparison(data, layout)["external_volume_l"], 24 * 14 * 14 / 1e6)

    def test_forged_validation_cannot_hide_missing_unit(self):
        data = problem()
        layout = solve(data)
        layout["placements"].pop()
        layout["validation"] = {"valid": True, "errors": []}
        with tempfile.TemporaryDirectory() as directory:
            path = render_report(data, layout, {"valid": True}, directory)
            html = path.read_text(encoding="utf-8")
            result = json.loads((Path(directory) / "comparison.json").read_text())
        self.assertIn("INVALID LAYOUT", html)
        self.assertFalse(result["geometry_valid"])
        self.assertFalse(result["no_worse_nominal_carton_volume"])
        self.assertNotIn('<polygon', html)

    def test_html_labels_are_escaped(self):
        data = problem()
        payload = '<script>alert("x")</script>'
        data["name"] = payload
        data["items"][0]["id"] = payload
        data["items"][0]["contents"] = {payload: 1}
        data["sources"] = [payload]
        data["limitations"] = [payload]
        with tempfile.TemporaryDirectory() as directory:
            path = render_report(data, solve(data), {}, directory)
            html = path.read_text(encoding="utf-8")
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_canonical_source_fingerprint(self):
        first = {"source": "drawing", "dimensions": [20, 10, 10]}
        second = {"dimensions": [20, 10, 10], "source": "drawing"}
        self.assertEqual(fingerprint(first), fingerprint(second))
        changed = copy.deepcopy(first)
        changed["dimensions"][0] += 1
        self.assertNotEqual(fingerprint(first), fingerprint(changed))

    def test_malformed_certificate_report_has_no_instructions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = render_report(problem(), {"placements": [None]}, {"valid": True}, directory)
            self.assertIn("INVALID LAYOUT", path.read_text())

    def test_invalid_reference_dimensions_rejected(self):
        data = problem()
        layout = solve(data)
        for dimensions in ([0, 1, 1], [float("nan"), 1, 1], [1, 1]):
            data["reference"]["external_mm"] = dimensions
            with self.assertRaises(ValueError):
                comparison(data, layout)

    def test_reference_geometry_is_not_rendered_in_wrong_container(self):
        data = problem()
        layout = solve(data)
        data["reference_layout"] = copy.deepcopy(layout)
        data["reference_layout"]["placements"][0]["position_mm"][0] = 100
        with tempfile.TemporaryDirectory() as directory:
            path = render_report(data, layout, {}, directory)
            html = path.read_text()
        self.assertIn('Reference reconstruction is not valid', html)
        self.assertNotIn('<h3>Alan reference reconstruction</h3>', html)


if __name__ == "__main__":
    unittest.main()
