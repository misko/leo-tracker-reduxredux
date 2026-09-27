import hashlib
import math
import unittest

import numpy as np

from known_state import NativeKnownState


RATE = 2_500_000
EPOCH = 320
CFO = 65_000.0


def synthetic(kind="pilot", *, seed=9):
    rng = np.random.default_rng(seed)
    values = rng.normal(0, 8, (RATE // 50, 2))
    if kind == "tone":
        t = np.arange(len(values))
        tone = 8000 * np.exp(2j * np.pi * 130_000 * t / RATE)
        values += np.column_stack((tone.real, tone.imag))
    if kind == "pilot":
        from leo.analysis.starlink.templates import qin_edge_pilot_frame

        template = np.asarray(qin_edge_pilot_frame(RATE, "lower"))
        for frame in range(16):
            start = EPOCH + round(frame * RATE / 750)
            stop = min(start + len(template), len(values))
            if stop <= start:
                break
            k = np.arange(stop - start)
            signal = 1400 * template[: stop - start] * np.exp(2j * np.pi * CFO * k / RATE)
            values[start:stop] += np.column_stack((signal.real, signal.imag))
    return np.clip(np.rint(values), -32768, 32767).astype(np.int16)


class KnownStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = NativeKnownState(RATE, "lower")

    @classmethod
    def tearDownClass(cls):
        cls.native.close()

    def test_known_point_scores_pilot_and_preserves_input(self):
        iq = synthetic()
        before = hashlib.sha256(iq).digest()
        result = self.native.measure(iq, EPOCH, CFO)
        self.assertEqual(hashlib.sha256(iq).digest(), before)
        self.assertEqual(result["timing_semantics"], "predicted_verified")
        self.assertEqual(result["timing_bracket_status"], "not_searched")
        self.assertEqual(result["glrt_evaluations"], 1)
        self.assertGreater(result["support_frames"], 10)
        self.assertGreater(result["margin"], 0.025)
        self.assertTrue(result["cfo_innovation_within_8khz"])
        self.assertLess(abs(result["tracking_cfo_hz"] - CFO), 500)

    def test_local_recovery_refines_small_timing_error(self):
        result = self.native.measure(synthetic(), EPOCH + 0.35, CFO, recover_timing=True)
        self.assertEqual(result["timing_semantics"], "locally_refined")
        self.assertEqual(result["glrt_evaluations"], 4)
        self.assertFalse(result["needs_reacquisition"])
        self.assertLess(abs(result["epoch"] + result["fractional_offset_samples"] - EPOCH), 0.6)

    def test_large_timing_error_requires_reacquisition(self):
        result = self.native.measure(synthetic(), EPOCH + 20, CFO, recover_timing=True)
        self.assertTrue(result["needs_reacquisition"] or result["margin"] <= 0.025)

    def test_wrong_cfo_is_not_trusted(self):
        result = self.native.measure(synthetic(), EPOCH, CFO + 40_000)
        self.assertFalse(result["cfo_innovation_within_8khz"])
        self.assertTrue(result["needs_reacquisition"])

    def test_noise_and_tone_do_not_pass_margin(self):
        for kind in ("noise", "tone"):
            with self.subTest(kind=kind):
                result = self.native.measure(synthetic(kind), EPOCH, CFO)
                self.assertLessEqual(result["margin"], 0.025)

    def test_input_contract_rejects_wrong_bounds_and_state(self):
        iq = synthetic()
        with self.assertRaises(ValueError):
            self.native.measure(iq[:-1], EPOCH, CFO)
        for epoch, cfo in ((math.nan, CFO), (EPOCH, math.inf), (EPOCH, 500_000)):
            with self.assertRaises(ValueError):
                self.native.measure(iq, epoch, cfo)

    def test_physical_period_wrap_is_score_equivalent_at_both_rates(self):
        for rate, phase in ((2_500_000, 3333.1), (5_000_000, 6666.6)):
            with self.subTest(rate=rate):
                rng = np.random.default_rng(rate)
                iq = rng.integers(-20, 21, (rate // 50, 2), dtype=np.int16)
                with NativeKnownState(rate, "lower") as native:
                    wrapped = phase - rate / 750.0
                    positive = native.measure(iq, phase, 0.0)
                    negative = native.measure(iq, wrapped, 0.0)
                    self.assertEqual(positive["epoch_samples"], negative["epoch_samples"])
                    self.assertEqual(positive["exact_score"], negative["exact_score"])
                    self.assertEqual(positive["control_score"], negative["control_score"])


if __name__ == "__main__":
    unittest.main()
