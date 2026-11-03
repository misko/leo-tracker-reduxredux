import unittest

from run import projected


class GradientTests(unittest.TestCase):
    def test_outward_gradient_removed_at_active_bound(self):
        self.assertEqual(projected([-1, 1], [5, -7], [(-1, 1)] * 2), 0)

    def test_inward_and_interior_gradients_retained(self):
        self.assertEqual(projected([-1, 0], [-5, 7], [(-1, 1)] * 2), 7)


if __name__ == "__main__":
    unittest.main()
