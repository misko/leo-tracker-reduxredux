import unittest

from known_state_v2 import NativeKnownStateV2
from known_state_v3 import NativeKnownStateV3
from test_known_state import EPOCH, RATE, synthetic


PHYSICAL_CFO = 5_210.0
SCORED_CFO = 103_754.0


class KnownStateV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generate a clean pilot whose physical CFO differs greatly from the
        # acquisition/scoring center, matching the concrete reviewer geometry.
        import test_known_state

        old = test_known_state.CFO
        test_known_state.CFO = PHYSICAL_CFO
        cls.iq = synthetic()
        test_known_state.CFO = old
        cls.v2 = NativeKnownStateV2(RATE, "lower")
        cls.v3 = NativeKnownStateV3(RATE, "lower")

    @classmethod
    def tearDownClass(cls):
        cls.v2.close()
        cls.v3.close()

    def test_dual_cfo_accepts_large_residual_when_physical_innovation_is_small(self):
        result = self.v3.measure(
            self.iq,
            EPOCH,
            SCORED_CFO,
            expected_physical_cfo_hz=PHYSICAL_CFO,
        )
        self.assertGreater(abs(result["cfo_residual_from_scored_hz"]), 90_000)
        self.assertLess(abs(result["physical_cfo_innovation_hz"]), 500)
        self.assertTrue(result["cfo_innovation_within_8khz"])
        self.assertFalse(result["needs_reacquire"])

    def test_default_preserves_v2_reacquisition_semantics(self):
        v2 = self.v2.measure(self.iq, EPOCH, SCORED_CFO)
        v3 = self.v3.measure(self.iq, EPOCH, SCORED_CFO)
        self.assertEqual(v3["exact_score"], v2["exact_score"])
        self.assertEqual(v3["control_score"], v2["control_score"])
        self.assertEqual(v3["tracking_cfo_hz"], v2["tracking_cfo_hz"])
        self.assertEqual(v3["needs_reacquire"], v2["needs_reacquire"])

    def test_wrong_physical_expectation_still_reacquires(self):
        result = self.v3.measure(
            self.iq,
            EPOCH,
            SCORED_CFO,
            expected_physical_cfo_hz=PHYSICAL_CFO + 20_000,
        )
        self.assertGreater(abs(result["physical_cfo_innovation_hz"]), 8_000)
        self.assertTrue(result["needs_reacquire"])

    def test_physical_cfo_may_cross_scoring_bound(self):
        import test_known_state

        old = test_known_state.CFO
        test_known_state.CFO = 401_000.0
        try:
            iq = synthetic()
        finally:
            test_known_state.CFO = old
        result = self.v3.measure(
            iq,
            EPOCH,
            390_000.0,
            expected_physical_cfo_hz=401_000.0,
        )
        self.assertAlmostEqual(result["tracking_cfo_hz"], 401_097.30113636365)
        self.assertLess(abs(result["physical_cfo_innovation_hz"]), 500)
        self.assertFalse(result["needs_reacquire"])

    def test_expected_residual_must_fit_glrt_support(self):
        with self.assertRaises(ValueError):
            self.v3.measure(
                self.iq,
                EPOCH,
                390_000.0,
                expected_physical_cfo_hz=504_000.0,
            )


if __name__ == "__main__":
    unittest.main()
