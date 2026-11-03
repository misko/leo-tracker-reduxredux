"""Numerical and synthetic checks for the research calibration estimator."""
import unittest

import numpy as np

from calibrate_candidate_density import fit, pack, signal_ratios
from leo.analysis.localization_candidate_set import candidate_set_log_ratio


class CalibrationTests(unittest.TestCase):
    def test_full_candidate_likelihood_parity(self):
        row = dict(samples=[dict(candidate_count=len(v), period_hz=t, residuals_hz=v)
                           for v, t in [([31., -50000.], 250000.), ([500., 7000., 90000.], 200000.)]])
        data = pack([row])
        for scale in [1., 70., 200., 2000.]:
            for p in [.001, .7, .999]:
                actual = np.log1p(p*(signal_ratios(data, scale)-1))
                expected = [candidate_set_log_ratio(s['residuals_hz'], [0.],
                    period=s['period_hz'], scale=scale, signal_probability=p) for s in row['samples']]
                np.testing.assert_allclose(actual, expected, atol=1e-12)

    def test_synthetic_parameter_recovery(self):
        rng = np.random.default_rng(52)
        rows = []
        for n in [1, 3, 7]:
            samples = []
            for _ in range(3000):
                values = rng.uniform(-125000, 125000, n)
                if rng.random() < .85:
                    signal = 70*np.tan(np.pi*(rng.random()-.5))
                    values[0] = (signal+125000) % 250000-125000
                samples.append(dict(candidate_count=n, period_hz=250000., residuals_hz=values.tolist()))
            rows.append(dict(samples=samples))
        result = fit(rows)
        self.assertLess(abs(result['signal_probability']-.85), .025)
        self.assertLess(abs(result['scale_hz']-70), 10)
        self.assertFalse(result['scale_grid_boundary'])
        self.assertFalse(result['probability_boundary'])


if __name__ == '__main__':
    unittest.main()
