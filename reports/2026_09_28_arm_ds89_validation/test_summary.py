import importlib.util
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds89_summary", HERE / "summary.py")
summary = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(summary)


def candidate(margin=0.0):
    return {"epoch": 10, "acquired_cfo_hz": 1.0, "tracking_cfo_hz": 1.0,
            "exact_score": 1.0, "control_score": 0.0, "margin": margin}


def expected_candidate(margin=0.0):
    value = candidate(margin)
    value["epoch_sample"] = value.pop("epoch")
    return value


class RecordingCountsTest(unittest.TestCase):
    def test_uses_frozen_maximum_matcher_and_counts_new_positive_windows(self):
        audit_spec = importlib.util.spec_from_file_location(
            "audit", HERE.parent / "2026_09_28_arm_full_optimization" / "independent_summary.py"
        )
        audit = importlib.util.module_from_spec(audit_spec)
        assert audit_spec.loader is not None
        audit_spec.loader.exec_module(audit)
        context = {"dataset_id": "DS8", "session_id": "recording", "visit_index": 0,
                   "ordinal": 0, "rate_hz": 2500000}
        windows = {}
        native_windows = {}
        for receiver, probe in audit.WINDOW_KEYS:
            expected = [expected_candidate() for _ in range(8)]
            actual = [candidate() for _ in range(8)]
            if (receiver, probe) == (0, 0):
                expected[0] = expected_candidate(0.1)
                actual[0] = candidate(0.1)
            if (receiver, probe) == (1, 0):
                actual[0] = candidate(0.1)
            windows[(receiver, probe)] = {"candidates": expected}
            native_windows[(receiver, probe)] = {"candidates": actual}
        baseline = {("recording", 0): windows}
        native = {("recording", 0): native_windows}
        got = summary.recording_counts([context], baseline, native, audit)
        self.assertEqual(got[0]["original_hits"], 1)
        self.assertEqual(got[0]["recovered_hits"], 1)
        self.assertEqual(got[0]["original_negative_windows_now_positive"], 1)
        self.assertFalse(got[0]["below_90_percent_recovery"])


if __name__ == "__main__":
    unittest.main()
