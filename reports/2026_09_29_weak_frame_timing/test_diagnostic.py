import unittest

import numpy as np
from diagnostic import HELD, TS, choose, evaluate, train


class TimingTests(unittest.TestCase):
    def test_frequency_and_prediction(self):
        y = np.exp(2j * np.pi * 127 * np.arange(300) * TS)[:, None] * np.ones((1, 8))
        f, q, g = train(y)
        self.assertAlmostEqual(f, 127, places=3)
        self.assertGreater(q, 0.999)
        self.assertLess(evaluate(y, f, g)["nmse"], 1e-8)

    def test_held_mutation_cannot_select_timing(self):
        rng = np.random.default_rng(39)
        y = np.exp(2j * np.pi * 127 * np.arange(300) * TS)[:, None] * np.ones((1, 8))
        other = rng.normal(size=y.shape) + 1j * rng.normal(size=y.shape)
        candidates = [other, y]
        a, af = choose(candidates)
        candidates[1][HELD] *= -3j
        b, bf = choose(candidates)
        self.assertEqual(a, 1)
        self.assertEqual(a, b)
        for x, z in zip(af, bf, strict=True):
            self.assertEqual(x[:2], z[:2])
            np.testing.assert_array_equal(x[2], z[2])


if __name__ == "__main__":
    unittest.main()
