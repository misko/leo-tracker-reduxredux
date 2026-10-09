import runpy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import leo.analysis.hard60_score as actual
from leo.analysis.hard60_score import likelihood
from leo.application.hard60_runner import HARD60_SCORE

driver = runpy.run_path(str(Path(__file__).with_name("run.py")))


def test_normalized_decomposition_matches_actual_likelihood():
    measured = np.array([0.0, 20.0])
    prediction = np.array([[1.0, 100.0, 500.0], [10.0, 200.0, 300.0]])
    for visible in (np.ones((2, 3), bool), np.array([[True, False, False], [False, True, True]])):
        a, b = driver["decomposition"](measured, prediction, visible, HARD60_SCORE)
        np.testing.assert_allclose(
            (a + b).sum(), likelihood(measured, prediction, visible, HARD60_SCORE).nll,
            atol=1e-13, rtol=0
        )


def fixture():
    base = np.zeros(9)
    plus, minus = base.copy(), base.copy()
    plus[7], minus[7] = 1e-5, -1e-5
    trials = [
        dict(kind="curvature", column=5, sign=sign, vector=v.tolist(), objective=1.0)
        for sign, v in [(1, plus), (-1, minus)]
    ]
    trials += [
        dict(kind="newton", damping=d, vector=base.tolist(), objective=1.0)
        for d in [1.0, 0.5, 0.25]
    ]
    fit = dict(initial_vector=base.tolist(), initial_objective=1.0, trials=trials)
    return dict(
        regions={
            "direct107:synthetic": dict(
                recovery=dict(result=dict(prefit_qualification=dict(fit=fit)))
            )
        }
    )


def test_six_saved_states_exact_identity_and_no_synthetic_new_seed():
    receipt = fixture()
    chosen = driver["states"](receipt)
    assert len(chosen) == 6
    assert chosen[1][1][7] == 1e-5 and chosen[2][1][7] == -1e-5
    receipt["regions"]["direct107:synthetic"]["recovery"]["result"]["prefit_qualification"]["fit"][
        "trials"
    ][0]["vector"][2] = 1
    with pytest.raises(AssertionError):
        driver["states"](receipt)


def test_budget_guard_prevents_any_model_call():
    # evaluate binding is accessed before loop; provide a method without executing it.
    class Model:
        def evaluate(self, vector):
            raise AssertionError("must not execute")

    Model.evaluate.__globals__["predict_orbits"] = lambda *_: None
    result = driver["replay"](Model(), [("base", [0] * 9, 1.0)], clock=lambda: 121.0, begun=0.0)
    assert result["status"] == "budget-exhausted"
    assert result["full_calls"] == result["fixed_calls"] == 0


def test_successful_real_objective_nonzero_receiver_c_and_partial_failure(monkeypatch):
    model = actual.Hard60Objective.__new__(actual.Hard60Objective)
    model.observations = SimpleNamespace(
        times_s=np.array([0.0, 0.1]), measured_hz=np.array([40.0, 80.0])
    )
    model.bank = SimpleNamespace(nodes_s=np.array([-10.0, 10.0]))
    model.prior = None
    model.score = HARD60_SCORE
    model.basis = np.array([[1.0], [-1.0], [0.0]])
    model.design = np.array([[1.0, 0.1, 0.0, 0.0, 2.0], [0.0, 0.0, 1.0, 0.1, 3.0]])
    model.baseline = np.array([50.0, -25.0])

    def predictor(bank, obs, prior, point, shifts):
        prediction = np.array([[10.0, 120.0, 500.0], [20.0, 100.0, 400.0]]) + shifts
        return prediction, np.ones((2, 3), bool), np.zeros((2, 3, 2)), np.ones((2, 3))

    monkeypatch.setattr(actual, "predict_orbits", predictor)
    base = np.array([0.0, 0.0, 15.0, 1.0, -10.0, 2.0, 3.0, 0.2, 0.1])
    vectors = [base.copy() for _ in range(6)]
    vectors[1][7] += 1e-5
    vectors[2][7] -= 1e-5
    names = ["base", "timing-1", "timing--1", "newton-1.0", "newton-0.5", "newton-0.25"]
    chosen = [(name, v, model.evaluate(v)[0]) for name, v in zip(names, vectors, strict=True)]
    result = driver["replay"](model, chosen)
    assert result["status"] == "complete"
    assert result["full_calls"] == result["fixed_calls"] == 6
    assert result["prediction_timing_derivative_audit"]["maximum_absolute_error_stable"] < 1e-8
    progress = {}
    bad = list(chosen)
    bad[1] = (bad[1][0], bad[1][1], bad[1][2] + 1)
    with pytest.raises(AssertionError):
        driver["replay"](model, bad, progress=progress)
    assert len(progress["rows"]) == 1
    assert progress["full_calls"] == 2 and progress["fixed_calls"] == 1
