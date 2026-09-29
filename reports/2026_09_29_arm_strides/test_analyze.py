import io
import json
import unittest

from analyze import matches, original_inventories, projection


def hit(epoch, cfo=0.0):
    return {"epoch_sample": epoch, "refined_epoch": epoch,
            "tracking_cfo_hz": cfo, "margin": 0.5}


class AnalyzerTests(unittest.TestCase):
    def test_baseline_uses_authoritative_probe_start_not_ordinal(self):
        row = {"method": "original", "repeat": 0, "status": "ok",
               "context": {"session_id": "s", "visit_index": 3},
               "result": {"probes": [{"receiver_id": 1, "probe_index": 9,
                                        "probe_start_ms": 20, "candidates": []}]}}
        inventory = original_inventories(io.StringIO(json.dumps(row) + "\n"))
        self.assertIn((1, 20), inventory[("s", 3)])
        self.assertNotIn((1, 90), inventory[("s", 3)])

    def test_matching_is_maximum_cardinality_not_greedy(self):
        # The first reference can take either actual; the second can take only
        # actual zero. An augmenting path is required to recover both.
        reference = [hit(0), hit(-2)]
        actual = [hit(0), hit(2)]
        self.assertEqual(matches(reference, actual), 2)

    def test_matching_never_reuses_one_actual_candidate(self):
        self.assertEqual(matches([hit(0), hit(0)], [hit(0)]), 1)

    def test_public_projection_drops_overlapping_probe_only(self):
        context = {
            "rate_hz": 2500000, "session_id": "projection-fixture",
            "visit_index": 7, "sample_start_counter": 9000000000000001,
            "manifest_sha256": "sha256:" + "1" * 64,
            "ci16_sha256": "2" * 64, "actual_if_offset_hz": 0,
            "target": {"channel": 1, "edge": "upper", "rf_center_hz": 11200000000},
        }
        candidate = {"refined_epoch": 1000, "tracking_cfo_hz": 1200.0,
                     "exact_score": 0.8, "control_score": 0.1, "margin": 0.7}
        output = {"rows": [
            {"receiver_id": 0, "probe_index": index, "probe_start_ms": start,
             "candidates": [candidate]}
            for index, start in enumerate((0, 10, 20))]}
        projected = projection({"context": context, "ci16_sha256": "2" * 64},
                               output, "sha256:" + "3" * 64)
        self.assertEqual(set(projected), {(0, 0), (0, 20)})
        self.assertEqual(sum(map(len, projected.values())), 2)
        for values in projected.values():
            self.assertNotIn("candidate_id", values[0])
            self.assertNotIn("source_group_id", values[0])
            self.assertNotIn("probe_index", values[0])

    def test_projection_preserves_selected_empty_observation_group(self):
        context = {
            "rate_hz": 2500000, "session_id": "empty-projection-fixture",
            "visit_index": 8, "sample_start_counter": 9000000000000001,
            "manifest_sha256": "sha256:" + "4" * 64,
            "actual_if_offset_hz": 0,
            "target": {"channel": 1, "edge": "upper", "rf_center_hz": 11200000000},
        }
        output = {"rows": [{"receiver_id": 0, "probe_index": 0,
                            "probe_start_ms": 0, "candidates": []}]}
        projected = projection({"context": context, "ci16_sha256": "5" * 64},
                               output, "sha256:" + "6" * 64)
        self.assertEqual(projected, {(0, 0): []})


if __name__ == "__main__":
    unittest.main()
