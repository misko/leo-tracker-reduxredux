import unittest
from unittest.mock import patch
import numpy as np
from model import TimingModel


class Quadratic:
    def __init__(self, *args):
        pass

    def evaluate(self, x, gradient):
        target = np.array([1., -2., .4])
        return -float((x-target)@(x-target)), -2*(x-target)


class TimingTests(unittest.TestCase):
    def test_prior_gradient(self):
        with patch('model.baseline.Stationary', Quadratic):
            model = TimingModel([{}], {}, 'sd010')
            x = np.array([.2, .3, -.25])
            result = model.evaluate(x)
            numerical = []
            for delta in np.eye(3)*1e-6:
                numerical.append((model.evaluate(x+delta)['score']-model.evaluate(x-delta)['score'])/2e-6)
            np.testing.assert_allclose(result['gradient'], numerical, atol=1e-7)

    def test_zero_timing_is_exact_constraint(self):
        with patch('model.baseline.Stationary', Quadratic):
            model = TimingModel([{}], {}, 'zero')
            a, b = model.evaluate([0,0,4]), model.evaluate([0,0,-3])
            self.assertEqual(a['score'], b['score'])
            self.assertEqual(a['gradient'][2], 0)
            self.assertEqual(model.bounds[2], (0., 0.))

    def test_original_score_unchanged(self):
        with patch('model.baseline.Stationary', Quadratic):
            model = TimingModel([{}], {}, 'original')
            x = np.array([.2, .3, -.25])
            self.assertEqual(model.evaluate(x)['score'], Quadratic().evaluate(x, True)[0])


if __name__ == '__main__':
    unittest.main()
