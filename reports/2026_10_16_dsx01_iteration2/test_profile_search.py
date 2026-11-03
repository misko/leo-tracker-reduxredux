import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from profile_search import timing_penalty_delta,Profiles,timing_vector
from leo.analysis.regional_position_score import zero_sum_basis
from leo.analysis.shared_scan_model import density
from leo.contracts.regional_position import PositionObservations


def synthetic_context(mask=None,held_change=0.,initial_timing=0.):
    """A coherent minority can be rescued only by sacrificing stronger support."""
    times=np.arange(40,dtype=float)
    measured=np.r_[np.zeros(30),np.full(10,5000.)]
    mask=np.ones(40,bool) if mask is None else mask
    measured[~mask]+=held_change
    full=PositionObservations(tuple(map(str,range(40))),times,measured,
        np.full(40,10.7e9),np.zeros(40,int),np.ones(40,int),np.ones(40))
    scored=replace(full,window_ids=tuple(np.array(full.window_ids)[mask]),
        **{k:getattr(full,k)[mask] for k in ['times_s','measured_hz','rf_hz','receiver','channel','margin']})
    bank=SimpleNamespace(numbers=np.array([11,22]),nodes_s=np.array([-21.,61.]))
    basis=zero_sum_basis(2)
    score=SimpleNamespace(clutter_rate=1.,detection_budget=1.6,common_sigma_s=3.,relative_sigma_s=2.)
    def predict(bank,obs,prior,point,tau,**options):
        pred=np.column_stack([np.full(len(obs.times_s),tau[0]*1000.),np.full(len(obs.times_s),40000.)])
        return pred,np.ones_like(pred,bool),None,None
    def evaluate(v,n):
        tau=v[7]+basis@v[8:]
        prediction=predict(bank,scored,None,v[:2],tau)[0]
        sigma=np.full(len(scored.times_s),125.)
        weight=np.ones_like(prediction)
        q=np.array([.8,.8])
        terms,details=density(scored.measured_hz,prediction,weight,sigma,q,score)
        penalty=.5*(v[7]/3.)**2+.5*np.sum((basis@v[8:]/2.)**2)
        details.update(detection_probability=q,sigma_hz=sigma,visibility_weight=weight)
        return (terms.nll+penalty,None,None,terms),details
    model=SimpleNamespace(bank=bank,basis=basis,score=score,mask=mask,clock_count=0,
        visibility_width=1e-5,scored_observations=scored,evaluate_details=evaluate,
        original=SimpleNamespace(correction=lambda v,n:np.zeros(40)))
    vector=np.zeros(9)
    vector=timing_vector(model,vector,np.array([initial_timing,0.]))
    context=SimpleNamespace(model=model,bank=bank,prior=None,vector=vector,observations=full,train_mask=mask)
    return context,predict


class ExactProfileTests(unittest.TestCase):
    def patches(self,predict):
        return patch('profile_search.predict_orbits',predict),patch('profile_search.elevation_geometry',
            lambda bank,obs,prior,point,tau:(np.ones((len(obs.times_s),2)),None,None,None))

    def test_full_likelihood_debits_sacrificed_coherent_support(self):
        ctx,predict=synthetic_context()
        p1,p2=self.patches(predict)
        with p1,p2:
            profile=Profiles(ctx,ctx.vector,np.empty(0))
            self.assertGreater(profile.score(np.array([5.,0.]))[0],profile.initial_objective)
            np.testing.assert_allclose(profile.score(profile.tau),profile.initial_objective,atol=1e-10)

    def test_profile_recovers_better_timing_branch_without_arc_selection(self):
        ctx,predict=synthetic_context(initial_timing=5.)
        p1,p2=self.patches(predict)
        with p1,p2:
            profile=Profiles(ctx,ctx.vector,np.empty(0))
            proposals=profile.search()
        winner=next(p for p in proposals if p['satellite']==11)
        self.assertAlmostEqual(winner['timing_s'],0.,places=8)
        self.assertGreater(winner['gain'],50.)

    def test_held_cfo_cannot_change_any_coordinate_profile_or_proposal(self):
        mask=np.arange(40)%2==0
        results=[]
        for change in [0.,98765.]:
            ctx,predict=synthetic_context(mask,held_change=change,initial_timing=5.)
            p1,p2=self.patches(predict)
            with p1,p2:
                profile=Profiles(ctx,ctx.vector,np.empty(0))
                results.append((profile.score(np.array([0.,1.])),profile.search()))
        np.testing.assert_array_equal(results[0][0],results[1][0])
        self.assertEqual(results[0][1],results[1][1])


class TimingPenaltyTests(unittest.TestCase):
    def test_gauge_exact_prior_for_every_candidate(self):
        old=np.array([-12.,2.,5.,11.])
        proposed=np.array([.5,-3.,7.,-1.])
        def penalty(tau):
            return .5*(tau.mean()/3.)**2+.5*np.sum(((tau-tau.mean())/2.)**2)
        expected=[]
        for k in range(len(old)):
            trial=old.copy()
            trial[k]=proposed[k]
            expected.append(penalty(trial)-penalty(old))
        np.testing.assert_allclose(timing_penalty_delta(old,proposed,3.,2.),expected,atol=1e-12)

    def test_timing_penalty_debits_large_absolute_and_relative_changes(self):
        old=np.zeros(4)
        delta=timing_penalty_delta(old,np.full(4,20.),3.,2.)
        self.assertTrue(np.all(delta>35.))
        np.testing.assert_array_equal(timing_penalty_delta(old,old,3.,2.),np.zeros(4))


if __name__=='__main__':
    unittest.main()
