"""B-only replay, physical correction frames and prediction-space likelihood closure."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
import test_ds21_joint_bank_augmentation as fixture

from leo.analysis import hard60_joint_clock
from leo.analysis.channel_group_calibration import GroupCalibrationObjective
from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.research import model_b_fusion_audit as core
from leo.contracts.regional_position import POSITION_SCORES, PositionObservations


@pytest.fixture
def models(monkeypatch):
    monkeypatch.setattr(hard60_joint_clock,"predict_orbits",fixture.orbit_stub)
    monkeypatch.setattr(core,"predict_orbits",fixture.orbit_stub)
    case,_ = fixture.synthetic_case()
    obs = case["prepared"]["all"].observations
    models,fits = {},{}
    for name,mask in (("all",np.ones(len(obs.window_ids),bool)),("low",obs.channel<=4),
                      ("high",obs.channel>=5)):
        child = PositionObservations(tuple(k for k,b in zip(obs.window_ids,mask,strict=True) if b),
            **{k:getattr(obs,k)[mask] for k in
               ("times_s","measured_hz","rf_hz","receiver","channel","margin")})
        base = Hard60Objective(child,case["full_bank"],case["prior"],POSITION_SCORES["V16"])
        nodes = np.linspace(-5,10,8)
        clock = hard60_joint_clock.JointClockObjective(base,nodes,np.zeros((2,len(nodes))),4)
        model = GroupCalibrationObjective(clock,child.channel>=5)
        v=np.zeros(model.size)
        v[:2] = [1,2] if name=="all" else [3,4]
        v[2:7] = [30,.2,-20,-.1,100]
        v[7],v[8:] = .3,.1
        n=np.linspace(-.2,.2,len(model.initial_nuisance))
        value,_,_,terms=model.evaluate_joint(v,n)
        models[name]=model
        fits[name]=dict(vector=v,nuisance=n,objective=value,likelihood_nll=terms.nll,converged=True)
    return models,fits


def test_three_original_replays_full_band_closure_and_real_frozen_frames(models):
    m,f=models
    calls=[]
    result=core.diagnose(m,f,on_objective=lambda:calls.append(1))
    assert len(calls)==3 and result["optimizer_calls"]==0
    assert result["replay"]["all"]["rf_center_hz"]!=result["replay"]["low"]["rf_center_hz"]
    total=0
    for view in ("low","high"):
        r=result["bands"][view]
        total+=r["combinations"]["orbit-all_calibration-all"]["nll"]
        assert r["combinations"]["orbit-half_calibration-half"]["nll"]==pytest.approx(
            f[view]["likelihood_nll"],abs=1e-10)
        obs=m[view].observations
        full=core.freeze_group_calibration(m["all"],f["all"])
        expected=m[view].correction(f[view]["vector"],f[view]["nuisance"])-full.predict(
            obs.times_s,obs.rf_hz,obs.receiver,obs.channel>=5)
        assert r["total_correction_difference_hz"]["rms"]==pytest.approx(
            np.sqrt(np.mean(expected**2)))
    assert total==pytest.approx(f["all"]["likelihood_nll"],abs=1e-10)


def test_added_drift_score_matches_actual_prediction_direction_finite_difference(models):
    m,f=models
    model,fit=m["all"],f["all"]
    result=core.original(model,fit)
    obs=model.observations
    direction=model.group_design[:,0]*(obs.times_s-model.group_time_center_s)
    prediction=result["orbit"]+result["correction"][:,None]
    h=1e-4
    values=[core.likelihood(obs.measured_hz,prediction+step*direction[:,None],
                           result["visible"],model.score).nll for step in (-h,h)]
    derivative=(values[1]-values[0])/(2*h)
    assert result["row"]["differential_drift_score_per_hz_s"][0]==pytest.approx(derivative,abs=1e-8)


def test_rejects_c_objective_altered_bank_and_changed_original_objective(models):
    m,f=models
    original=m["low"]
    m["low"]=SimpleNamespace(prior=m["all"].prior,score=m["all"].score,bank=m["all"].bank)
    with pytest.raises(ValueError,match="Original B"):
        core.diagnose(m,f)
    m["low"]=original
    original.bank=replace(original.bank,numbers=original.bank.numbers+1)
    with pytest.raises(ValueError,match="shared candidate bank"):
        core.diagnose(m,f)
    original.bank=m["all"].bank
    f["all"]["objective"]+=1
    with pytest.raises(ValueError,match="replay failed"):
        core.diagnose(m,f)


def test_original_likelihood_port_must_be_exact_b_function(models):
    m,f=models
    m["all"].base.likelihood_port=lambda *a:None
    with pytest.raises(ValueError,match="Original B"):
        core.diagnose(m,f)
