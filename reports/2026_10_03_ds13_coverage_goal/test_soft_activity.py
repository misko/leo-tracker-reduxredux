import unittest
import numpy as np
from soft_activity import mixture_log_likelihood


class SoftActivityTests(unittest.TestCase):
    def test_mixture_is_normalized_not_average_log_score(self):
        local=np.log([.8,.2]);glob=np.log([.1,.9]);out=mixture_log_likelihood(local,glob)
        np.testing.assert_allclose(np.exp(out),[.73,.27]);self.assertAlmostEqual(np.exp(out).sum(),1.)

    def test_retains_global_fallback_when_local_impossible(self):
        self.assertAlmostEqual(mixture_log_likelihood([-np.inf],[-3])[0],-3+np.log(.1))

    def test_exact_endpoints_and_extreme_scores(self):
        np.testing.assert_array_equal(mixture_log_likelihood([-1000],[-2000],0),[-1000])
        np.testing.assert_array_equal(mixture_log_likelihood([-1000],[-2000],1),[-2000])
        self.assertTrue(np.isfinite(mixture_log_likelihood([-1000],[-2000])[0]))

    def test_invalid_weight_rejected(self):
        with self.assertRaises(ValueError):mixture_log_likelihood([0],[0],1.1)


if __name__=='__main__':unittest.main()
