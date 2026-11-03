"""Synthetic live-objective tests: prior math, copied state, exact score ports."""
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from numpy.testing import assert_allclose, assert_array_equal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'2026_10_16_dsx01_models'))
sys.path.insert(0, str(ROOT/'2026_10_16_dsx01_iteration2'))
from common import Context, refit
from profile_search import Profiles, timing_vector, timing_penalty_delta
from timing_prior import prior_context, timing_penalty
from leo.application.channel_group_refinement import objective
from leo.analysis.sequential_group_calibration import SequentialShift, fixed_shift_objective
from leo.analysis.shared_scan_model import SharedScanObjective
from leo.contracts.regional_position import PositionObservations, RegionalPrior


def synthetic_context():
    n = 40
    obs = PositionObservations(tuple(map(str,range(n))), np.arange(n,dtype=float),
        np.zeros(n), np.linspace(11.1e9,11.2e9,n), np.arange(n)%2,
        np.arange(n)%8+1, np.ones(n))
    bank = SimpleNamespace(numbers=np.array([10,20,30]),nodes_s=np.array([-21.,61.]))
    prior = RegionalPrior(38.5,-121.5,250.,0.)
    nodes = np.linspace(-1,40,7)
    joint = objective(SimpleNamespace(observations=obs),bank,prior,nodes)
    shift = SequentialShift(joint.frame.receivers,np.zeros(len(joint.frame.receivers)))
    raw = fixed_shift_objective(joint.base,shift)
    model = SharedScanObjective(raw,shift)
    vector = timing_vector(model,np.zeros(model.size),np.array([-3.,2.,5.]))
    return Context('synthetic',model,model,vector,model.initial_nuisance.copy(),obs,
        bank,prior,np.ones(n,bool),nodes,{})


def prediction(bank, obs, prior, position, tau, **kwargs):
    n,k = len(obs.times_s),len(bank.numbers)
    return (np.zeros((n,k)),np.ones((n,k),bool),np.zeros((n,k,2)),np.zeros((n,k)))


def elevation(bank,obs,prior,point,tau):
    n,k = len(obs.times_s),len(bank.numbers)
    return (np.ones((n,k)),np.zeros((n,k,2)),np.zeros((n,k)),np.zeros((n,k),int))


class PriorTests(unittest.TestCase):
    def patches(self):
        return (patch('leo.analysis.shared_scan_model.predict_orbits',prediction),
                patch('leo.analysis.shared_scan_model.elevation_geometry',elevation),
                patch('profile_search.predict_orbits',prediction),
                patch('profile_search.elevation_geometry',elevation))

    def test_no_shared_cached_model_or_seed_mutation(self):
        original = synthetic_context()
        original.vector[6] = 123.
        original_vector = original.vector.copy()
        one = prior_context(original,1.,fixed_c=True)
        half = prior_context(original,.5)
        self.assertIsNot(one.model,original.model)
        self.assertIs(one.model,one.full_model)
        self.assertEqual(original.model.score.relative_sigma_s,2.)
        self.assertEqual(original.model.original.score.relative_sigma_s,2.)
        self.assertEqual(one.model.score.relative_sigma_s,1.)
        self.assertEqual(half.full_model.score.relative_sigma_s,.5)
        self.assertEqual(one.model.score.common_sigma_s,3.)
        self.assertEqual(one.vector[6],0.)
        self.assertEqual(original.vector[6],123.)
        self.assertIs(one.observations,original.observations)
        self.assertIs(one.bank,original.bank)
        self.assertIs(one.prior,original.prior)
        self.assertEqual(replace(one.model.score,relative_sigma_s=2.),original.model.score)
        one.vector[7] = 8.
        one.nuisance[:] = 1.
        assert_array_equal(original.vector,original_vector)
        assert_array_equal(original.nuisance,np.zeros_like(original.nuisance))

    def test_distinct_full_model_gets_the_same_score_without_aliasing(self):
        original = synthetic_context()
        other = prior_context(original,2.)
        original = replace(original,full_model=other.model)
        changed = prior_context(original,.5)
        self.assertIsNot(changed.model,changed.full_model)
        self.assertIs(changed.model.score,changed.full_model.score)
        self.assertEqual(original.full_model.score.relative_sigma_s,2.)

    def test_live_prior_gradient_and_common_relative_decomposition(self):
        original = synthetic_context()
        p1,p2,p3,p4=self.patches()
        with p1,p2,p3,p4:
            old=original.model.evaluate_joint(original.vector,original.nuisance)
            for width in [1.,.5]:
                changed=prior_context(original,width)
                new=changed.model.evaluate_joint(changed.vector,changed.nuisance)
                tau=changed.vector[7]+changed.model.basis@changed.vector[8:]
                expected=timing_penalty(tau,3.,width)-timing_penalty(tau,3.,2.)
                self.assertAlmostEqual(new[0]-old[0],expected,places=10)
                assert_allclose(new[1][:8],old[1][:8],atol=1e-12)
                assert_allclose(new[1][8:]-old[1][8:],
                    changed.vector[8:]*(1/width**2-1/2.**2),atol=1e-12)
                assert_allclose(new[2],old[2],atol=1e-12)
                self.assertEqual(new[3].nll,old[3].nll)

    def test_prior_delta_and_finite_difference_match_for_every_width(self):
        tau=np.array([-9.,2.,4.,7.]);proposed=np.array([3.,-5.,10.,-1.])
        for width in [2.,1.,.5]:
            expected=[]
            for k,value in enumerate(proposed):
                trial=tau.copy();trial[k]=value
                expected.append(timing_penalty(trial,3.,width)-timing_penalty(tau,3.,width))
            assert_allclose(timing_penalty_delta(tau,proposed,3.,width),expected,atol=1e-12)
            analytic=tau.mean()/(len(tau)*3.**2)+(tau-tau.mean())/width**2
            numerical=[]
            for k in range(len(tau)):
                step=np.eye(len(tau))[k]*1e-5
                numerical.append((timing_penalty(tau+step,3.,width)-
                                  timing_penalty(tau-step,3.,width))/2e-5)
            assert_allclose(analytic,numerical,atol=2e-8,rtol=2e-8)

    def test_full_model_profile_and_refit_use_identical_tightened_score(self):
        original=synthetic_context();context=prior_context(original,.5)
        p1,p2,p3,p4=self.patches()
        with p1,p2,p3,p4:
            exact=context.model.evaluate_joint(context.vector,context.nuisance)[0]
            self.assertEqual(context.full_model.evaluate_joint(context.vector,context.nuisance)[0],exact)
            profiles=Profiles(context,context.vector,context.nuisance)
            assert_allclose(profiles.score(profiles.tau),exact,atol=1e-10)
            proposed=profiles.tau.copy();proposed[0]=1.
            vv=timing_vector(context.model,context.vector,proposed)
            assert_allclose(profiles.score(proposed)[0],
                context.model.evaluate_joint(vv,context.nuisance)[0],atol=1e-10)
            result=refit(context,context.vector,context.nuisance,max_evaluations=1,max_seconds=10)
            assert_allclose(result['diagnostics']['objective'],exact,atol=1e-10)
            self.assertEqual(result['diagnostics']['evaluations'],1)

    def test_invalid_width_is_rejected(self):
        context=synthetic_context()
        for value in [0.,-1.,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):prior_context(context,value)


if __name__=='__main__':
    unittest.main()
