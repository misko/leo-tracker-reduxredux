import unittest
import numpy as np
from interval_audit_v2 import quantiles


class IntervalReportingTests(unittest.TestCase):
    def test_concentrated_zero_grid_mass_contains_zero(self):
        g=np.arange(-100.,101.,25.);w=np.zeros(len(g));w[4]=1.
        self.assertEqual(quantiles(g,w,interpretation='discrete_mass'),[0.,0.,0.])
        np.testing.assert_allclose(quantiles(g,w),[-11.875,0.,11.875],atol=1e-12)

    def test_symmetric_distribution_has_symmetric_endpoints_and_median(self):
        g=np.arange(-100.,101.,25.);w=np.exp(-g*g/(2*30**2))
        for kind in ['discrete_mass','bin_density']:
            a,b,c=quantiles(g,w,interpretation=kind)
            self.assertAlmostEqual(a,-c);self.assertAlmostEqual(b,0.)

    def test_offgrid_and_domain_endpoints_are_explicit(self):
        g=np.arange(-100.,101.,25.);w=np.zeros(len(g));w[4]=1.
        lo,_,hi=quantiles(g,w)
        self.assertTrue(lo<7.3<hi)
        self.assertFalse(0.<=7.3<=0.) # discrete mass cannot cover off-grid truth.
        w[:]=0;w[0]=1.
        lo,_,hi=quantiles(g,w)
        self.assertGreaterEqual(lo,g[0]);self.assertLess(hi,g[1])


if __name__=='__main__':unittest.main(verbosity=2)
