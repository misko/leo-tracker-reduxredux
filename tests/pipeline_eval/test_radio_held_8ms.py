import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from radio_held_8ms import project, radio_routes, select


class RadioHeld8ms(unittest.TestCase):
    def test_signs_and_ties(self):
        self.assertEqual(radio_routes({0: 1e-10, 1: -1e-10}), {0: "history", 1: "unfiltered"})
        self.assertEqual(radio_routes({0: 0.0, 1: 1.0}), {0: "unfiltered", 1: "history"})
        self.assertEqual(radio_routes({0: -0.0, 1: -1.0}), {0: "unfiltered", 1: "unfiltered"})
        self.assertEqual(radio_routes({0: 1.0, 1: 2.0}), {0: "history", 1: "history"})
        with self.assertRaisesRegex(ValueError, "finite"):
            radio_routes({0: float("nan"), 1: 1.0})

    def test_mixed_projection_keeps_full_order_and_empty_lanes(self):
        measured = [
            {"receiver_id": radio, "visit_index": visit, "candidates": candidates}
            for visit, radio, candidates in ((0, 0, [5]), (0, 1, [6]), (1, 0, []), (1, 1, [7]))
        ]
        history = [dict(row, candidates=[]) for row in measured]
        rows = project(measured, history, {0: "history", 1: "unfiltered"})
        self.assertEqual(rows, [history[0], measured[1], measured[2], measured[3]])
        with self.assertRaisesRegex(ValueError, "introduced"):
            project(measured, [*history[:2], dict(history[2], candidates=[8]), history[3]],
                    {0: "history", 1: "unfiltered"})
        with self.assertRaisesRegex(ValueError, "changed"):
            project(measured, [dict(history[0], visit_index=2), *history[1:]],
                    {0: "history", 1: "unfiltered"})

    def test_same_sign_returns_original_recipe_and_packet(self):
        original = {"source": {"probes": [{"receiver_id": 0, "candidates": [1]}]}}
        recipe = {"original": True}
        witness = dict(choice={"log_score_gain_by_radio": {0: 0, 1: -1}, "route": "unfiltered"},
                       parent_native_sha256="parent-rows", parent_detector_sha256="parent-recipe",
                       native_sha256="global-rows", detector_recipe_sha256="global-recipe",
                       receiver_recipe=recipe, selector={})
        with patch("eight_ms_held_fit.select", return_value=(original, witness)), patch("anchor_holds.history_rows") as history:
            packet, evidence = select(original, {})
        history.assert_not_called()
        self.assertIs(packet, original)
        self.assertIs(evidence["receiver_recipe"], recipe)
        self.assertEqual(evidence["native_sha256"], "global-rows")
        self.assertEqual(evidence["detector_recipe_sha256"], "global-recipe")


if __name__ == "__main__":
    unittest.main()
