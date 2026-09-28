import math
import time
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.special import expit

import shared_effect_evaluator as subject
from paired_reception_evaluator import PairedEvaluator


def fixture(kind, sigmas=(0., 0., 1.2)):
    origin=(37.8,-122.4); receiver=np.asarray(subject.runner.base.point(*origin).ecef_km)
    banks={};blocks=[];reception={}
    for tid,times in ((11,[0,.2,.5,.8]),(22,[0,1,2,3])):
        track=SimpleNamespace(track_id=tid,times_s=np.asarray(times),
            measured_hz=np.array([0.,10.,20.,30.]),training_mask=np.array([1,1,0,0],bool))
        positions=np.stack([np.tile(receiver+s,(4,1)) for s in ([100,300,200],[-100,-300,200])])[:,None]
        banks[tid]=SimpleNamespace(source=track,position_km=positions)
        for cid,pred in ((200,[0,9,18,27]),(100,[0,11,22,33])):
            blocks.append(SimpleNamespace(track_id=tid,candidate_ids=np.array([cid]),
                predictions_hz=np.asarray(pred,float)[None,None,:],visible=np.array([True])))
        reception[tid]=[dict(observation_index=i,matched=True,detection_logit_east0=.2,
            detection_east_slope=1.,ratio_mean_east0=.1,ratio_east_slope=.5,
            log_margin_ratio_rx1_rx0=.3) for i in (2,3)]
    value=kind.__new__(kind);value.banks=banks;value.index={tid:{100:0,200:1} for tid in banks}
    value.origin=origin;value.predictions=lambda east,north:blocks
    value.parameters={"scale_hz":100.,"degrees_of_freedom":2.};value.cache={};value.started=time.monotonic()
    value.reception=reception;value.ratio_variance=.2
    value.variants={name:(reception,.2,sigma) for name,sigma in zip(("old","mixture","shared"),sigmas)}
    return value


def test_zero_sigma_exact_parity_reordered_candidates_and_weighting():
    current=fixture(subject.SharedEffectEvaluator).evaluate(0,0)
    paired=fixture(PairedEvaluator);paired.variants={"old":(paired.reception,.2),"mixture":(paired.reception,.2)}
    expected=paired.evaluate(0,0)
    assert current["weight_seconds"]==expected["weight_seconds"]==5
    for name in ("old","mixture"):
        assert current["variant_scores"][name]==pytest.approx(expected["variant_scores"][name],abs=1e-12)
    assert current["variant_scores"]["shared"] != current["variant_scores"]["mixture"]
    assert fixture(subject.SharedEffectEvaluator).evaluate(0,0)["variant_scores"]["old"]==pytest.approx(expected["variant_scores"]["old"])


def test_nonzero_detection_matches_independent_integral_and_preserves_other_terms():
    predicted=np.array([[0.,0.,0.]]);east=np.array([[.4,.4,.4]]);measured=np.zeros(3);train=np.array([1,0,0],bool)
    shortlist={"candidate_indices":[0],"profiled_cfo_hz":[0.],"log_weights":[0.],
               "scale_hz":100.,"degrees_of_freedom":2.}
    rows=[dict(observation_index=i,matched=True,detection_logit_east0=.2,detection_east_slope=.5,
               ratio_mean_east0=.1,ratio_east_slope=.3,log_margin_ratio_rx1_rx0=.2) for i in (1,2)]
    got=subject.shared_joint_heldout_score(predicted,east,measured,train,shortlist,rows,
                                           ratio_variance=.4,detection_sigma=1.3)
    z=.4; sigma=1.3
    integral=quad(lambda u:expit(z+u)**2*math.exp(-u*u/(2*sigma*sigma))/(sigma*math.sqrt(2*math.pi)),
                  -np.inf,np.inf)[0]
    assert got["candidate_detection_log_likelihood"][0]==pytest.approx(math.log(integral),abs=2e-10)
    assert got["scores"]["D_plus_geometry"] != got["scores"]["D_plus_detection"]
    assert got["quadrature"]["passed"]


def test_empty_reception_recovers_d_and_cache_identity():
    evaluator=fixture(subject.SharedEffectEvaluator);evaluator.variants={"shared":({11:[],22:[]},.2,1.)}
    first=evaluator.evaluate(0,0)
    assert first is evaluator.evaluate(0,0)
    assert first["variant_scores"]["shared"]["D"]==pytest.approx(
        first["variant_scores"]["shared"]["D_plus_geometry"])


def test_quadrature_disagreement_fails_closed(monkeypatch):
    def fake(logits, matched, sigma, order):
        return np.zeros(len(logits)) + (order == 128)
    monkeypatch.setattr(subject,"candidate_detection_loglik",fake)
    evaluator=fixture(subject.SharedEffectEvaluator,sigmas=(1.,1.,1.))
    with pytest.raises(FloatingPointError,match="quadrature"):
        evaluator.evaluate(0,0)
