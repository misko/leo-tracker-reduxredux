import unittest
import numpy as np
from numpy.testing import assert_allclose
from circular import wrap,intercept


class CircularInterceptTests(unittest.TestCase):
    def test_seam_mean_and_prediction(self):
        y=np.array([4.8,-4.9,4.9,-4.8]);fit=intercept(y,10.)
        self.assertAlmostEqual(abs(fit['offset']),5.)
        self.assertAlmostEqual(fit['training_sse'],.1)

    def test_exact_global_score_matches_or_beats_fine_grid(self):
        rng=np.random.default_rng(321)
        for n in [1,2,5,12]:
            y=rng.uniform(-40,40,n);p=10.;fit=intercept(y,p)
            grid=np.linspace(-p/2,p/2,40001)
            best=float(np.min(np.sum(wrap(y[:,None]-grid[None,:],p)**2,axis=0)))
            self.assertLessEqual(fit['training_sse'],best+1e-10)
            self.assertLessEqual(best-fit['training_sse'],n*(p/40000)**2)
            self.assertEqual(fit['enumerated_cuts'],n)

    def test_independent_whole_period_translations_and_sample_permutation(self):
        y=np.array([-4.9,4.8,4.9,-4.8,3.]);a=intercept(y,10.)
        b=intercept(y+10*np.array([3,-7,0,2,-1]),10.);c=intercept(y[::-1],10.)
        assert_allclose(wrap(a['offset']-b['offset'],10.),0.,atol=1e-14,rtol=0)
        self.assertAlmostEqual(a['training_sse'],b['training_sse'],places=12)
        self.assertEqual(a,c)

    def test_held_values_do_not_enter_intercept_and_fixed_signs_are_not_selected(self):
        y=np.array([4.9,-4.9,4.8,-4.8,4.7,-4.7]);train=np.arange(6)%2==0;x=np.arange(6)*.3
        for sign in [0.,1.,-1.]:
            a=intercept((y-sign*x)[train],10.)
            changed=y.copy();changed[~train]+=7.
            self.assertEqual(a,intercept((changed-sign*x)[train],10.))


if __name__=='__main__':unittest.main()
