"""Owned algebra/layout/gate-copy tests; no scan propagation or position fits."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import adapter as a
import parent_diagnostics as dg
import runner as k
from ds23_position_information import marginal_position_information
from dsx01_hierarchical_bound import hierarchical_bound


class ScientificTests(unittest.TestCase):
    def test_old_slots_and_constants_are_preserved(self):
        p=SimpleNamespace(hardware=np.zeros((3,8)),smooth=np.zeros((3,4)),labels=[1,2],supported=[1],members=[0,1,2],phase_sigma=np.array([2.,4.]))
        s=a.coordinate_spec(p,np.array([1.,-2.]),3,2)
        self.assertEqual(s['old_width'],20)
        np.testing.assert_array_equal(s['old_constant_indices'],[17,18,19])
        np.testing.assert_array_equal(s['scales'][17:20],[.3]*3)
        np.testing.assert_array_equal(s['scales'][20:],[1.]*6)
        np.testing.assert_array_equal(s['mean'][12:14],[.5,-.5])
        np.testing.assert_array_equal(s['groups'][20:],[-1]*6)

    def test_zero_append_normalized_VI_equivalence(self):
        rng=np.random.default_rng(71);u=rng.normal(size=(20,5));raw=rng.normal(size=20)*20
        args=(raw,u,np.full(20,40.),np.repeat([0,1],10))
        old=hierarchical_bound(*args,prior_groups=np.array([-1,0,1,-1,-1]),prior_nu=3)
        new=hierarchical_bound(raw,np.column_stack((u,np.zeros((20,6)))),args[2],args[3],
            prior_groups=np.array([-1,0,1,-1,-1]+[-1]*6),prior_nu=3)
        self.assertAlmostEqual(old['negative_twice_elbo'],new['negative_twice_elbo'],places=10)
        np.testing.assert_allclose(old['coefficient'],new['coefficient'][:5],atol=1e-13)
        np.testing.assert_array_equal(new['coefficient'][5:],0.)

    def test_shared_family_loading_and_zero_design(self):
        p=SimpleNamespace(extra_families=(10,20),flat_times=np.arange(4.),flat_labels=np.array([0,1,0,1]),
            labels=[10,20],q=np.array([1.,2.,3.,4.]),extra_scale=1.,sky=None,extra_mode_bank=None,reference=np.zeros(2))
        modes=np.arange(12.).reshape(4,3)
        with patch.object(a,'paired_frequency_modes',return_value=modes):
            b=a.extra_columns(p,np.zeros(2))
            np.testing.assert_array_equal(b[[0,2],:3],modes[[0,2]]*p.q[[0,2],None])
            np.testing.assert_array_equal(b[[1,3],:3],0.)
            np.testing.assert_array_equal(b[[1,3],3:],modes[[1,3]]*p.q[[1,3],None])
            p.extra_scale=0.
            np.testing.assert_array_equal(a.extra_columns(p,np.zeros(2)),0.)

    def test_gate_copy_omits_means_without_cache_mutation(self):
        c=dict(coefficient=np.array([2.,3.]),features=np.array([[7.,11.],[13.,17.]]),
            conditional_residual_hz=np.array([5.,6.]),linear_raw_prediction_residual_hz=np.array([4.]),predictive_extra_columns=np.array([[19.]]))
        p=SimpleNamespace(extra_families=[9],extra_start=1,linear_entries=[1],calculate=lambda x:c,
            original_calibration_supported=(7,),supported=[7],conditional_frequency=lambda x:('full',),conservative_frequency=lambda x:('conservative',))
        before=a.fingerprint(c);view=a.gate_view(p);gate=view.calculate(np.zeros(2))
        np.testing.assert_array_equal(gate['conditional_residual_hz'],[38.,57.])
        np.testing.assert_array_equal(gate['linear_raw_prediction_residual_hz'],[61.])
        self.assertEqual(before,a.fingerprint(c));self.assertEqual(view.supported,[7])
        self.assertEqual(a.gate_view(p,'literal_expanded_fullmean').supported,[7,9])
        self.assertEqual(p.supported,[7])

    def test_shared_covariance_dense_oracle_and_information_monotonicity(self):
        rng=np.random.default_rng(93);u=rng.normal(size=(40,7));b=rng.normal(size=(40,3));j=rng.normal(size=(40,2))
        w=np.linspace(.01,.02,40);prior=np.linspace(.5,2.,7)
        oracle=dg.dense_oracle(u,w,prior,b);self.assertTrue(oracle['passed'])
        old=marginal_position_information(j,u,w,prior)
        new=marginal_position_information(j,np.column_stack((u,b)),w,np.r_[prior,np.ones(3)])
        self.assertGreaterEqual(np.linalg.eigvalsh(old-new).min(),-1e-10)

    def test_triage_does_not_cross_criteria_between_arms(self):
        def row(move,var):return dict(numerically_qualified=True,movement_proxy_norm_km=move,weak_variance_fractional_change=var)
        case=dict(case='x',status='complete',arms={'c0':row(.06,.01),'fitted_c':row(.01,.06)})
        self.assertFalse(dg.triage([case])['proceed_all_four_cases'])
        case['arms']['fitted_c']=row(.06,.01)
        self.assertTrue(dg.triage([case])['proceed_all_four_cases'])
        case['arms']['c0']['numerically_qualified']=False
        self.assertFalse(dg.triage([case])['proceed_all_four_cases'])

    def test_expired_budget_cannot_start_work(self):
        with self.assertRaises(TimeoutError):
            with k.alarm(0):self.fail('expired work started')

    def test_membership_preservation_requires_both_arms(self):
        original={arm:dict(accepted_observation_ids=[1,2]) for arm in a.r.ARMS}
        candidate={arm:dict(accepted_observation_ids=[1,2,3]) for arm in a.r.ARMS}
        self.assertTrue(k.preservation(original,candidate)[0])
        candidate['fitted_c']['accepted_observation_ids']=[1]
        self.assertFalse(k.preservation(original,candidate)[0])
        del candidate['fitted_c'];self.assertFalse(k.preservation(original,candidate)[0])

    def test_absolute_phase_gate_and_Gamma_are_required(self):
        arms={arm:dict(state={'phases':[0.]},final_phase_change_s=.001,final_log_precision_change=1e-6) for arm in a.r.ARMS}
        with patch('algo02_scan.pair_passes',return_value=True):
            self.assertTrue(a.qualification(arms)['conservative_paired_valid'])
            arms['c0']['state']['phases']=[15.1]
            self.assertFalse(a.qualification(arms)['conservative_paired_valid'])
            arms['c0']['state']['phases']=[0.];arms['fitted_c']['final_log_precision_change']=1e-3
            self.assertFalse(a.qualification(arms)['phase_Gamma_converged_both_arms'])


if __name__=='__main__':unittest.main()
