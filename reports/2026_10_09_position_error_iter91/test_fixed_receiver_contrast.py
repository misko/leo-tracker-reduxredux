"""Production B7 hooks on synthetic orbits, without a recording fit."""

from copy import copy
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from fixed_receiver_contrast import FixedReceiverContrast, fit

from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.hard60_slope_prior import SlopePrior
from tests.analysis.test_hard60_joint import setup


def model():
    base, old = setup()
    knots = old.initial_clock.reshape(2, -1) @ old.null.T
    centers = np.full(len(base.bank.numbers), base.observations.time_center_s)
    return SlopePrior(base, old.nodes, knots, centers, 0.5)


def state(base):
    vector = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    clock = base.initial_clock.copy()
    clock[base.slope_slice] = [2, -1]
    clock[-2:] = [20, -10]
    return vector, clock


def test_zero_control_is_exact_b7_and_adds_no_dimensions_or_penalties():
    original = model()
    wrapped = FixedReceiverContrast(original, original.bank.numbers, [0, 0, 0])
    vector, clock = state(original)
    expected, actual = original.evaluate_joint(vector, clock), wrapped.evaluate_joint(vector, clock)
    assert actual[0] == expected[0]
    np.testing.assert_array_equal(actual[1], expected[1])
    np.testing.assert_array_equal(actual[2], expected[2])
    np.testing.assert_array_equal(actual[3].residual_hz, expected[3].residual_hz)
    assert wrapped.size == original.size
    assert wrapped.precision is original.precision
    assert len(wrapped.initial_clock) == len(original.initial_clock)


def test_unsigned_receiver_dtype_preserves_sign_and_invalid_receiver_fails():
    original = model()
    original.observations = copy(original.observations)
    object.__setattr__(
        original.observations, "receiver", original.observations.receiver.astype(np.uint8)
    )
    wrapped = FixedReceiverContrast(original, original.bank.numbers, [12, -5, -7])
    np.testing.assert_array_equal(wrapped.receiver_sign[original.observations.receiver == 0], -1)
    np.testing.assert_array_equal(wrapped.receiver_sign[original.observations.receiver == 1], 1)
    invalid = original.observations.receiver.copy()
    invalid[0] = 2
    object.__setattr__(original.observations, "receiver", invalid)
    with pytest.raises(ValueError, match="RX0 or RX1"):
        FixedReceiverContrast(original, original.bank.numbers, [12, -5, -7])


def test_fixed_correction_gradients_and_objective_accounting():
    original = model()
    wrapped = FixedReceiverContrast(original, original.bank.numbers, [12, -5, -7])
    vector, clock = state(original)
    value, gradient, extra, terms = wrapped.evaluate_joint(vector, clock)
    relative = wrapped.basis @ vector[8:]
    penalty = 0.5 * (vector[7] / wrapped.score.common_sigma_s) ** 2
    penalty += 0.5 * np.sum((relative / wrapped.score.relative_sigma_s) ** 2)
    penalty += 0.5 * clock @ wrapped.precision @ clock
    assert value == pytest.approx(terms.nll + penalty, abs=1e-12)
    point = np.r_[vector, clock]
    numeric = []
    for delta in np.eye(len(point)) * 1e-4:
        plus, minus = point + delta, point - delta
        numeric.append(
            (
                wrapped.evaluate_joint(plus[: len(vector)], plus[len(vector) :])[0]
                - wrapped.evaluate_joint(minus[: len(vector)], minus[len(vector) :])[0]
            )
            / 2e-4
        )
    np.testing.assert_allclose(np.r_[gradient, extra], numeric, atol=2e-4, rtol=2e-4)
    assert not wrapped.contrasts_hz.flags.writeable


def test_receiver_exchange_and_contrast_sign_symmetry():
    original = model()
    vector, clock = state(original)
    swapped_obs = replace(original.observations, receiver=1 - original.observations.receiver)
    # The fixed baseline follows each original observation; swap receiver-labeled
    # affine/smooth/RF parameters and recreate the existing smooth null basis.
    base = Hard60Objective(
        swapped_obs,
        original.bank,
        original.prior,
        original.score,
        receiver_baseline_hz=original.baseline,
    )
    swapped = SlopePrior(
        base, original.nodes, np.zeros((2, len(original.nodes))), original.centers_s, 0.5
    )
    vector2 = vector.copy()
    vector2[2:6] = vector[[4, 5, 2, 3]]
    clock2 = clock.copy()
    block = original.smooth_clock_count // 2
    clock2[: original.smooth_clock_count] = np.r_[clock[block : 2 * block], clock[:block]]
    clock2[-2:] = clock[-2:][::-1]
    wrapped = FixedReceiverContrast(original, original.bank.numbers, [12, -5, -7])
    exchanged = FixedReceiverContrast(swapped, swapped.bank.numbers, [-12, 5, 7])
    expected, actual = (
        wrapped.evaluate_joint(vector, clock),
        exchanged.evaluate_joint(vector2, clock2),
    )
    assert actual[0] == pytest.approx(expected[0], abs=1e-10)
    np.testing.assert_allclose(actual[3].residual_hz, expected[3].residual_hz, atol=1e-10)
    np.testing.assert_allclose(actual[1][:2], expected[1][:2], atol=1e-10)


def test_existing_fitter_c0_locks_without_running_optimizer(monkeypatch):
    import leo.analysis.hard60_dynamic_rf as module

    def evaluate_initial(fun, initial, **kwargs):
        assert kwargs["method"] == "SLSQP"
        assert kwargs["bounds"].lb[-2:].tolist() == [0, 0]
        assert kwargs["bounds"].ub[-2:].tolist() == [0, 0]
        fun(initial)
        return SimpleNamespace(success=True)

    monkeypatch.setattr(module, "minimize", evaluate_initial)
    original = model()
    wrapped = FixedReceiverContrast(original, original.bank.numbers, [12, -5, -7])
    vector, clock = state(original)
    result = fit(wrapped, vector, arm="zero-c", clock_seed=clock, maximum_seconds=1)
    assert result["vector"][6] == 0
    np.testing.assert_array_equal(result["rf_drift_coefficients"], [0, 0])
    assert result["objective"] == pytest.approx(
        wrapped.evaluate_joint(result["vector"], result["clock_coefficients"])[0], abs=1e-12
    )
    assert result["converged"] == (result["stationarity"] <= 0.001)


@pytest.mark.parametrize(
    "ids,values",
    [([999], [0]), ([100, 100], [0, 0]), ([100, 101], [1, 1]), ([100], [float("nan")])],
)
def test_invalid_frozen_corrections_rejected(ids, values):
    with pytest.raises(ValueError):
        FixedReceiverContrast(model(), ids, values)
