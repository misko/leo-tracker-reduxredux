from types import SimpleNamespace

import numpy as np
import pytest
from independent_rx_fit import (
    IndependentRXObjective,
    capture_clock,
    continuous_to_lines,
    fit_independent_rx,
)
from independent_rx_run import child_initializer


def data_fixture(captures=2):
    return SimpleNamespace(
        child_sessions=tuple(f"scan{index}" for index in range(captures)),
        child_origins_utc_ns=np.arange(captures) * 300_000_000_000,
        origin_utc_ns=0, reference_time_s=300.0, numbers=np.array([101, 102]),
        times=np.concatenate([np.repeat([100., 150., 200.], 2) + 300 * index
                              for index in range(captures)]),
        capture_index=np.repeat(np.arange(captures), 6),
        receiver=np.tile([0, 1], 3 * captures), group=np.arange(6 * captures),
    )


class FakePlan:
    def __init__(self, data, satellites):
        self.matrix = np.zeros((len(data.times) * len(satellites), 6 + len(data.numbers)))

    def predict(self, parameters):
        return self.matrix @ parameters, np.ones(len(self.matrix), bool), self

    def transpose_multiply(self, weights):
        return self.matrix.T @ weights


class QuadraticLikelihood:
    def __init__(self, target):
        self.target = target

    def evaluate(self, prediction, visible, **kwargs):
        residual = prediction - self.target
        return {"total_log_likelihood": -0.5 * np.sum(residual**2),
                "prediction_gradient": -residual}


class GradientPlan(FakePlan):
    def __init__(self, data, satellites):
        super().__init__(data, satellites)
        self.matrix = np.random.default_rng(12).normal(size=self.matrix.shape)


def test_independent_line_derivatives_and_no_cross_scan_coupling():
    data = data_fixture()
    objective = IndependentRXObjective(data, np.zeros(8), np.zeros((2, 2, 2)), [0, 1],
                                       QuadraticLikelihood(np.ones((12, 2))),
                                       plan_factory=GradientPlan)
    vector = objective.initial_vector.copy()
    vector[2:10] = np.arange(8) / 1000
    vector[-2:] = [0.2, -0.1]
    _, gradient = objective.evaluate(vector)
    for index in range(len(vector)):
        plus, minus = vector.copy(), vector.copy()
        plus[index] += 1e-6
        minus[index] -= 1e-6
        numerical = (objective.evaluate(plus)[0] - objective.evaluate(minus)[0]) / 2e-6
        np.testing.assert_allclose(gradient[index], numerical, atol=1e-5, rtol=1e-6)
    _, delta, indices = capture_clock(data)
    lines = np.zeros((4, 2))
    lines[2, 1] = 17
    offsets = lines[indices, 0] + lines[indices, 1] * delta
    np.testing.assert_array_equal(offsets[:6], 0)
    np.testing.assert_array_equal(offsets[data.receiver == 1], 0)
    np.testing.assert_array_equal(offsets[[6, 8, 10]], [-850, 0, 850])


def test_continuous_line_conversion_reproduces_prediction():
    data = data_fixture(4)
    parameters = np.array([1, 2, 100, 3, -500, -2, 0, 0])
    lines = continuous_to_lines(data, parameters)
    _, delta, indices = capture_clock(data)
    actual = lines.reshape(-1, 2)[indices]
    expected = parameters[2 + 2 * data.receiver] + parameters[3 + 2 * data.receiver] * (
        data.times - data.reference_time_s
    )
    np.testing.assert_allclose(actual[:, 0] + actual[:, 1] * delta, expected)


def test_fit_recovers_opposite_slopes_and_independent_intercepts():
    data = data_fixture()
    truth = np.array([[[200., 12.], [-300., -18.]], [[900., -9.], [100., 21.]]])
    _, delta, indices = capture_clock(data)
    row_lines = truth.reshape(-1, 2)[indices]
    target = np.repeat((row_lines[:, 0] + row_lines[:, 1] * delta)[:, None], 2, axis=1)
    fitted = fit_independent_rx(data, np.zeros(8), np.zeros((2, 2, 2)), [0, 1],
                                QuadraticLikelihood(target), plan_factory=FakePlan)
    np.testing.assert_allclose(fitted["rx_lines_hz_hz_s"], truth, atol=1e-5)
    assert fitted["objective"] <= fitted["initial_objective"]
    assert fitted["free_parameter_count"] == 12
    assert fitted["model_penalty"]["extra_rx_parameters"] == 4
    np.testing.assert_array_equal(fitted["parameters"][2:6], 0)


def test_deadline_retains_initial_state_without_convergence():
    data = data_fixture()
    ticks = iter([0., 20., 21.])
    fitted = fit_independent_rx(data, np.zeros(8), np.zeros((2, 2, 2)), [0, 1],
                                QuadraticLikelihood(np.ones((12, 2))), plan_factory=FakePlan,
                                clock=lambda: next(ticks), budget_s=1)
    assert not fitted["success"]
    assert fitted["convergence_reason"] == "budget_exhausted"
    assert fitted["objective"] == fitted["initial_objective"]


def test_children_preserve_different_slopes_without_averaging():
    data = data_fixture()
    receipts = {
        session: {"unit": {"session_ids": [session], "size": 1},
                  "fit": {"rx_initial": [0, 0, 10, 2 + index, 20, -5 - index],
                          "rough": {"position_km": [index, -index]}}}
        for index, session in enumerate(data.child_sessions)
    }
    _, lines = child_initializer(data, receipts)
    np.testing.assert_array_equal(lines[:, :, 1], [[2, -5], [3, -6]])


def test_invalid_slope_rejected():
    data = data_fixture()
    lines = np.zeros((2, 2, 2))
    lines[1, 0, 1] = 51
    with pytest.raises(ValueError, match="initializer"):
        IndependentRXObjective(data, np.zeros(8), lines, [0, 1], None)


def test_nonterminal_best_cannot_inherit_optimizer_success():
    def minimizer(function, initial, **kwargs):
        candidate = initial.copy()
        candidate[2] = 0.001
        function(candidate)
        return SimpleNamespace(x=initial, success=True, message="terminal success")

    data = data_fixture()
    fitted = fit_independent_rx(data, np.zeros(8), np.zeros((2, 2, 2)), [0, 1],
                                QuadraticLikelihood(np.ones((12, 2))), plan_factory=FakePlan,
                                minimizer=minimizer)
    assert not fitted["success"]
    assert fitted["convergence_reason"] == "best_retained_nonterminal"


@pytest.mark.parametrize("captures", [1, 2, 4])
def test_each_scan_has_four_free_rx_parameters_and_unbounded_intercepts(captures):
    data = data_fixture(captures)
    lines = np.zeros((captures, 2, 2))
    lines[:, :, 0] = 500_000
    objective = IndependentRXObjective(data, np.zeros(8), lines, [0, 1], None,
                                       plan_factory=FakePlan)
    assert len(objective.initial_vector) == 2 + 4 * captures + 2
    assert objective.bounds[2:2 + 4 * captures:2] == [(None, None)] * (2 * captures)
    assert objective.bounds[3:2 + 4 * captures:2] == [(-5.0, 5.0)] * (2 * captures)
