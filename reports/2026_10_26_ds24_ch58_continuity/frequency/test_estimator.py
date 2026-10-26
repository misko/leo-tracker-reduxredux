import inspect
import unittest
from unittest.mock import patch
import numpy as np
import estimator


def packet(hypotheses=True):
    return dict(prediction_id='unit', target_support=dict(start_counter=3540000,stop_counter=3640000),
        hypotheses=[dict(hypothesis_id='h0',epoch_samples=4321.25,predicted_cfo_hz=1234.,
            prediction_sigma_hz=150.,elapsed_s=.354,carry_cfo_hz=1200.,
            donors=[dict(observation_id='old',support=dict(start_counter=0,stop_counter=100000))])]
            if hypotheses else [])


class FrequencyTests(unittest.TestCase):
    def test_no_donor_is_explicit_and_does_not_touch_samples(self):
        out=estimator.estimate(np.zeros(100000,complex),10_000_000,'lower',packet(False))
        self.assertEqual(out['status'],'no_donor')
        self.assertEqual(out['hypotheses'],[])
        self.assertEqual(out['independent_new_observations'],0)

    def test_overlapping_donor_and_wrong_support_are_rejected(self):
        p=packet(); p['hypotheses'][0]['donors'][0]['support']['stop_counter']=3540001
        with self.assertRaisesRegex(ValueError,'earlier/disjoint'):
            estimator.estimate(np.zeros(100000,complex),10_000_000,'lower',p)
        with self.assertRaisesRegex(ValueError,'length mismatch'):
            estimator.estimate(np.zeros(99999,complex),10_000_000,'lower',packet())

    def test_profile_scale_matches_complex_gaussian_amplitude_projection(self):
        rng=np.random.default_rng(2); c=rng.normal(size=(4,64))+1j*rng.normal(size=(4,64))
        t=np.tile(np.arange(64)*4.4e-6,(4,1)); energy=np.ones(64)*44.; s2=1.7
        out=estimator.profile(c,t,energy,s2,150.,.354)
        direct=[]
        for f in estimator.GRID:
            direct.append(sum(abs(np.sum(row*np.exp(-2j*np.pi*f*tt)))**2
                              for row,tt in zip(c,t))/(s2*energy.sum()))
        np.testing.assert_allclose(out['relative_log_likelihood'],np.asarray(direct)-max(direct),atol=1e-13)
        self.assertAlmostEqual(sum(out['conditional_grid_weights']),1.)
        self.assertFalse(out['uncertainty_weights_qualified'])

    def test_multiple_frequency_modes_are_not_collapsed(self):
        t=np.tile(np.arange(64)*4.4e-6,(8,1))
        c=np.exp(2j*np.pi*2500*t)+np.exp(-2j*np.pi*2500*t)
        out=estimator.profile(c,t,np.ones(64),.001,1000.,.354)
        self.assertGreaterEqual(len(out['modes']),2)

    def test_signature_source_and_ownership_do_not_use_evaluation_truth(self):
        self.assertEqual(list(inspect.signature(estimator.estimate).parameters),
                         ['later_samples','sample_rate_hz','edge','packet'])
        src=inspect.getsource(estimator)
        self.assertNotIn('import study',src)
        self.assertNotIn('213456.75',src)
        self.assertNotIn('GPS',src)
        self.assertNotIn('_conditioned_correlation_workspace',src)

    def test_noise_convention_and_fractional_support_are_explicit(self):
        rng=np.random.default_rng(3)
        z=(rng.normal(size=100000)+1j*rng.normal(size=100000))/np.sqrt(2)
        c,t,e,s2,stats=estimator.correlations(z,10_000_000,'lower',4321.25,200000.)
        self.assertEqual(c.shape[1],64)
        self.assertEqual(t.shape,c.shape)
        self.assertGreater(s2,.5); self.assertLess(s2,1.2)
        self.assertTrue(all(0<=a<b<=100000 for a,b in stats['complete_frame_sample_envelopes']))


if __name__=='__main__': unittest.main(verbosity=2)
