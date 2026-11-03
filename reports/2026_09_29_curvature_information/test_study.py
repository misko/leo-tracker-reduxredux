import unittest

import numpy as np
from study import curvature, prior


class CurvatureTests(unittest.TestCase):
    def test_translation_invariant_and_orthogonal(self):
        t = np.array([0, 1, 3, 4, 7, 10, 14.0])
        z = curvature(t)
        np.testing.assert_allclose(curvature(t + 100), z, atol=1e-10)
        self.assertAlmostEqual(float(z.sum()), 0, places=10)
        self.assertAlmostEqual(float((t - t.mean()) @ z), 0, places=10)

    def test_curvature_keeps_linear_but_can_remove_other_position_information(self):
        t = np.arange(15.0) - 7
        z = curvature(t)
        design = np.column_stack([t, z, np.zeros(len(t))])
        result = prior.compare([dict(a=design, z=z, group=0)])
        np.testing.assert_allclose(result["shared"]["retention"], [0, 1], atol=1e-10)
        self.assertAlmostEqual(result["shared"]["information"][0][0], float(t @ t), places=8)


if __name__ == "__main__":
    unittest.main()
