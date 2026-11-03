import unittest
from types import SimpleNamespace
import numpy as np
from profile_kernel import components,replacement_nll,timing_penalty,replaced_timing_penalty,predict_single_candidate
from leo.analysis.shared_scan_model import density
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.analysis.regional_position_score import predict_orbits,observer
from leo.analysis.shared_scan_model import elevation_geometry
from leo.contracts.regional_position import PositionOrbitBank,PositionObservations,RegionalPrior


class KernelTests(unittest.TestCase):
    def test_replacement_replays_full_normalized_density_including_visibility(self):
        rng=np.random.default_rng(8);n=19;k=5
        measured=rng.uniform(-ALIAS_HZ/2,ALIAS_HZ/2,n)
        prediction=measured[:,None]+rng.normal(0,400,(n,k));weight=rng.uniform(0,1,(n,k))
        sigma=np.full(n,125.);q=np.array([.03,.04,.05,.06,.02])
        config=SimpleNamespace(clutter_rate=.5,detection_budget=.2)
        odds,signal=components(measured[:,None],prediction,weight,sigma[:,None],q,ALIAS_HZ)
        for index in range(k):
            other=np.arange(k)!=index
            candidate=prediction[:,index]+rng.normal(0,100,n);visibility=rng.uniform(0,1,n)
            new_odds,new_signal=components(measured,candidate,visibility,sigma,q[index],ALIAS_HZ)
            score=replacement_nll(odds[:,other].sum(axis=1),signal[:,other].sum(axis=1),
                new_odds,new_signal,config.clutter_rate,ALIAS_HZ)
            full=prediction.copy();full[:,index]=candidate;ww=weight.copy();ww[:,index]=visibility
            reference=density(measured,full,ww,sigma,q,config)[0].nll
            self.assertAlmostEqual(score,reference,places=10)

    def test_zero_posterior_candidate_still_has_visibility_normalizer_effect(self):
        measured=np.zeros(4);sigma=np.full(4,125.)
        odds,signal=components(measured,np.full(4,50000.),np.ones(4),sigma,.1,ALIAS_HZ)
        visible=replacement_nll(np.zeros(4),np.zeros(4),odds,signal,.5,ALIAS_HZ)
        invisible=replacement_nll(np.zeros(4),np.zeros(4),np.zeros(4),np.zeros(4),.5,ALIAS_HZ)
        self.assertGreater(visible,invisible)

    def test_common_and_relative_prior_match_explicit_gauge_for_each_candidate(self):
        rng=np.random.default_rng(18)
        for k in [2,3,86]:
            total=rng.normal(0,3,k);grid=np.linspace(-20,20,41)
            for index in [0,k-1]:
                copy=np.tile(total,(len(grid),1));copy[:,index]=grid
                np.testing.assert_allclose(replaced_timing_penalty(total,index,grid,3.,2.),
                    timing_penalty(copy,3.,2.),rtol=1e-13,atol=1e-12)

    def test_batched_candidates_match_individual_likelihood_queries(self):
        rng=np.random.default_rng(63);measured=np.zeros(13);prediction=rng.normal(0,100,(7,13))
        odds,signal=components(measured,prediction,np.ones((7,13)),125.,.03,ALIAS_HZ)
        batch=replacement_nll(np.ones(13)*.2,np.ones(13)*.0001,odds,signal,.5,ALIAS_HZ)
        for i in range(7):self.assertAlmostEqual(batch[i],replacement_nll(np.ones(13)*.2,
            np.ones(13)*.0001,odds[i],signal[i],.5,ALIAS_HZ),places=12)

    def test_batched_ephemeris_predictions_match_public_ports(self):
        prior=RegionalPrior();nodes=np.arange(-21.,322.,.25);site,up=observer(prior,[0,0])
        velocity=np.array([1.,3.,-2.]);acceleration=np.array([.001,-.002,.003])
        positions=site+1000*up+nodes[:,None]*velocity+.5*nodes[:,None]**2*acceleration
        velocities=velocity+nodes[:,None]*acceleration
        bank=PositionOrbitBank(np.array([41]),nodes,positions[None],velocities[None])
        obs=PositionObservations(tuple(map(str,range(4))),np.array([0.,67.13,185.4,300.]),
            np.zeros(4),np.array([11e9,11.25e9,12e9,12.25e9]),np.array([0,1,0,1]),
            np.array([1,2,6,7]),np.ones(4))
        timings=np.array([-20.,-.075,0.,2.25,20.]);actual,sine=predict_single_candidate(bank,obs,prior,[12.,-7.],timings)
        for i,t in enumerate(timings):
            expected=predict_orbits(bank,obs,prior,[12.,-7.],np.array([t]),derivatives=False)[0][:,0]
            elevation=elevation_geometry(bank,obs,prior,[12.,-7.],np.array([t]))[0][:,0]
            np.testing.assert_allclose(actual[i],expected,rtol=0,atol=1e-8)
            np.testing.assert_allclose(sine[i],elevation,rtol=0,atol=1e-14)
        with self.assertRaises(ValueError):predict_single_candidate(bank,obs,prior,[0,0],np.array([30.]))


if __name__=='__main__':unittest.main()
