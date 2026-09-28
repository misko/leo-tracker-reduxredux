"""Independent synthetic checks of calibration and header exclusion."""

import unittest

import numpy as np
from recover import TS, geometry, pilot_calibrate


class RecoveryTests(unittest.TestCase):
    def fixture(self):
        rng = np.random.default_rng(701)
        truth = np.exp(0.5j * np.pi * rng.integers(0, 4, (301, 1024)))
        pilot = truth[1:, 488:496].copy()
        response = 3 * np.exp(1j * (0.9 + 0.035 * (np.arange(1024) - 491.5)))
        observed = (
            truth * response * np.exp(2j * np.pi * 734.23 * (np.arange(301) - 1) * TS)[:, None]
        )
        return observed, truth, pilot

    def test_recovers_withheld_symbols(self):
        observed, truth, pilot = self.fixture()
        recovered, diag = pilot_calibrate(observed, pilot)
        self.assertAlmostEqual(diag["frequency_hz"], 734.23, places=2)
        self.assertAlmostEqual(diag["phase_slope"], 0.035, places=5)
        np.testing.assert_allclose(recovered[:21, 476:508], truth[:21, 476:508], atol=1e-5)

    def test_header_values_cannot_change_calibration(self):
        observed, _, pilot = self.fixture()
        _, before = pilot_calibrate(observed, pilot)
        observed[:21] *= 7 * np.exp(0.63j)
        _, after = pilot_calibrate(observed, pilot)
        self.assertEqual(before["frequency_hz"], after["frequency_hz"])
        self.assertEqual(before["phase_slope"], after["phase_slope"])
        self.assertGreater(after["pilot_holdout_evm"], before["pilot_holdout_evm"] + 1)

    def test_lower_edge_frequency_and_calibration(self):
        bins, pilot_bins, center = geometry("lower")
        self.assertEqual(center, -115429687.5)
        self.assertFalse(set(bins) & set(pilot_bins))
        observed, truth, _ = self.fixture()
        pilot = truth[1:, pilot_bins]
        recovered, diag = pilot_calibrate(observed, pilot, edge="lower")
        self.assertAlmostEqual(diag["frequency_hz"], 734.23, places=2)
        np.testing.assert_allclose(recovered[:21, bins], truth[:21, bins], atol=1e-5)


if __name__ == "__main__":
    unittest.main()
