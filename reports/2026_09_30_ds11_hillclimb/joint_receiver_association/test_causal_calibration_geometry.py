import unittest
from causal_calibration_geometry import available


class AvailabilityTests(unittest.TestCase):
    def test_both_capture_and_finalization_must_precede_cutoff(self):
        self.assertTrue(available(dict(capture_end_utc_ns=8, finalized_utc_ns=9), 10))
        for end, final in ((10, 9), (8, 10), (11, 9), (8, 11)):
            self.assertFalse(available(dict(capture_end_utc_ns=end, finalized_utc_ns=final), 10))
