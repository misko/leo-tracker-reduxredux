import unittest
import numpy as np
from run import slope_fit, predict, PERIOD


class DriftTests(unittest.TestCase):
    def test_injected_and_alias_wrapped_drift(self):
        fit = slope_fit([(0, PERIOD/2-10), (10, -PERIOD/2+10), (20, -PERIOD/2+30)])
        self.assertAlmostEqual(fit[0], 2)
        t = np.array([0., 5., 10.])
        baseline, predicted = predict(t, 900+2*t, np.array([-1., 5., 15., 21.]), fit)
        np.testing.assert_allclose(predicted, [910, 910, 930, 910])
        self.assertTrue(np.all(baseline == 910))

    def test_support_slope_gate_and_exact_fallback(self):
        self.assertIsNone(slope_fit([(0, 0), (10, 100)]))
        self.assertIsNone(slope_fit([(0, 0), (10, 300), (20, 600)]))
        a,b = predict(np.arange(6), np.arange(6), np.array([1.,2.]), None)
        np.testing.assert_array_equal(a,b)


if __name__ == '__main__':
    unittest.main()
