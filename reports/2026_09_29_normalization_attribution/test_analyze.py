import math
import unittest

from analyze import components


class AttributionTest(unittest.TestCase):
    def test_identity_across_background_strength_and_missing_mass(self):
        # Construct densities independently, including nearly pure signal and
        # nearly pure background. Attribution must recover their log ratio.
        for signal in (1e-30, 0.01, 1.0, 100, 1e30):
            for mass in (0.2, 0.999, 1.0):
                retained = 0.8 * signal + 0.2
                full_signal = signal * (10 / 500) / mass
                full = 0.8 * full_signal + 0.2
                row = dict(
                    retained_visible=10,
                    visible=500,
                    full=dict(
                        retained_mass=mass,
                        retained_signal_probability=0.8 * signal / retained,
                        full_signal_probability=0.8 * full_signal / full,
                        exact_full_log_score=math.log(full),
                        retained_log_score=math.log(retained),
                    ),
                )
                terms, error = components(row, "full")
                self.assertLess(error, 1e-12)
                self.assertAlmostEqual(terms["actual"], math.log(full / retained), places=12)


if __name__ == "__main__":
    unittest.main()
