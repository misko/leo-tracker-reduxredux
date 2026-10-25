"""Owned algebra and negative-control tests, with no corpus position fitting."""

import unittest
import numpy as np

import contrasts as c


class ContrastTests(unittest.TestCase):
    def test_brackets_no_extrapolation_or_large_gap(self):
        pairs=c.brackets(np.array([-1.,.25,1.,2.,4.]),np.array([0.,1.,4.]))
        self.assertEqual([v[0] for v in pairs],[1,2,4])
        self.assertEqual(pairs[0][3],.25)

    def test_interpolation_covariance_preserves_reused_endpoint(self):
        a=np.array([[1.,0.,-.75,-.25,0.],[0.,1.,0.,-.75,-.25]])
        sigma=np.array([2.,3.,4.,5.,6.])
        covariance=(a*sigma)@(a*sigma).T
        self.assertEqual(covariance[0,1],.25*.75*25)
        rng=np.random.default_rng(2026102519)
        samples=(rng.normal(size=(40000,5))*sigma)@a.T
        np.testing.assert_allclose(np.cov(samples.T),covariance,rtol=.035,atol=.1)

    def test_affine_and_c_alias_terms_are_removed(self):
        t=np.linspace(0,100,17);d=np.column_stack((np.ones(len(t)),t/100))
        covariance=np.diag(np.linspace(2,5,len(t))**2)
        raw=np.sin(t/13)
        original=c.affine_null(raw,covariance,d,t)
        changed=c.affine_null(raw+7*c.PERIOD+5300+12*t,covariance,d,t)
        np.testing.assert_allclose(original['y'],changed['y'],atol=1e-9)
        self.assertEqual(original['dimension'],15)
        self.assertLess(original['affine_leak'],1e-12)

    def test_gaussian_predictive_matches_dense_covariance(self):
        rng=np.random.default_rng(72)
        train=[dict(y=rng.normal(size=23),b=rng.normal(size=(23,31))*.2)]
        target=dict(y=rng.normal(size=15),b=rng.normal(size=(15,31))*.2,reconstruction=np.eye(15))
        mean,precision=c.posterior(train)
        metrics,_=c.predictive(target,mean,precision)
        residual=target['y']-target['b']@mean
        covariance=np.eye(15)+target['b']@np.linalg.solve(precision,target['b'].T)
        dense=15*np.log(2*np.pi)+np.linalg.slogdet(covariance)[1]+residual@np.linalg.solve(covariance,residual)
        self.assertAlmostEqual(metrics['negative_twice_log_density'],dense,places=10)
        old_mean=mean.copy()
        target['y']+=9999
        np.testing.assert_array_equal(c.posterior(train)[0],old_mean)

    def test_rotation_energy_and_global_receiver_swap_invariance(self):
        rng=np.random.default_rng(5)
        train=[dict(y=rng.normal(size=18),b=rng.normal(size=(18,31)))]
        b=train[0]['b'];rotation=c.circular_rotation()
        np.testing.assert_allclose((b@rotation)@(b@rotation).T,b@b.T,atol=1e-11)
        target=dict(y=rng.normal(size=12),b=rng.normal(size=(12,31)),reconstruction=np.eye(12))
        original=c.predictive(target,*c.posterior(train))[0]
        swapped=[dict(y=-v['y'],b=v['b']) for v in train]
        opposite=dict(target,y=-target['y'])
        result=c.predictive(opposite,*c.posterior(swapped))[0]
        self.assertAlmostEqual(original['negative_twice_log_density'],result['negative_twice_log_density'],places=10)

    def test_shared_signal_is_predictable_with_negative_controls(self):
        rng=np.random.default_rng(994)
        t=np.linspace(15,285,90);b=c.basis(t)/6
        coefficient=np.zeros(31);coefficient[7]=2.;coefficient[20]=-1.5
        train=[dict(y=b@coefficient+rng.normal(size=len(t)),b=b) for _ in range(3)]
        held=dict(y=b@coefficient+rng.normal(size=len(t)),b=b,reconstruction=np.eye(len(t)))
        native=c.predictive(held,*c.posterior(train))[0]['standardized_mean_square']
        polarity=c.predictive(held,*c.posterior(train,-np.eye(31)))[0]['standardized_mean_square']
        shifted=c.predictive(held,*c.posterior(train,c.circular_rotation()))[0]['standardized_mean_square']
        self.assertLess(native,held['y']@held['y'])
        self.assertLess(native,polarity)
        self.assertLess(native,shifted)

    def test_no_signal_does_not_systematically_improve_density(self):
        rng=np.random.default_rng(2026102520);b=c.basis(np.linspace(10,290,60))/75
        gains=[]
        for _ in range(64):
            train=[dict(y=rng.normal(size=60),b=b)]
            held=dict(y=rng.normal(size=60),b=b,reconstruction=np.eye(60))
            result=c.predictive(held,*c.posterior(train))[0]
            zero=60*np.log(2*np.pi)+held['y']@held['y']
            gains.append(zero-result['negative_twice_log_density'])
        self.assertLess(np.mean(gains),0)


if __name__=='__main__':
    unittest.main()
