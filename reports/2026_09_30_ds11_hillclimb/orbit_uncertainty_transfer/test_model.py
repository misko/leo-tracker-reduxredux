import unittest
import numpy as np
from model import track_scores,fit_prior,predictive,BETA

class PriorTests(unittest.TestCase):
    def test_centers_and_training_scores_ignore_held(self):
        t=np.arange(20.);m=t%2==0;r=800+2*t;d=3*t+.1*t*t
        a,_=track_scores(t,r,d,m);r[~m]+=1e6;d[~m]-=1e6;b,_=track_scores(t,r,d,m)
        for arm in a:np.testing.assert_array_equal(a[arm]['train'],b[arm]['train'])
        c,_=track_scores(t,r+6000,d-2000,m)
        for arm in b:np.testing.assert_allclose(b[arm]['train'],c[arm]['train'],atol=1e-9)
    def test_zero_direction_exact_baseline_and_symmetric_prior(self):
        scores,_=track_scores(np.arange(12.),np.arange(12.),np.zeros(12),np.arange(12)<8)
        s=scores['orbit'];prior=fit_prior(np.tile(s['train'],(5,1)))
        self.assertTrue(prior['converged'])
        self.assertAlmostEqual(predictive(s['train'],s['joint'],prior['weights']),s['joint'][0]-s['train'][0],places=10)
        self.assertEqual(sum(BETA),0.)
