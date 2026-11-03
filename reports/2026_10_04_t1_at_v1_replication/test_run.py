import unittest
from types import SimpleNamespace
import numpy as np
from run import TopAbsoluteCalibration, absolute_parameters


class AbsoluteTests(unittest.TestCase):
    def test_bound_and_no_input_mutation(self):
        original = np.arange(10, dtype=float)
        result = absolute_parameters(original, [1, 3], -20.)
        np.testing.assert_array_equal(original, np.arange(10))
        self.assertEqual(result[7], -20.)
        self.assertEqual(result[9], -20.)
        for bad in [20.001, -20.001, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                absolute_parameters(original, [1], bad)

    def test_fold_reference_never_changes_satellite_timing(self):
        cal = TopAbsoluteCalibration.__new__(TopAbsoluteCalibration)
        cal.group_count = 2
        cal.inverse = np.array([0, 1])
        cal.parts = [(np.array([i]), SimpleNamespace(times=np.array([float(i)])),
                      {'fitted-c': (np.zeros(8), reference, np.array([5.]))})
                     for i, reference in enumerate([-0.5, -1.0])]
        calls = []
        def predictor(data, params, rows, satellites):
            calls.append(params.copy())
            return params[6+satellites], np.ones(len(rows), bool), SimpleNamespace(tau=np.ones(len(rows)))
        cal.predictor = predictor
        predicted, visible, rate = cal.predict('fitted-c', np.array([0, 1]), 0.25)
        np.testing.assert_array_equal(predicted, np.full((2, 2), 5.25))
        self.assertTrue(visible.all())
        for p in calls:
            np.testing.assert_array_equal(p[6:], [0.25, 0.25])


if __name__ == '__main__':
    unittest.main()
