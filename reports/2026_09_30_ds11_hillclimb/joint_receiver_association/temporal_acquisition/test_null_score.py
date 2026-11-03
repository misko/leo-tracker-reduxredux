from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from temporal_receiver import sequence_score
from null_score import score


class ConstantRefreshTests(unittest.TestCase):
    def test_missing_rows_integrate_exactly_and_gradient_matches(self):
        times = np.array([0., .2, .6, 1., 2., 6.])
        states = np.array([1, 2, 1, 3, 3, 2])
        mask = np.array([True, False, True, False, True, True])
        p = np.array([.2, .5, .3])
        sequences = [(times[mask], states[mask], p)]
        for tau in (.01, 1., 10., 60.):
            value, gradient = score(np.log(tau), sequences)
            expected, _ = sequence_score(times, np.broadcast_to(np.log(p), (1, len(times), 3)), states, mask, tau)
            self.assertAlmostEqual(value, expected[0], places=10)
            numerical = (score(np.log(tau) + 1e-5, sequences)[0] - score(np.log(tau) - 1e-5, sequences)[0]) / 2e-5
            self.assertAlmostEqual(gradient, numerical, places=7)

    def test_empty_and_single_observation_are_tau_independent(self):
        p = np.array([.2, .5, .3])
        self.assertEqual(score(0., []), (0., 0.))
        value, gradient = score(4., [([5.], [2], p)])
        self.assertAlmostEqual(value, np.log(.5))
        self.assertEqual(gradient, 0.)
