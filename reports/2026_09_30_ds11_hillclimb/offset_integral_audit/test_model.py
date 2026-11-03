import math
import unittest
import numpy as np
from scipy.special import gammaln
from model import marginal,LOG_C,SIGMA,PRIOR


class IntegralTests(unittest.TestCase):
    def test_coincident_observations_broad_prior_limit(self):
        n=8
        value=marginal(np.zeros(n),0.,n*LOG_C)
        expected=n*LOG_C+math.log(2*SIGMA)+.5*math.log(math.pi)+gammaln(2.5*n-.5)-gammaln(2.5*n)-math.log(PRIOR*math.sqrt(2*math.pi))
        self.assertLess(abs(value['log_marginal']-expected),1e-8)

    def test_anchor_invariance_and_two_modes(self):
        r=np.array([-900.,-850.,850.,900.])
        def score(b):return len(r)*LOG_C-2.5*np.log1p(((r-b)/SIGMA)**2/4).sum()-.5*(b/PRIOR)**2
        a=marginal(r,-850.,score(-850.));b=marginal(r,850.,score(850.),1e-10)
        self.assertLess(abs(a['log_marginal']-b['log_marginal']),1e-8)
        self.assertLess(a['relative_quadrature_error'],1e-7)
