from collections import Counter
from types import SimpleNamespace

import numpy as np

from leo.analysis.localization_v3 import family_cavity

from reports.ALGO08.v3.held_family_fixed_state import FixedPhase, binding, state_readout


def test_reads_exact_same_final_native_result_once():
    calls = []

    def calculate(point):
        calls.append(point)
        return {"coefficient": np.array([1., 2.])}

    p = SimpleNamespace(calculate=calculate)
    p.state = lambda point: p.calculate(point)
    counts = Counter()
    state, readout = state_readout(p, np.array([2., 3.]), counts)
    assert len(calls) == counts["saved_native_endpoint"] == 1
    assert state is readout and p.calculate is calculate


def test_missing_state_calculation_defers_to_original():
    original = lambda point: {"x": point}
    p = SimpleNamespace(calculate=original, state=lambda point: "separate-state")
    counts = Counter()
    point = np.array([2., 3.])
    state, readout = state_readout(p, point, counts)
    assert state == "separate-state" and readout["x"] is point
    assert counts == {"ordinary_endpoint": 1}


def test_exact_phase_reuse_and_prior_lifetime():
    counts = Counter()
    fixed = FixedPhase(counts)
    covariance = np.eye(2)
    calls = []

    def geometry(phase):
        calls.append(phase)
        return np.array([phase, phase]), np.eye(2), np.ones(2)

    def predict(raw, design):
        return raw + fixed.prior_root(covariance) @ np.ones(2)

    values = mean = np.ones(2)
    a = fixed.evaluate(0., geometry, values, mean, predict)
    b = fixed.evaluate(0., geometry, values, mean, predict)
    assert all(x is y for x, y in zip(a, b))
    assert all(x is y for x, y in zip(a[:3], fixed.final_geometry(0., geometry)))
    fixed.evaluate(-0., geometry, values, mean, predict)
    assert len(calls) == 2
    assert counts == dict(prior_factorizations=1, reused_prior_factorizations=1,
                          dynamic_predictions=2, reused_predictions=1, reused_final_geometry=1)


def test_original_release_binding_is_private_and_restored():
    original = family_cavity.family_data, family_cavity.candidate_prediction
    with binding() as counts:
        assert not counts["unsupported"]
        assert all(a is not b for a, b in zip(original, (family_cavity.family_data, family_cavity.candidate_prediction)))
    assert original == (family_cavity.family_data, family_cavity.candidate_prediction)
