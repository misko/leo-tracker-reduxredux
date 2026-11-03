import unittest
import numpy as np
from scipy.special import logsumexp
from scipy.stats import multivariate_normal
from evidence import age_penalty,phase_prior,components,marginal


class EvidenceTests(unittest.TestCase):
    def test_recency_odds_halve_per_day_not_per_point(self):
        self.assertEqual(age_penalty(40),0.)
        self.assertAlmostEqual(np.exp(-.5*age_penalty(72)),.5)
        with self.assertRaises(ValueError):age_penalty(-1)

    def test_phase_prior_is_normalized_for_all_widths(self):
        for s in [1.,5.,50.]:
            self.assertAlmostEqual(logsumexp(phase_prior(np.linspace(-15,15,301),s)),0.)

    def test_integrated_linear_score_matches_dense_gaussian(self):
        t=np.arange(5.);y=np.array([2.,4.,5.,3.,6.]);f=np.zeros((3,5));c=components(y,f,np.ones(3,bool),t,[0],100,noise_hz=2,bias_hz=3,rate_hz_s=.5)
        x=np.column_stack([np.ones(5),t-t.mean()]);cov=4*np.eye(5)+x@np.diag([9,.25])@x.T
        expected=multivariate_normal.logpdf(y,cov=cov)
        self.assertAlmostEqual(c['loglik'][0,0],expected)

    def test_wider_prior_is_penalized_when_data_constrain_phase(self):
        phases=np.linspace(-15,15,601);t=np.arange(5.)
        c=components(np.zeros(5),phases[:,None]*100*np.ones((1,5)),np.ones(len(phases),bool),t,[0],100,noise_hz=1,bias_hz=.01,rate_hz_s=.01)
        self.assertGreater(marginal(c,phases,10.)['score'],marginal(c,phases,1.)['score']+3)

    def test_unidentified_phase_is_not_artificially_penalized(self):
        phases=np.linspace(-15,15,301);c=components(np.zeros(5),np.zeros((301,5)),np.ones(301,bool),np.arange(5.),[0],100)
        self.assertAlmostEqual(marginal(c,phases,1.)['score'],marginal(c,phases,10.)['score'])

    def test_invisible_prior_mass_is_not_renormalized_away(self):
        phases=np.array([-1.,0.,1.]);c=components(np.zeros(5),np.zeros((3,5)),[True,True,True],np.arange(5.),[0],100)
        a=marginal(c,phases,1.)['score'];c['loglik'][0,0]=-np.inf
        self.assertGreater(marginal(c,phases,1.)['score'],a)

    def test_bad_shapes_rejected(self):
        with self.assertRaises(ValueError):components([1,2,3],np.zeros((3,2)),[True]*3,[1,2,3],[0],100)


if __name__=='__main__':unittest.main()
