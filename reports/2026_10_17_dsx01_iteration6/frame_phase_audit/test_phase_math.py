"""Arrival sign, exact large counters, physical period and unwrap seams."""
from fractions import Fraction
import unittest
import numpy as np
from phase_math import relative_counter, arrival_phase_samples, unwrap_phase_samples


class PhaseMathTests(unittest.TestCase):
    def test_absolute_counter_precision_and_no_fixed_width_multiply(self):
        session = 2**60+17
        valid = 2**60+12345
        self.assertEqual(relative_counter(valid, session, 20, 2500000), 62328)
        counter = 10**24+1234567
        expected = (Fraction((counter*750)%2500000, 750)+Fraction(500)+Fraction(1, 4))%Fraction(2500000, 750)
        self.assertAlmostEqual(arrival_phase_samples(counter, 500, .25, 2500000), float(expected), places=9)

    def test_positive_delay_has_positive_phase_even_across_the_wrap_seam(self):
        period = 2500000/750
        before = arrival_phase_samples(0, 3300, .25, 2500000)
        after = arrival_phase_samples(0, 3400, .25, 2500000)
        self.assertLess(after, before)
        unwrapped = unwrap_phase_samples([before, after], 2500000)
        self.assertAlmostEqual(unwrapped[1]-unwrapped[0], 100., places=9)
        self.assertAlmostEqual((after-before)%period, 100., places=9)

    def test_physical_fractional_period_does_not_accumulate_rounded_frame_error(self):
        period = Fraction(2500000, 750)
        values = [arrival_phase_samples(round(k*period), 500, .125, 2500000) for k in range(12)]
        residual = np.array(values)-values[0]
        self.assertLessEqual(max(abs(residual)), 1/3+1e-10)
        self.assertAlmostEqual(values[3], values[0], places=9)
        self.assertAlmostEqual(values[9], values[0], places=9)

    def test_common_counter_translation_and_epoch_delay_are_distinct(self):
        a = relative_counter(2**60+10000, 2**60, 4, 2500000)
        b = relative_counter(2**60+10**12+10000, 2**60+10**12, 4, 2500000)
        self.assertEqual(a, b)
        p = arrival_phase_samples(a, 500, -.2, 2500000)
        q = arrival_phase_samples(b, 600, -.2, 2500000)
        self.assertAlmostEqual(q-p, 100., places=9)


if __name__ == '__main__':
    unittest.main()
