import copy
import unittest

from bom2kit.bom import reconcile_bom


class BomTests(unittest.TestCase):
    def test_packet_multiplication_and_direct_sku(self):
        bom = {"components": [{"id": "servo-C018", "quantity": 6},
                              {"id": "screw", "quantity": 20}]}
        problem = {"items": [{"id": "servo-C018", "quantity": 6},
                             {"id": "hardware-bag", "quantity": 2,
                              "contents": {"screw": 10}}]}
        before = copy.deepcopy((bom, problem))
        result = reconcile_bom(bom, problem)
        self.assertTrue(result["complete"])
        self.assertFalse(result["geometry_validated"])
        self.assertEqual(result["declared"], {"screw": 20, "servo-C018": 6})
        self.assertEqual((bom, problem), before)

    def test_variant_and_case_substitution_fails(self):
        result = reconcile_bom(
            {"components": [{"id": "C018", "quantity": 6}]},
            {"items": [{"id": "c018", "quantity": 3}, {"id": "C049", "quantity": 3}]})
        self.assertEqual(result["missing"], {"C018": 6})
        self.assertEqual(result["extra"], {"C049": 3, "c018": 3})
        self.assertFalse(result["complete"])

    def test_opaque_box_is_not_inferred_as_its_contents(self):
        result = reconcile_bom({"components": [{"id": "servo", "quantity": 12}]},
                               {"items": [{"id": "BOX5", "quantity": 1}]})
        self.assertEqual(result["missing"], {"servo": 12})
        self.assertEqual(result["extra"], {"BOX5": 1})

    def test_revisions_require_explicit_matching_declaration(self):
        bom = {"components": [{"id": "part", "quantity": 2, "revision": "R3"}]}
        problem = {"items": [{"id": "bag", "quantity": 2, "contents": {"part": 1}}]}
        self.assertFalse(reconcile_bom(bom, problem)["complete"])
        problem["items"][0]["contents_revisions"] = {"part": "R3"}
        self.assertTrue(reconcile_bom(bom, problem)["complete"])
        self.assertTrue(reconcile_bom(bom, {"items": [
            {"id": "part", "quantity": 2, "revision": "R3"}]})["complete"])

    def test_invalid_quantities_and_duplicate_ids(self):
        good_bom = {"components": [{"id": "x", "quantity": 1}]}
        for count in [True, False, 0, -1, 1.0, "1", None]:
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    reconcile_bom(good_bom, {"items": [{"id": "x", "quantity": count}]})
                with self.assertRaises(ValueError):
                    reconcile_bom(good_bom, {"items": [{"id": "bag", "quantity": 1,
                                                       "contents": {"x": count}}]})
                with self.assertRaises(ValueError):
                    reconcile_bom({"components": [{"id": "x", "quantity": count}]},
                                  {"items": [{"id": "x", "quantity": 1}]})
        row = {"id": "x", "quantity": 1}
        with self.assertRaises(ValueError):
            reconcile_bom({"components": [row, row]}, {"items": [row]})
        with self.assertRaises(ValueError):
            reconcile_bom(good_bom, {"items": [row, row]})

    def test_malformed_mappings(self):
        bom = {"components": [{"id": "x", "quantity": 1}]}
        for mapping in [{}, [], {1: 2}, {"": 2}]:
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                reconcile_bom(bom, {"items": [{"id": "bag", "quantity": 1,
                                              "contents": mapping}]})

    def test_output_stable_under_input_reordering(self):
        bom = {"components": [{"id": "z", "quantity": 1}, {"id": "a", "quantity": 2}]}
        problem = {"items": [{"id": "z", "quantity": 1}, {"id": "a", "quantity": 2}]}
        self.assertEqual(reconcile_bom(bom, problem), reconcile_bom(
            {"components": bom["components"][::-1]}, {"items": problem["items"][::-1]}))


if __name__ == "__main__":
    unittest.main()
