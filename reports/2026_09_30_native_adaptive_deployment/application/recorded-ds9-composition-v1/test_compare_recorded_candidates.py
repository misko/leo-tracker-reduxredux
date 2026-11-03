import copy
import csv
import io
import unittest

from compare_recorded_candidates import compare, event_candidates, indexed_candidates


def example():
    return {(301, 0, 0, 0): {
        "rank": 0, "integer_epoch": 2743, "fractional_status": "complete",
        "acquired_cfo_hz": -547892.5, "integer_tracking_cfo_hz": -547892.5,
        "integer_exact_score": 0.48, "integer_control_score": 0.04,
        "integer_margin": 0.44, "fractional_offset": -0.66,
        "tracking_cfo_hz": -547892.5, "exact_score": 0.51,
        "control_score": 0.038, "margin": 0.472,
    }}


class ComparisonTests(unittest.TestCase):
    def test_scanner_event_mapping_and_duplicates(self):
        row = {"kind": 5, "visit": 301, "receiver_id": 0, "probe_index": 0,
               "candidate_index": 0, "epoch": 2743, "fractional_epoch_status": 1,
               "detector_status": 0, "acquired_cfo_hz": -547892.5,
               "tracking_cfo_hz": -547892.5, "exact_score": 0.48,
               "control_score": 0.04, "margin": 0.44,
               "fractional_epoch_offset_samples": -0.66,
               "fractional_tracking_cfo_hz": -547892.5,
               "fractional_exact_score": 0.51, "fractional_control_score": 0.038,
               "fractional_margin": 0.472}

        def stream(rows):
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=row, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
            output.seek(0)
            return output

        self.assertEqual(event_candidates(stream([row])), example())
        with self.assertRaises(ValueError):
            event_candidates(stream([row, row]))
        row["fractional_epoch_status"] = 2
        row["fractional_exact_score"] = float("nan")
        parsed = event_candidates(stream([row]))
        self.assertIsNone(parsed[(301, 0, 0, 0)]["exact_score"])
        row["fractional_epoch_status"] = 1
        with self.assertRaises(ValueError):
            event_candidates(stream([row]))

    def test_reference_inventory_is_strict(self):
        candidate = next(iter(example().values()))
        rows = [dict(candidate, rank=i) for i in range(8)]
        receipt = {"visit": 301, "status": "pass", "native": {"0": rows, "1": rows}}
        self.assertEqual(len(indexed_candidates([receipt], "native")), 16)
        with self.assertRaises(ValueError):
            indexed_candidates([receipt, receipt], "native")
        receipt["status"] = "fail"
        with self.assertRaises(ValueError):
            indexed_candidates([receipt], "native")
        receipt["status"] = "pass"
        del receipt["native"]["1"]
        with self.assertRaises(ValueError):
            indexed_candidates([receipt], "native")

    def test_exact_and_finite_tolerance(self):
        expected = example()
        actual = copy.deepcopy(expected)
        actual[(301, 0, 0, 0)]["tracking_cfo_hz"] += 1e-8
        self.assertEqual(compare(actual, expected)["passing_candidates"], 1)

    def test_missing_or_extra_candidates_fail(self):
        expected = example()
        with self.assertRaises(ValueError):
            compare({}, expected)
        actual = copy.deepcopy(expected)
        actual[(302, 0, 0, 0)] = actual[(301, 0, 0, 0)]
        with self.assertRaises(ValueError):
            compare(actual, expected)

    def test_nonfinite_and_large_error_fail(self):
        for value in (float("nan"), float("inf"), -547890.0, True):
            actual = example()
            actual[(301, 0, 0, 0)]["tracking_cfo_hz"] = value
            with self.assertRaises(ValueError):
                compare(actual, example())

    def test_gate_difference_fails_even_within_scalar_tolerance(self):
        actual, expected = example(), example()
        actual[(301, 0, 0, 0)]["margin"] = 0.025 - 1e-12
        expected[(301, 0, 0, 0)]["margin"] = 0.025
        with self.assertRaises(ValueError):
            compare(actual, expected)

    def test_unavailable_values_and_structure(self):
        actual = example()
        row = actual[(301, 0, 0, 0)]
        row["fractional_status"] = "unbracketed"
        for name in ("fractional_offset", "tracking_cfo_hz", "exact_score",
                     "control_score", "margin"):
            row[name] = None
        self.assertEqual(compare(actual, copy.deepcopy(actual))[
            "unavailable_fractional_candidates"], 1)
        expected = copy.deepcopy(actual)
        row["exact_score"] = 0.0
        with self.assertRaises(ValueError):
            compare(actual, expected)
        row["exact_score"] = None
        row["integer_epoch"] += 1
        with self.assertRaises(ValueError):
            compare(actual, expected)


if __name__ == "__main__":
    unittest.main()
