import math
import unittest
from bounds import binomial_upper,independent_mean_upper


class BoundTests(unittest.TestCase):
    def test_exact_zero_events(self):
        for n in [64,256]:
            expected=1-.05**(1/n)
            self.assertAlmostEqual(binomial_upper(0,n),expected)
            self.assertAlmostEqual(independent_mean_upper(0,n),expected)

    def test_single_event_exact_tail_and_conservative_heterogeneous_bound(self):
        p=binomial_upper(1,256)
        self.assertAlmostEqual((1-p)**256+256*p*(1-p)**255,.05,places=12)
        self.assertGreater(independent_mean_upper(1,256),p)


if __name__=='__main__':unittest.main(verbosity=2)
