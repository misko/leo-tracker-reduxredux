import importlib.util
from pathlib import Path
from types import MethodType, SimpleNamespace

import numpy as np
import pytest

import leo.analysis.hard60_satellite_correction as production
from leo.application.hard60_runner import HARD60_SCORE

spec = importlib.util.spec_from_file_location(
    "objective109", Path(__file__).with_name("objective.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(monkeypatch):
    rng = np.random.default_rng(91)
    spatial = rng.normal(size=(4, 3, 2))
    timing = rng.normal(size=(4, 3))

    def orbit(bank, obs, prior, xy, shifts):
        prediction = np.einsum("nki,i->nk", spatial, xy) + timing * shifts
        return prediction, np.ones((4, 3), bool), spatial, timing

    monkeypatch.setattr(module, "predict_orbits", orbit)
    monkeypatch.setattr(production, "predict_orbits", orbit)
    basis = np.array([[1.0], [-1.0], [0.0]])
    base = SimpleNamespace(
        observations=SimpleNamespace(
            times_s=np.arange(4.0), measured_hz=np.array([0.0, 20.0, 40.0, 60.0])
        ),
        bank=None,
        prior=None,
        score=HARD60_SCORE,
        basis=basis,
        size=9,
        design=rng.normal(size=(4, 5)),
        baseline=np.arange(4.0),
        clock_design=rng.normal(size=(4, 6)),
        precision=np.eye(6) / 3,
        satellite_basis=np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, -1.0]]),
        offset_slice=slice(0, 2),
        slope_slice=slice(2, 4),
        delta_time=rng.normal(size=(4, 3)),
    )
    base.physical_corrections = MethodType(
        production.SatelliteCorrection.physical_corrections, base
    )
    base.evaluate_joint = MethodType(production.SatelliteCorrection.evaluate_joint, base)
    return base, rng.normal(size=9), rng.normal(size=6)


def test_zero_exact_production_and_metadata(monkeypatch):
    base, vector, clock = fixture(monkeypatch)
    objective = module.PersistenceObjective(
        base, [2, 0, 3, 1], np.array([True, False, True, False]), rho=0
    )
    actual, expected = objective.evaluate_joint(vector, clock), base.evaluate_joint(vector, clock)
    assert actual[0] == expected[0]
    np.testing.assert_array_equal(actual[1], expected[1])
    np.testing.assert_array_equal(actual[2], expected[2])
    assert objective.precision is base.precision


def test_positive_full_physical_clock_gradient(monkeypatch):
    base, vector, clock = fixture(monkeypatch)
    objective = module.PersistenceObjective(
        base, [2, 0, 3, 1], np.array([True, False, True, False]), rho=0.6
    )
    value, gradient, nuisance, terms = objective.evaluate_joint(vector, clock)
    assert np.isfinite(value)
    np.testing.assert_allclose(terms.responsibilities.sum(axis=1) + terms.clutter_probability, 1)
    for block, analytical in ((vector, gradient), (clock, nuisance)):
        for i in range(len(block)):
            old = block[i]
            block[i] = old + 1e-5
            plus = objective.evaluate_joint(vector, clock)[0]
            block[i] = old - 1e-5
            minus = objective.evaluate_joint(vector, clock)[0]
            block[i] = old
            assert (plus - minus) / 2e-5 == pytest.approx(analytical[i], abs=1e-8)


def test_c0_locks_and_invalid_packing(monkeypatch):
    base, vector, clock = fixture(monkeypatch)
    vector[6], clock[-2:] = 0, 0
    module.PersistenceObjective.assert_zero_c(vector, clock)
    clock[-1] = 1
    with pytest.raises(ValueError):
        module.PersistenceObjective.assert_zero_c(vector, clock)
    with pytest.raises(ValueError):
        module.PersistenceObjective(base, [0, 0, 2, 3], np.ones(4, bool), rho=0.6)
