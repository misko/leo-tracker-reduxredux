import math
import time
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.stats import multivariate_normal

import dual_shared_effect_evaluator as subject
import shared_effect_evaluator as detection


def direct_fixture(tau):
    predicted=np.array([[0.,0.,0.],[0.,0.,0.]])
    east=np.array([[.4,.3,.2],[-.5,-.4,-.3]])
    measured=np.zeros(3);train=np.array([1,0,0],bool)
    shortlist={"candidate_indices":[0,1],"profiled_cfo_hz":[0.,0.],
        "log_weights":np.log([.3,.7]),"scale_hz":100.,"degrees_of_freedom":2.}
    rows=[dict(observation_index=i,matched=True,detection_logit_east0=.2,
        detection_east_slope=.5,ratio_mean_east0=.1,ratio_east_slope=.3,
        log_margin_ratio_rx1_rx0=.2) for i in (1,2)]
    args=(predicted,east,measured,train,shortlist,rows)
    return args,dict(ratio_variance=.4,detection_sigma=1.1,ratio_tau=tau)


def test_tau_zero_exact_shared_detection_parity():
    args,kw=direct_fixture(0.)
    dual=subject.dual_shared_joint_heldout_score(*args,**kw)
    shared=detection.shared_joint_heldout_score(*args,ratio_variance=.4,detection_sigma=1.1)
    assert dual["scores"]==shared["scores"]
    assert dual["candidate_ratio_log_likelihood"]==shared["candidate_ratio_log_likelihood"]


def test_nonzero_ratio_matches_dense_covariance_oracle_and_preserves_d_detection():
    args,kw=direct_fixture(.6)
    got=subject.dual_shared_joint_heldout_score(*args,**kw)
    east=args[1]; covariance=.4*np.eye(2)+.6**2*np.ones((2,2))
    expected=[]
    for candidate in range(2):
        residual=np.array([.2-(.1+.3*east[candidate,i]) for i in (1,2)])
        expected.append(multivariate_normal.logpdf(residual,mean=np.zeros(2),cov=covariance))
    assert got["candidate_ratio_log_likelihood"]==pytest.approx(expected,abs=2e-12)
    base=detection.shared_joint_heldout_score(*args,ratio_variance=.4,detection_sigma=1.1)
    assert got["scores"]["D"]==base["scores"]["D"]
    assert got["scores"]["D_plus_detection"]==base["scores"]["D_plus_detection"]


def test_candidate_permutation_preserves_all_scores():
    args,kw=direct_fixture(.6);baseline=subject.dual_shared_joint_heldout_score(*args,**kw)
    predicted,east,measured,train,shortlist,rows=args
    permuted=dict(shortlist,log_weights=np.asarray(shortlist["log_weights"])[::-1],
                  profiled_cfo_hz=np.asarray(shortlist["profiled_cfo_hz"])[::-1])
    actual=subject.dual_shared_joint_heldout_score(
        predicted[::-1],east[::-1],measured,train,permuted,rows,**kw)
    assert actual["scores"]==pytest.approx(baseline["scores"],abs=1e-12)
    assert actual["candidate_ratio_log_likelihood"]==pytest.approx(
        baseline["candidate_ratio_log_likelihood"][::-1])


def evaluator():
    origin=(37.8,-122.4);receiver=np.asarray(subject.runner.base.point(*origin).ecef_km)
    banks={};blocks=[];rx={}
    for tid,times in ((11,[0,.2,.5,.8]),(22,[0,1,2,3])):
        track=SimpleNamespace(track_id=tid,times_s=np.asarray(times),measured_hz=np.array([0.,10.,20.,30.]),training_mask=np.array([1,1,0,0],bool))
        banks[tid]=SimpleNamespace(source=track,position_km=np.stack([np.tile(receiver+s,(4,1)) for s in ([100,300,200],[-100,-300,200])])[:,None])
        for cid,p in ((200,[0,9,18,27]),(100,[0,11,22,33])):blocks.append(SimpleNamespace(track_id=tid,candidate_ids=np.array([cid]),predictions_hz=np.asarray(p,float)[None,None,:],visible=np.array([True])))
        rx[tid]=[dict(observation_index=i,matched=True,detection_logit_east0=.2,detection_east_slope=1.,ratio_mean_east0=.1,ratio_east_slope=.5,log_margin_ratio_rx1_rx0=.3) for i in (2,3)]
    value=subject.DualSharedEffectEvaluator.__new__(subject.DualSharedEffectEvaluator)
    value.banks=banks;value.index={tid:{100:0,200:1} for tid in banks};value.origin=origin;value.predictions=lambda e,n:blocks
    value.parameters={"scale_hz":100.,"degrees_of_freedom":2.};value.cache={};value.started=time.monotonic()
    value.variants={"old":(rx,.2,0.,0.),"detection":(rx,.2,1.,0.),"dual":(rx,.2,1.,.5)}
    return value


def test_evaluator_reordered_candidates_unequal_weights_and_cache():
    value=evaluator();first=value.evaluate(0,0)
    assert first is value.evaluate(0,0);assert first["weight_seconds"]==5
    assert first["variant_scores"]["old"] != first["variant_scores"]["dual"]
    assert first["variant_scores"]["detection"]["D_plus_detection"]==pytest.approx(first["variant_scores"]["dual"]["D_plus_detection"])
    assert all(v <= .001 for v in first["quadrature_maximum_candidate_loglik_absolute_difference"].values())


def test_no_reception_and_no_matched_ratio_rows():
    value=evaluator();empty={11:[],22:[]};value.variants={"dual":(empty,.2,1.,.5)}
    row=value.evaluate(0,0)["variant_scores"]["dual"]
    assert row["D"]==pytest.approx(row["D_plus_geometry"])
    args,kw=direct_fixture(.5);rows=[dict(args[-1][0],matched=False,log_margin_ratio_rx1_rx0=None)]
    got=subject.dual_shared_joint_heldout_score(*args[:-1],rows,**kw)
    assert got["candidate_ratio_log_likelihood"]==[0.,0.]
