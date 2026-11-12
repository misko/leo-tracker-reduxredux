from copy import deepcopy

import numpy as np
import pytest
from scipy.optimize import OptimizeResult

from leo.analysis.localization_v3 import position
from leo.analysis.localization_v5 import annotation_fallback as fallback
from leo.analysis.localization_v5 import annotation_training as primary
from leo.contracts.localization_v5 import ANNOTATION_FALLBACK_POLICY, annotation_training_policy


class Problem:
    def __init__(self):
        self.lower, self.upper = np.array([-1., -2.]), np.array([2., 1.])
        self.keep = np.array([True, False, True])
        self.calls, self.calculations = [], []

    def residual(self, at):
        self.calls.append(at.copy())
        return np.r_[(at - [.2, -.3]) * [2., 3.], 4.]

    def calculate(self, at):
        self.calculations.append(at.copy())
        return dict(conditional_residual_hz=np.array([3., 99., 4.]),
                    normalization_constant=17., negative_twice_elbo=123.)


def assert_equal(actual, expected):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            assert_equal(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for observed, wanted in zip(actual, expected, strict=True):
            assert_equal(observed, wanted)
    elif isinstance(expected, np.ndarray):
        np.testing.assert_array_equal(actual, expected)
    else:
        assert actual == expected


def nonsuccess(objective, start, **kwargs):
    objective(start)
    endpoint = start + [.1, .1]
    score = objective(endpoint)
    return OptimizeResult(x=endpoint, fun=score + max(1., .1 * score), nfev=2, njev=0, nit=0,
                          success=False, status=2, message="ABNORMAL: synthetic",
                          jac=np.ones(2))


def test_success_preserves_every_primary_numerical_field_and_does_not_run_reference(monkeypatch):
    expected = primary.fit(Problem(), [.5, -.7])
    assert expected["converged"] is True
    problem = Problem()

    def forbidden(*args, **kwargs):
        pytest.fail("Successful primary fit must not invoke reference solver")

    monkeypatch.setattr(position, "fit", forbidden)
    result = fallback.fit(problem, [.5, -.7])
    for key, value in expected.items():
        if key not in ("history", "optimizer_policy", "history_kind"):
            assert_equal(result[key], value)
    assert result["evaluations"] == len(problem.calls)
    assert result["final_metadata_calculate_calls"] == len(problem.calculations) == 1
    assert result["reference_fit_completed"] is False
    assert result["fallback"] == dict(attempted=False, completed=False, evaluations=0,
                                      stopped=None, budget_exhausted=False)
    assert result["optimizer_policy"] == fallback.fit.policy == annotation_training_policy(
        ANNOTATION_FALLBACK_POLICY)
    assert result["attempts"][0]["converged"] is True
    for recorded, original in zip(result["history"], expected["history"], strict=True):
        assert_equal({key: recorded[key] for key in original}, original)


@pytest.mark.parametrize("start", [[.5, -.7], [-9., 9.]])
def test_abnormal_primary_runs_full_reference_from_original_start_and_preserves_all_calls(
    monkeypatch, start
):
    reference_problem = Problem()
    reference = position.fit(reference_problem, start, iterations=48)
    problem = Problem()
    original_start = np.array(start)
    lower, upper, keep = problem.lower.copy(), problem.upper.copy(), problem.keep.copy()

    def abnormal(objective, at, **kwargs):
        objective(at)
        endpoint = np.clip(at + [.1, -.1], lower, upper)
        score = objective(endpoint)
        return OptimizeResult(x=endpoint, fun=score + 1., nfev=2, njev=0, nit=0,
                              success=False, status=2, message="ABNORMAL: synthetic",
                              jac=np.ones(2))

    monkeypatch.setattr(primary, "minimize", abnormal)
    result = fallback.fit(problem, original_start)
    for key in reference:
        if key not in ("history", "evaluations"):
            assert_equal(result[key], reference[key])
    assert_equal(result["reference_optimizer_history"], reference["history"])
    assert result["reference_optimizer_history_kind"] == "accepted iterates from original GN"
    assert result["history_kind"] == "all physical residual evaluations across attempts"
    assert result["evaluations"] == len(problem.calls) == 2 + reference["evaluations"]
    assert result["fallback"]["evaluations"] == len(reference_problem.calls)
    assert result["reference_fit_completed"] is result["fallback"]["completed"] is True
    assert result["converged"] is None
    assert result["scipy_result"]["success"] is False
    assert result["scipy_result"]["status"] == 2
    assert result["scipy_result_scope"] == "primary optimizer attempt"
    assert result["score_correction"] is None
    assert result["stationarity"] == dict(
        source="original GN endpoint; stationarity not measured",
        projected_gradient_inf_norm=None, gtol=None, satisfied=None)
    assert result["attempts"][0]["stationarity"]["projected_gradient_inf_norm"] == 1.
    assert result["attempts"][0]["score_correction"]["additional_residual_evaluations"] == 0
    assert result["final_metadata_calculate_calls"] == len(problem.calculations) == 2
    for observed, recorded in zip(problem.calls, result["history"], strict=True):
        np.testing.assert_array_equal(observed, recorded["parameters"])
        assert recorded["score"] == pytest.approx(
            np.r_[(observed - [.2, -.3]) * [2., 3.], 4.] @
            np.r_[(observed - [.2, -.3]) * [2., 3.], 4.])
    for observed, wanted in zip(problem.calls[2:], reference_problem.calls, strict=True):
        np.testing.assert_array_equal(observed, wanted)
    assert len(reference_problem.calls) > len(reference["history"])
    np.testing.assert_array_equal(original_start, start)
    for observed, wanted in ((problem.lower, lower), (problem.upper, upper), (problem.keep, keep)):
        np.testing.assert_array_equal(observed, wanted)
    assert not result["physical_budget_exhausted"]


def test_primary_physical_cap_does_not_shorten_reference_budget(monkeypatch):
    def exhaust(objective, at, **kwargs):
        for _ in range(626):
            objective(at)

    monkeypatch.setattr(primary, "minimize", exhaust)
    original_fit = position.fit
    starts = []

    def observe(problem, start, iterations):
        starts.append(np.array(start))
        assert iterations == 48
        return original_fit(problem, start, iterations=iterations)

    monkeypatch.setattr(position, "fit", observe)
    problem = Problem()
    result = fallback.fit(problem, [.5, -.7])
    assert result["attempts"][0]["evaluations"] == 625
    assert result["attempts"][0]["budget_exhausted"] is True
    assert result["attempts"][0]["scipy_result"] is None
    assert result["budget_exhausted"] is True
    assert result["converged"] is None
    assert result["reference_fit_completed"] is True
    assert result["evaluations"] == len(problem.calls) <= 1250
    np.testing.assert_array_equal(starts, [[.5, -.7]])


def test_full_48_iteration_reference_budget_is_completed_without_claiming_convergence(monkeypatch):
    class SlowProblem(Problem):
        def __init__(self):
            super().__init__()
            self.lower, self.upper = np.array([-1., -1.]), np.array([1000., 1000.])

        def residual(self, at):
            self.calls.append(at.copy())
            return 1e40 * np.exp(-at)

    reference_problem = SlowProblem()
    reference = position.fit(reference_problem, iterations=48)
    assert reference["stopped"] == "iteration_budget"
    assert len(reference["history"]) == 49
    monkeypatch.setattr(primary, "minimize", nonsuccess)
    problem = SlowProblem()
    result = fallback.fit(problem)
    for key in reference:
        if key not in ("history", "evaluations"):
            assert_equal(result[key], reference[key])
    assert_equal(result["reference_optimizer_history"], reference["history"])
    assert result["evaluations"] == len(problem.calls) == reference["evaluations"] + 2
    assert result["reference_fit_completed"] is True
    assert result["converged"] is None
    assert result["stationarity"]["satisfied"] is None
    assert result["budget_exhausted"] is True
    assert result["fallback"]["budget_exhausted"] is True
    assert result["attempts"][0]["budget_exhausted"] is False


def test_both_full_physical_budgets_are_accounted_without_dropping_work(monkeypatch):
    def exhaust(objective, at, **kwargs):
        for _ in range(626):
            objective(at)

    def reference_budget(residual, start, lower, upper, *, iterations):
        assert iterations == 48
        point = np.clip(start, lower, upper)
        for _ in range(625):
            values = residual(point)
        score = float(values @ values)
        return dict(parameters=point, score=score, evaluations=625,
                    history=[dict(parameters=point.copy(), score=score)],
                    stopped="iteration_budget")

    monkeypatch.setattr(primary, "minimize", exhaust)
    monkeypatch.setattr(position, "bounded_gauss_newton", reference_budget)
    problem = Problem()
    result = fallback.fit(problem)
    assert result["evaluations"] == len(result["history"]) == len(problem.calls) == 1250
    assert [row["evaluations"] for row in result["attempts"]] == [625, 625]
    assert all(row["attempt"] == 0 for row in result["history"][:625])
    assert all(row["attempt"] == 1 for row in result["history"][625:])
    assert result["physical_budget_exhausted"] is True
    assert result["reference_fit_completed"] is True
    assert result["converged"] is None
    assert result["final_metadata_calculate_calls"] == len(problem.calculations) == 2


@pytest.mark.parametrize("value", [[], [[1.]], [np.nan], [np.inf], [1e308]])
def test_invalid_reference_residual_is_not_returned_as_a_completed_fallback(monkeypatch, value):
    monkeypatch.setattr(primary, "minimize", nonsuccess)
    problem = Problem()
    residual = problem.residual

    def invalid(at):
        if len(problem.calls) >= 2:
            problem.calls.append(at.copy())
            return value
        return residual(at)

    problem.residual = invalid
    with pytest.raises(ValueError):
        fallback.fit(problem)
    assert len(problem.calls) == 3
    assert len(problem.calculations) == 1


@pytest.mark.parametrize("mode", ["cap", "count", "exception", "nonfinite", "iteration_budget"])
def test_reference_failures_abort_and_iteration_budget_completion_is_not_convergence(
    monkeypatch, mode
):
    monkeypatch.setattr(primary, "minimize", nonsuccess)
    original_fit = position.fit

    def reference(problem, start, iterations):
        if mode == "cap":
            for _ in range(626):
                problem.residual(np.asarray(start))
        if mode == "exception":
            raise ArithmeticError("reference failure")
        result = original_fit(problem, start, iterations=iterations)
        if mode == "count":
            result["evaluations"] += 1
        elif mode == "nonfinite":
            result["negative_twice_elbo"] = np.nan
        elif mode == "iteration_budget":
            result["stopped"] = "iteration_budget"
        return result

    monkeypatch.setattr(position, "fit", reference)
    problem = Problem()
    if mode == "iteration_budget":
        result = fallback.fit(problem)
        assert result["converged"] is None
        assert result["reference_fit_completed"] is True
        assert result["budget_exhausted"] is True
        assert result["fallback"]["stopped"] == "iteration_budget"
        assert result["fallback"]["budget_exhausted"] is True
        assert result["attempts"][0]["budget_exhausted"] is False
        assert result["attempts"][1]["converged"] is None
    else:
        error = {"cap": RuntimeError, "exception": ArithmeticError}.get(mode, ValueError)
        with pytest.raises(error):
            fallback.fit(problem)
        if mode == "cap":
            assert len(problem.calls) == 2 + 625
            assert len(problem.calculations) == 1


@pytest.mark.parametrize("error", [ValueError("invalid primary"), RuntimeError("unknown primary")])
def test_primary_exceptions_propagate_without_reference(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(primary, "minimize", fail)
    with pytest.raises(type(error), match=str(error)):
        fallback.fit(Problem())


def test_result_telemetry_and_policy_are_independent_between_attempts_and_calls(monkeypatch):
    monkeypatch.setattr(primary, "minimize", nonsuccess)
    first = fallback.fit(Problem())
    second = fallback.fit(Problem())
    expected = deepcopy(second)
    first["history"][0]["parameters"][0] = 99.
    first["reference_optimizer_history"][0]["parameters"][0] = 99.
    first["attempts"][0]["scipy_result"]["success"] = True
    first["attempts"][0]["score_correction"]["reason"] = "changed"
    first["optimizer_policy"]["primary"]["options"]["maxiter"] = 1
    assert first["scipy_result"]["success"] is False
    assert first["score_correction"] is None
    assert_equal(second, expected)
    assert fallback.fit.policy == annotation_training_policy(ANNOTATION_FALLBACK_POLICY)


def test_changed_iteration_budget_is_rejected_without_work():
    problem = Problem()
    with pytest.raises(ValueError, match="48 position steps"):
        fallback.fit(problem, iterations=47)
    assert problem.calls == problem.calculations == []
