"""Truth separation, original nomination port and exact conditional laws."""
import unittest
from unittest.mock import patch
import numpy as np
import experiment as e


class NominationTests(unittest.TestCase):
    def test_expired_budget_never_arms_or_starts_another_stage(self):
        with patch.object(e.signal,'setitimer') as timer:
            for remaining in (0.,-1.):
                with self.assertRaises(TimeoutError): e.alarm(remaining)
            timer.assert_not_called()

    def catalogue(self):
        return dict(norads=np.arange(10)+100,frequency_hz=np.ones((10,3)),
            derivative_hz_per_s=np.ones((10,3)),phase_sd_s=np.ones(10),phase_means_s=np.zeros(10),
            minimum_mean_elevation_deg=np.ones(10),minimum_domain_endpoint_elevation_deg=np.ones(10))

    def test_screen_uses_injected_observation_and_never_forces_missing_true_identity(self):
        catalogue=self.catalogue(); raw=np.array([7.,8.,9.]); calls=[]
        def kernel(*args):
            calls.append(args)
            return dict(score=np.arange(10.),aliases=np.zeros(10,int))
        with patch.object(e.k,'coarse_phase_scores',kernel):
            result=e.ordinary_screen(dict(raw_hz=raw,covariance_hz2=np.eye(3)),catalogue)
        np.testing.assert_array_equal(calls[0][0],raw)
        self.assertEqual(result['candidate_norads'],list(range(100,108)))
        self.assertNotIn(109,result['candidate_norads'])
        self.assertFalse(result['forced_or_reserved_candidate'])

    def test_truth_fields_cannot_cross_screen_port(self):
        for key in ('true_identity','phase','kind','forced_nominee','reserve'):
            with self.assertRaises(ValueError):
                e.ordinary_screen(dict(raw_hz=np.zeros(3),covariance_hz2=np.eye(3),**{key:109}),self.catalogue())

    def test_response_free_pool_excludes_all_parent_families(self):
        catalogue=self.catalogue(); catalogue['phase_means_s'][2]=16.
        catalogue['minimum_domain_endpoint_elevation_deg'][3]=-1.
        catalogue['phase_sd_s'][4]=0.
        self.assertEqual(e.eligible_generators(catalogue,{0,1,5}),[6,7,8,9])

    def test_conditional_generator_closes_and_preserves_common_alias_law(self):
        seeds=e.child_seeds('DS24-0010',0)
        radio=np.arange(3.);cov=np.array([[2.,.5,0.],[.5,3.,.2],[0.,.2,1.]])
        mean=np.array([10.,11.,12.]);shape=np.arange(6.).reshape(3,2)
        values,truth=e.conditional_draw(radio,cov,mean,shape,seeds)
        expected=radio+mean+shape@truth['shape_or_polynomial_coefficients']+truth['conditional_Gaussian_hz']-truth['whole_source_alias']*e.k.PERIOD
        np.testing.assert_array_equal(values,expected)
        self.assertIn(truth['whole_source_alias'],e.ALIASES)
        _,null=e.conditional_draw(radio,cov,np.zeros(3),np.ones((3,5)),seeds)
        self.assertEqual(truth['whole_source_alias'],null['whole_source_alias'])
        np.testing.assert_array_equal(truth['conditional_Gaussian_z'],null['conditional_Gaussian_z'])
        self.assertEqual(len(set(seeds)),5)

    def test_fixed_seeds_reproduce_and_separate_trials_and_contexts(self):
        self.assertEqual(e.child_seeds('DS24-0010',0),e.child_seeds('DS24-0010',0))
        self.assertNotEqual(e.child_seeds('DS24-0010',0),e.child_seeds('DS24-0011',0))
        self.assertNotEqual(e.child_seeds('DS24-0010',0),e.child_seeds('DS24-0010',1))

    def test_adaptive_reference_selection_uses_dense_rank_and_ordering_uncertainty(self):
        rows=[dict(norad=1,status='complete',objective=0.,reference_objective=5.,score_error=5.),
            dict(norad=2,status='complete',objective=2.,reference_objective=2.,score_error=0.),
            dict(norad=3,status='complete',objective=3.,reference_objective=3.,score_error=0.),
            dict(norad=4,status='complete',objective=9.,reference_objective=8.,score_error=1.),
            dict(norad=5,status='blocked')]
        self.assertEqual(e.adaptive_candidates(rows,8.5),[2,3,1,4])

    def test_real_original_screen_kernel_receives_finite_synthetic_context(self):
        catalogue=self.catalogue();catalogue['frequency_hz']=np.arange(30.).reshape(10,3)
        result=e.ordinary_screen(dict(raw_hz=np.array([1.,2.,3.]),covariance_hz2=np.eye(3)),catalogue)
        self.assertEqual(len(result['coarse_scores']),10)
        self.assertEqual(len(result['candidate_indices']),8)
        self.assertEqual(result['catalogue_count'],10)


if __name__=='__main__':unittest.main()
