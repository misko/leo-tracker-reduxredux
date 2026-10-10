import copy

import numpy as np
import pytest
from measurement import PERIOD_HZ, shared_starts, substitute


def rows():
    return [
        {
            "window_id": "a",
            "status": "complete",
            "result": {
                "parity": "passed",
                "scorer_kind": "original-python-conditioned-scorer",
                "original_passed": True,
                "baseline_cfo_hz": 500000,
                "logparabola_cfo_hz": 500000 - PERIOD_HZ + 100,
                "newton_cfo_hz": 500090,
                "changes": {
                    "logparabola": {"circular_hz": 100, "wrap_count": -1},
                    "newton": {"circular_hz": 90, "wrap_count": 0},
                },
            },
        }
    ]


def test_branch_preservation_and_wrapped_residual_gradient_equivalence():
    out = substitute(["a"], [500000], rows(), "logparabola")
    assert out["measured_hz"] == pytest.approx([500100], abs=1e-7, rel=0)
    assert out["representation_wraps"].tolist() == [-1]
    direct = rows()[0]["result"]["logparabola_cfo_hz"]
    predictions = np.array([499900.0, 500300.0, 503000.0])

    def residual(measured):
        return (measured - predictions + PERIOD_HZ / 2) % PERIOD_HZ - PERIOD_HZ / 2

    np.testing.assert_allclose(residual(direct), residual(out["measured_hz"][0]), atol=1e-7, rtol=0)
    # Away from a wrap seam, Gaussian frequency gradient and NLL are identical.
    np.testing.assert_allclose(
        residual(direct) / 125**2, residual(out["measured_hz"][0]) / 125**2, atol=1e-10, rtol=0
    )
    assert substitute(["a"], [500000], rows(), "original")["measured_hz"].tolist() == [500000]


@pytest.mark.parametrize("kind", ["missing", "duplicate", "failure", "frequency", "receipt"])
def test_no_imputation_or_incomplete_comparison(kind):
    data = copy.deepcopy(rows())
    if kind == "missing":
        data = []
    if kind == "duplicate":
        data += copy.deepcopy(data)
    if kind == "failure":
        data[0]["status"] = "budget-exhausted"
    if kind == "frequency":
        data[0]["result"]["baseline_cfo_hz"] += 1
    if kind == "receipt":
        data[0]["result"]["changes"]["newton"]["wrap_count"] = 1
    with pytest.raises(ValueError):
        substitute(["a"], [500000], data, "original")


def test_six_starts_identical_except_explicit_c_locks_independent_copies():
    v, c = np.arange(10.0, dtype=float), np.arange(8.0, dtype=float)
    starts = shared_starts(v, c, rf_clock_columns=[3, 4])
    for (_variant, arm), state in starts.items():
        expected_v, expected_c = v.copy(), c.copy()
        if arm == "zero-c":
            expected_v[6], expected_c[[3, 4]] = 0, 0
        np.testing.assert_array_equal(state["vector"], expected_v)
        np.testing.assert_array_equal(state["clock_coefficients"], expected_c)
    starts[("newton", "fitted-c")]["vector"][0] = 999
    assert starts[("original", "fitted-c")]["vector"][0] == v[0] == 0


def test_actual_b7_likelihood_wrap_score_and_prediction_gradient():
    from types import SimpleNamespace

    from leo.analysis.hard60_score import likelihood

    score = SimpleNamespace(sigma_hz=125.0, detection_budget=1.0, clutter_rate=0.1)
    predictions = np.array([[499900.0, 500300.0, 503000.0]])
    visible = np.ones_like(predictions, dtype=bool)
    original_branch = substitute(["a"], [500000], rows(), "logparabola")["measured_hz"]
    raw_branch = np.array([rows()[0]["result"]["logparabola_cfo_hz"]])
    a, b = (
        likelihood(value, predictions, visible, score) for value in (original_branch, raw_branch)
    )
    assert a.nll == pytest.approx(b.nll, rel=0, abs=1e-10)
    np.testing.assert_allclose(a.prediction_gradient, b.prediction_gradient, rtol=0, atol=1e-10)


def test_measurement_model_does_not_mutate_original_or_other_arrays():
    from dataclasses import dataclass
    from types import SimpleNamespace

    from measurement import clone_measurement_model

    from leo.analysis.hard60_score import likelihood

    @dataclass
    class Observations:
        measured_hz: np.ndarray
        rf_hz: np.ndarray
        times_s: np.ndarray
        window_ids: tuple

    observations = Observations(np.array([500000.0]), np.array([1e10]), np.array([4.0]), ("a",))
    score = SimpleNamespace(sigma_hz=125.0, detection_budget=1.0, clutter_rate=0.1)
    original = SimpleNamespace(observations=observations, design=np.ones((1, 5)), score=score)
    predictions = np.array([[499900.0, 500300.0, 503000.0]])
    visible = np.ones_like(predictions, dtype=bool)

    def cost(model):
        return likelihood(model.observations.measured_hz, predictions, visible, model.score).nll

    before = cost(original)
    candidate = clone_measurement_model(original, [500100.0])
    assert cost(original) == before
    assert cost(candidate) != before
    assert candidate.observations is not observations
    assert not np.shares_memory(candidate.observations.measured_hz, observations.measured_hz)
    np.testing.assert_array_equal(candidate.observations.rf_hz, observations.rf_hz)
    np.testing.assert_array_equal(candidate.observations.times_s, observations.times_s)
    candidate.design[0, 0] = 9
    candidate.observations.rf_hz[0] = 0
    assert original.design[0, 0] == 1 and original.observations.rf_hz[0] == 1e10
    original.cached_terms = None
    with pytest.raises(ValueError, match="unreviewed"):
        clone_measurement_model(original, [500100.0])
