import unittest

from audit import audit


class TimingTests(unittest.TestCase):
    def test_bracket_and_mismatch(self):
        t = dict(
            begin_before_realtime_ns=1100,
            begin_before_monotonic_ns=100,
            begin_after_realtime_ns=1300,
            begin_after_monotonic_ns=300,
            terminal_realtime_ns=2010,
            terminal_monotonic_ns=1000,
            first_sample_earliest_utc_ns=1100,
            first_sample_estimate_utc_ns=1205,
            first_sample_latest_utc_ns=1310,
            first_sample_bracket_width_ns=210,
            maximum_realtime_monotonic_offset_spread_ns=10,
            qualification_limit_ns=300,
            qualified=True,
            session_start_device_sample_counter=100,
            sample_rate_hz=10,
        )
        r = dict(
            timing=t,
            observation_start_utc_ns=1205,
            fitted_tau_s=1.0,
            terminal=dict(first_counter=100, final_counter=3100),
        )
        value = audit(r)
        self.assertAlmostEqual(value["outside_distance_s"], 1 - 105e-9)
        self.assertEqual(value["counter_duration_s"], 300)
        t["first_sample_estimate_utc_ns"] += 1
        with self.assertRaises(AssertionError):
            audit(r)

    def test_missing_is_explicit(self):
        self.assertEqual(audit(dict(timing=None)), dict(status="missing"))


if __name__ == "__main__":
    unittest.main()
