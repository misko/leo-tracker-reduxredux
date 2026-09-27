import unittest

from run_cadence import CadenceSchedule, classify_reference, latency_rows, summarize
from tracking import Key


class CadenceTests(unittest.TestCase):
    def test_schedule_is_source_time_causal_and_key_isolated(self):
        schedule = CadenceSchedule(1.0)
        a = Key("s", 0, 1, "lower", 100)
        b = Key("s", 0, 2, "lower", 100)
        self.assertEqual(schedule.begin(a, 1_000), (True, "cold_blind"))
        self.assertEqual(schedule.begin(a, 1_099), (False, "not_due"))
        self.assertEqual(schedule.begin(b, 1_099), (True, "cold_blind"))
        self.assertEqual(schedule.begin(a, 1_100), (True, "scheduled_blind"))
        # A future timestamp cannot change decisions already emitted.
        prefix = CadenceSchedule(1.0)
        self.assertEqual(prefix.begin(a, 1_000), (True, "cold_blind"))
        self.assertEqual(prefix.begin(a, 1_099), (False, "not_due"))

    def test_failed_fast_is_unknown_not_loss_or_absence(self):
        self.assertEqual(classify_reference(True, False, "unknown"), "unknown")
        self.assertEqual(classify_reference(True, False, "blind"), "lost")
        self.assertEqual(classify_reference(True, True, "fast"), "covered")

    def test_unknown_visit_keeps_state_cost_and_no_stale_positive(self):
        row = {
            "action": "failed_fast_unknown", "result_kind": "unknown",
            "attempted_fast_check": True, "reference_positive": True,
            "reference_positive_outcome": "unknown", "candidate_positive": False,
            "baseline_times": [{"cpu_ms": 10.0, "wall_ms": 11.0}],
            "cost_components": {
                "blind": {"cpu_ms": 0.0, "wall_ms": 0.0},
                "check": {"cpu_ms": 0.2, "wall_ms": 0.3},
                "state": {"cpu_ms": 0.1, "wall_ms": 0.1},
            },
            "key_id": "k", "rate_hz": 100, "case_id": "c",
            "visit_index": 1, "start_counter": 100,
        }
        result = summarize([row])
        self.assertEqual(result["unknown_visits"], 1)
        self.assertEqual(result["candidate_positive_visits"], 0)
        self.assertAlmostEqual(result["costs"]["strategy_total"]["cpu_ms"], 0.3)

    def test_latency_reports_never_discovered_without_lookahead(self):
        rows = [
            {"key_id": "a", "reference_positive": True, "candidate_positive": False,
             "start_counter": 100, "visit_index": 1, "rate_hz": 100, "case_id": "a1"},
            {"key_id": "a", "reference_positive": True, "candidate_positive": True,
             "start_counter": 150, "visit_index": 2, "rate_hz": 100, "case_id": "a2"},
            {"key_id": "b", "reference_positive": True, "candidate_positive": False,
             "start_counter": 200, "visit_index": 1, "rate_hz": 100, "case_id": "b1"},
        ]
        latency = latency_rows(rows)
        self.assertEqual(latency[0]["lag_seconds"], 0.5)
        self.assertTrue(latency[1]["never_discovered"])


if __name__ == "__main__":
    unittest.main()
