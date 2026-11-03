import math
import unittest

from summarize import mixture


class MixtureTests(unittest.TestCase):
    def test_equal_density_and_extreme_log_scores(self):
        self.assertAlmostEqual(mixture([-10000.0] * 3), -10000.0)
        self.assertAlmostEqual(mixture([-10000.0, -20000.0, -30000.0]), -10000.0 - math.log(3))

    def test_average_densities_not_log_scores(self):
        self.assertAlmostEqual(
            mixture([math.log(0.1), math.log(0.2), math.log(0.9)]), math.log(0.4)
        )


if __name__ == "__main__":
    unittest.main()
