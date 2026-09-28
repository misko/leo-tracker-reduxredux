import time
from types import SimpleNamespace

import numpy as np
import pytest

from dual_shared_effect_evaluator import DualSharedEffectEvaluator
from dual_track_diagnostic import DualTrackDiagnosticEvaluator


def evaluator(kind):
    import dual_track_diagnostic as subject
    origin=(37.8,-122.4);receiver=np.asarray(subject.runner.base.point(*origin).ecef_km)
    banks={};blocks=[];rx={}
    for tid,times in ((11,[0,.2,.5,.8]),(22,[0,1,2,3])):
        track=SimpleNamespace(track_id=tid,times_s=np.asarray(times),measured_hz=np.array([0.,10.,20.,30.]),training_mask=np.array([1,1,0,0],bool))
        banks[tid]=SimpleNamespace(source=track,position_km=np.stack([np.tile(receiver+s,(4,1)) for s in ([100,300,200],[-100,-300,200])])[:,None])
        # Deliberately reverse prediction versus bank candidate order.
        for cid,p in ((200,[0,9,18,27]),(100,[0,11,22,33])):blocks.append(SimpleNamespace(track_id=tid,candidate_ids=np.array([cid]),predictions_hz=np.asarray(p,float)[None,None,:],visible=np.array([True])))
        rx[tid]=[dict(observation_index=i,matched=True,detection_logit_east0=.2,detection_east_slope=1.,ratio_mean_east0=.1,ratio_east_slope=.5,log_margin_ratio_rx1_rx0=.3) for i in (2,3)]
    value=kind.__new__(kind);value.banks=banks;value.index={tid:{100:0,200:1} for tid in banks}
    value.origin=origin;value.predictions=lambda e,n:blocks;value.parameters={"scale_hz":100.,"degrees_of_freedom":2.};value.cache={};value.started=time.monotonic()
    value.variants={"old":(rx,.2,0.,0.),"detection":(rx,.2,1.,0.),"dual":(rx,.2,1.,.5)}
    return value


def logsumexp(values):
    values=np.asarray(values);m=np.max(values);return m+np.log(np.exp(values-m).sum())


def test_aggregate_exactly_matches_frozen_scorer_with_reordered_ids_and_weights():
    expected=evaluator(DualSharedEffectEvaluator).evaluate(0,0)
    diagnostic=evaluator(DualTrackDiagnosticEvaluator);actual=diagnostic.evaluate(0,0)
    assert actual["weight_seconds"]==expected["weight_seconds"]==5
    for name in expected["variant_scores"]:
        assert actual["variant_scores"][name]==pytest.approx(expected["variant_scores"][name],abs=1e-12)
    assert [t["weight_seconds"] for t in actual["tracks"]]==[1,4]
    assert all(t["candidate_ids"]==[200,100] for t in actual["tracks"])
    assert all(sum(t["training_prior"]["probabilities"])==pytest.approx(1.)
               for t in actual["tracks"])
    assert diagnostic.evaluate(0,0) is actual


def test_track_scores_reconstruct_shared_candidate_marginal_and_aggregate():
    result=evaluator(DualTrackDiagnosticEvaluator).evaluate(0,0)
    for track in result["tracks"]:
        n=track["reserve_observations"]
        for name,variant in track["variants"].items():
            lw=np.asarray(track["log_weights"]);f=np.asarray(variant["candidate_frequency_log_likelihood"])
            d=np.asarray(variant["candidate_detection_log_likelihood"]);r=np.asarray(variant["candidate_ratio_log_likelihood"])
            assert variant["scores"]["D_plus_geometry"]==pytest.approx(-logsumexp(lw+f+d+r)/n)
            assert sum(variant["frequency_posterior_probabilities"])==pytest.approx(1.)
            assert sum(variant["joint_posterior_probabilities"])==pytest.approx(1.)
            joint=np.exp(lw+f+d+r-logsumexp(lw+f+d+r))
            assert variant["joint_posterior_probabilities"]==pytest.approx(joint)
            assert variant["joint_map_candidate_id"]==track["candidate_ids"][int(np.argmax(joint))]
    for name,aggregate in result["variant_scores"].items():
        for arm,value in aggregate.items():
            rebuilt=sum(t["weight_seconds"]*t["variants"][name]["scores"][arm] for t in result["tracks"])/result["weight_seconds"]
            assert rebuilt==pytest.approx(value,abs=1e-12)


def test_variant_order_does_not_change_diagnostic_values():
    first=evaluator(DualTrackDiagnosticEvaluator).evaluate(0,0)
    other=evaluator(DualTrackDiagnosticEvaluator)
    other.variants=dict(reversed(list(other.variants.items())))
    second=other.evaluate(0,0)
    assert first["weight_seconds"]==second["weight_seconds"]
    assert first["tracks"]==second["tracks"]
    assert first["variant_scores"]==second["variant_scores"]


def test_core_reserve_and_quadrature_receipts_fail_closed(monkeypatch):
    import dual_track_diagnostic as subject
    original=subject.dual.score_variants
    def changed(*args,**kwargs):
        values=original(*args,**kwargs)
        first=next(iter(values.values()))
        first["reserve_observations"] += 1
        return values
    monkeypatch.setattr(subject.dual,"score_variants",changed)
    with pytest.raises(ValueError,match="reserve count"):
        evaluator(DualTrackDiagnosticEvaluator).evaluate(0,0)


@pytest.mark.parametrize("maximum,tolerance,passed", [
    (float("nan"), .001, True), (-1., .001, True),
    (.002, .001, True), (0., float("inf"), True), (0., .001, False)])
def test_quadrature_rejects_invalid_receipt(monkeypatch, maximum, tolerance, passed):
    import dual_track_diagnostic as subject
    original = subject.dual.score_variants
    def changed(*args, **kwargs):
        values = original(*args, **kwargs)
        next(iter(values.values()))["quadrature"].update(
            maximum_candidate_loglik_absolute_difference=maximum,
            tolerance=tolerance, passed=passed)
        return values
    monkeypatch.setattr(subject.dual, "score_variants", changed)
    with pytest.raises(ValueError, match="quadrature"):
        evaluator(DualTrackDiagnosticEvaluator).evaluate(0, 0)
