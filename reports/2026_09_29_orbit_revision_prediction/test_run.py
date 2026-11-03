import unittest

import numpy as np
from run import held_error, prediction


class RevisionTests(unittest.TestCase):
    def test_radial_velocity_and_interpolation(self):
        positions = np.array([[[7000.0, 0, 0]], [[7100.0, 0, 0]]])
        velocities = np.array([[[1.0, 0, 0]], [[3.0, 0, 0]]])
        measured = prediction(positions, velocities, np.zeros(3), 0.25)
        np.testing.assert_allclose(measured, [-11200000000 / 299792.458 * 1.5])

    def test_constant_offset_invariance(self):
        r = np.array([2.0, 4.0, 5.0, 9.0])
        mask = np.array([True, True, False, False])
        self.assertEqual(held_error(r, mask), 4.0)
        self.assertEqual(held_error(r + 1000, mask), 4.0)

    def test_revision_sign(self):
        delta = np.arange(10.0) * 2
        mask = np.arange(10) % 2 == 0
        self.assertEqual(held_error(delta - delta, mask), 0.0)
        self.assertGreater(held_error(delta + delta, mask), held_error(delta, mask))


if __name__ == "__main__":
    unittest.main()
