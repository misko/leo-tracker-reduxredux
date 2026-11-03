import unittest
import types
import numpy as np
from timing_prior_scale import apply


class TimingPriorScaleTests(unittest.TestCase):
    def objective(self):
        def penalty(v):
            g=np.zeros(8);g[6]=v[6]/100;g[7]=v[7]
            return .5*(v[6]**2/100+v[7]**2),g
        return types.SimpleNamespace(base=types.SimpleNamespace(common_prior=True,penalty=penalty),size=8,
                                     curvature=lambda v:np.diag([2.]*6+[2.01,3.,2.]))

    def test_double_sigma_quarters_actual_penalty_and_curvature(self):
        o=self.objective();v=np.arange(8,dtype=float);old,gradient=o.base.penalty(v)
        apply(o,2.)
        value,new_gradient=o.base.penalty(v)
        self.assertAlmostEqual(value,old/4);np.testing.assert_allclose(new_gradient,gradient/4)
        h=o.curvature(np.zeros(9));self.assertAlmostEqual(h[6,6],2.0025);self.assertEqual(h[7,7],2.25)
        self.assertEqual(h[8,8],2.)

    def test_unit_scale_is_identity(self):
        o=self.objective();old=o.curvature(np.zeros(9));apply(o,1.)
        np.testing.assert_array_equal(o.curvature(np.zeros(9)),old)

    def test_invalid_and_double_application(self):
        with self.assertRaises(ValueError):apply(self.objective(),0.)
        o=apply(self.objective(),1.)
        with self.assertRaises(ValueError):apply(o,1.)
