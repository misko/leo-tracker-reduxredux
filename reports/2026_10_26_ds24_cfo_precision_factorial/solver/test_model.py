import unittest
import numpy as np
from ds23_frozen_precision import conditional_gaussian,arm_prior_precision
from model import helper_prior


class PacketTests(unittest.TestCase):
    def test_same_arm_full_prior_roundtrip_and_nonunit_refusal(self):
        original=np.arange(1.,23.)/3
        self.assertTrue(np.array_equal(helper_prior(original,'c0'),original))
        fitted=np.insert(original,8,1.)
        reduced=helper_prior(fitted,'fitted_c')
        self.assertTrue(np.array_equal(arm_prior_precision(reduced,True),fitted))
        self.assertTrue(np.array_equal(reduced,original))
        fitted[8]=1.001
        with self.assertRaises(ValueError):helper_prior(fitted,'fitted_c')

    def test_precision_and_scaled_constant_units_are_not_overwritten(self):
        full=np.r_[np.ones(8),[.17,2.7,1/.3**2]]
        mapped=helper_prior(np.insert(full,8,1.),'fitted_c')
        self.assertEqual(mapped[-1],1/.3**2);self.assertEqual(mapped[-3],.17)
        for bad in (np.r_[1.,0.],np.r_[1.,np.nan]):
            with self.assertRaises(ValueError):helper_prior(bad,'c0')

    def test_conditional_normal_equations_and_density(self):
        rng=np.random.default_rng(19);u=rng.normal(size=(13,4));y=rng.normal(size=13)
        sigma=np.linspace(2,4,13);power=np.linspace(.2,1,13);tau=np.linspace(.5,2,13);prior=np.array([1.,.2,2.,1/.3**2])
        c=conditional_gaussian(y,u,sigma,power,tau,prior,1.)
        w=power*tau/sigma**2;gram=np.diag(prior)+u.T@(w[:,None]*u)
        coefficient=np.linalg.solve(gram,u.T@(w*y));innovation=y-u@coefficient
        expected=innovation@(w*innovation)+coefficient@(prior*coefficient)+np.linalg.slogdet(gram)[1]-np.log(prior).sum()+np.sum(power*(np.log(2*np.pi)+2*np.log(sigma)-np.log(tau)))
        self.assertLess(np.max(abs(c['coefficient']-coefficient)),1e-12)
        self.assertLess(abs(c['objective']-expected),1e-10)
        self.assertLess(abs(c['residual']@c['residual']+c['normalization_constant']-c['objective']),1e-10)

    def test_packet_factorial_means_are_refit_not_carried(self):
        u=np.array([[1.,0.],[1.,1.],[1.,2.]]);s=np.ones(3);prior=np.array([1.,11.11111111111111])
        a=conditional_gaussian(np.array([1.,2.,4.]),u,s,s,s,prior,1.)
        b=conditional_gaussian(np.array([1.,3.,6.]),u,s,s,s,prior,1.)
        self.assertFalse(np.array_equal(a['coefficient'],b['coefficient']))
        self.assertTrue(np.array_equal(a['coefficient_prior_precision'],b['coefficient_prior_precision']))


if __name__=='__main__':unittest.main()
