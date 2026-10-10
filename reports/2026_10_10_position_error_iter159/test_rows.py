"""Actual joint mixture/prior algebra with a deterministic synthetic orbit port."""
import numpy as np
import pytest
import copy
from dataclasses import replace

from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, PositionScore, RegionalPrior
from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.hard60_slope_prior import SlopePrior
from leo.analysis.hard60_bounded_fit import _Problem
import leo.analysis.hard60_satellite_correction as production
from rows import RowObjective, ROW_ARRAYS, prior_terms


def setup(monkeypatch):
    times=np.array([0.,1.,3.,7.,9.,10.])
    observations=PositionObservations(tuple(map(str,range(6))),times,
        np.array([11.,24.,48.,-20.,10.,90.]),np.array([10.,10.,11.,12.,12.,12.])*1e9,
        np.array([0,1,0,1,0,1]),np.arange(6),np.ones(6))
    bank=PositionOrbitBank(np.array([1,2,3]),np.array([-21.,31.]),np.zeros((3,2,3)),np.zeros((3,2,3)))
    base=Hard60Objective(observations,bank,RegionalPrior(latitude_deg=12.,longitude_deg=34.),
                        PositionScore('V16',125.,1.,.5,2.,1.))
    model=SlopePrior(base,np.linspace(0,10,4),np.zeros((2,4)),np.array([3.,4.,5.]),.5)
    def orbit(bank,obs,prior,point,shifts,**kwargs):
        n,k=len(obs.times_s),len(bank.numbers)
        prediction=obs.times_s[:,None]+np.arange(k)[None,:]*50+point[0]*2+point[1]*3+shifts[None,:]*4
        spatial=np.broadcast_to(np.array([2.,3.]),(n,k,2)).copy()
        return prediction,np.ones((n,k),bool),spatial,np.full((n,k),4.)
    monkeypatch.setattr(production,'predict_orbits',orbit)
    return model


def test_joint_decomposition_design_and_original_unchanged(monkeypatch):
    model=setup(monkeypatch)
    before={name:getattr(model,name).copy() for name in ROW_ARRAYS}
    folds=[RowObjective(model,np.array([0,1,2])),RowObjective(model,np.array([3,4,5]))]
    v=np.linspace(-.1,.2,model.size);c=np.linspace(-2,3,len(model.initial_clock))
    full=model.evaluate_joint(v,c);parts=[f.evaluate_joint(v,c) for f in folds]
    prior=prior_terms(model,v,c)
    for i in range(3):np.testing.assert_allclose(parts[0][i]+parts[1][i]-prior[i],full[i],atol=1e-10,rtol=1e-12)
    assert parts[0][3].nll+parts[1][3].nll==pytest.approx(full[3].nll,abs=1e-10)
    for f,part in zip(folds,parts):
        assert f.observations is model.observations
        assert f.selected_observations.time_center_s != model.observations.time_center_s
        assert f.selected_observations.rf_center_hz != model.observations.rf_center_hz
        for name in ('responsibilities','prediction_gradient','residual_hz'):
            np.testing.assert_allclose(getattr(part[3],name),getattr(full[3],name)[f.rows])
        for name in ROW_ARRAYS:
            np.testing.assert_array_equal(getattr(f._delegate,name),before[name][f.rows])
            np.testing.assert_array_equal(getattr(model,name),before[name])
        assert f.precision is model.precision and f.bank is model.bank


def test_constraints_use_full_support_times(monkeypatch):
    model=setup(monkeypatch);fold=RowObjective(model,np.array([1,2,3,4]))
    v=np.zeros(model.size)
    original=_Problem(model,v);restricted=_Problem(fold,v)
    assert (original.coverage_min,original.coverage_max)==(restricted.coverage_min,restricted.coverage_max)
    # A raw sliced model would have larger coverage margins, even when +/-20 clip matches.
    assert _Problem(fold._delegate,v).coverage_min != original.coverage_min
    np.testing.assert_array_equal(original.constraints(v),restricted.constraints(v))


@pytest.mark.parametrize('rows',[[],[2,1],[1,1],[0,6],[-1,0],[0.,1.],[True,False],np.array([2,1],dtype=np.uint64)])
def test_invalid_rows_rejected(monkeypatch,rows):
    model=setup(monkeypatch)
    with pytest.raises(ValueError):RowObjective(model,rows)


def test_joint_only_port_prevents_accidental_full_data_evaluation(monkeypatch):
    fold=RowObjective(setup(monkeypatch),[0,1])
    with pytest.raises(TypeError):fold.evaluate(np.zeros(fold.size))
    with pytest.raises(AttributeError):fold.physical_corrections(np.zeros(len(fold.initial_clock)))


def test_held_measurements_cannot_change_training_value_or_gradients(monkeypatch):
    full=setup(monkeypatch);changed=copy.copy(full)
    measured=full.observations.measured_hz.copy();measured[3:]+=10000
    changed.observations=replace(full.observations,measured_hz=measured)
    vector=np.zeros(full.size);clock=np.zeros(len(full.initial_clock))
    original=RowObjective(full,[0,1,2]).evaluate_joint(vector,clock)
    perturbed=RowObjective(changed,[0,1,2]).evaluate_joint(vector,clock)
    for i in range(3):np.testing.assert_array_equal(original[i],perturbed[i])
    assert RowObjective(full,[3,4,5]).evaluate_joint(vector,clock)[3].nll != RowObjective(changed,[3,4,5]).evaluate_joint(vector,clock)[3].nll
