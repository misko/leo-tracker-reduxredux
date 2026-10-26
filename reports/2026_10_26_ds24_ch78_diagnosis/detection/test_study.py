import unittest
import numpy as np
from study import analytic, injection, truth_error, EPOCH, CFO
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score


class InjectionTests(unittest.TestCase):
    def test_independent_waveform_matches_public_first_frame(self):
        for edge in ['lower', 'upper']:
            expected = qin_edge_pilot_frame(10_000_000, edge)
            actual = analytic(len(expected), 10_000_000, edge, epoch=0, cfo=0)*np.exp(-.37j)
            np.testing.assert_allclose(actual, expected, atol=3e-7)

    def test_native_power_ratio(self):
        background = np.full(1000, 14+12j)
        wave = analytic(1000, 10_000_000, 'lower')
        values, receipt = injection(background, wave, -18)
        self.assertAlmostEqual(np.mean(abs(values-background)**2)/np.mean(abs(background)**2), 10**-1.8)
        self.assertEqual(receipt['background_mean_complex_power_native'], 340.)

    def test_timing_identity_uses_exact_frame_period(self):
        candidate = dict(integer_epoch_sample=round(EPOCH+10_000_000/750),
            fractional_epoch_offset_samples=EPOCH+10_000_000/750-round(EPOCH+10_000_000/750),
            fractional_tracking_cfo_hz=CFO+12)
        error = truth_error(candidate, 10_000_000)
        self.assertAlmostEqual(error['timing_error_samples'], 0)
        self.assertEqual(error['cfo_error_hz'], 12)

    def test_known_anchor_noiseless(self):
        for edge in ['lower', 'upper']:
            wave = analytic(200000, 10_000_000, edge).astype(np.complex64)
            score = conditioned_glrt64_score(wave, 10_000_000, epoch_sample=int(EPOCH),
                fractional_epoch_offset_samples=.25, acquired_cfo_hz=CFO, edge=edge)
            self.assertGreater(score.margin, .5)
            self.assertLess(abs(score.tracking_cfo_hz-CFO), 100)


if __name__ == '__main__':
    unittest.main(verbosity=2)
