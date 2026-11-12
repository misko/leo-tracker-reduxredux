from copy import deepcopy

import numpy as np
import pytest
from scipy.optimize import OptimizeResult

from leo.analysis.localization_v5 import annotation_training as training
from leo.contracts.localization_v5 import annotation_training_policy


class QuadraticProblem:
    def __init__(self, target=(0.2, -0.3)):
        self.target = np.asarray(target)
        self.lower, self.upper = np.array([-1.0, -2.0]), np.array([2.0, 1.0])
        self.keep = np.array([True, False, True])
        self.calls, self.calculations = [], []

    def residual(self, at):
        assert np.all(at >= self.lower) and np.all(at <= self.upper)
        self.calls.append(at.copy())
        return np.r_[(at - self.target) * [2.0, 3.0], 4.0]

    def calculate(self, at):
        self.calculations.append(at.copy())
        return dict(conditional_residual_hz=np.array([3.0, 99.0, 4.0]),
                    normalization_constant=17.0, negative_twice_elbo=123.0)


def returned(objective, start, **changes):
    return OptimizeResult(dict(x=start.copy(), fun=objective(start), nfev=1, njev=0,
                               nit=0, success=True, status=0, message="synthetic stop",
                               jac=np.zeros(2)), **changes)


@pytest.mark.parametrize("target", [(0.5, -0.4), (3.0, -3.0)])
def test_bounded_fit_matches_evaluated_objective_and_records_every_call(target):
    problem = QuadraticProblem(target)
    result = training.fit(problem, (8.0, -9.0))
    np.testing.assert_allclose(result["parameters"], np.clip(target, problem.lower, problem.upper),
                               atol=0.002)
    expected = np.r_[(result["parameters"] - target) * [2.0, 3.0], 4.0]
    assert result["score"] == pytest.approx(expected @ expected)
    assert result["evaluations"] == len(problem.calls) == len(result["history"])
    assert result["evaluations"] == result["scipy_result"]["nfev"]
    assert len(problem.calculations) == result["final_metadata_calculate_calls"] == 1
    np.testing.assert_array_equal(problem.calculations[0], result["parameters"])
    assert result["history_kind"] == "all residual evaluations including Jacobians"
    for observed, recorded in zip(problem.calls, result["history"], strict=True):
        np.testing.assert_array_equal(observed, recorded["parameters"])
    assert result["active_points"] == 2
    assert result["residual_rms_hz"] == pytest.approx(np.sqrt(12.5))
    assert result["normalization_constant"] == 17.0
    assert result["negative_twice_elbo"] == 123.0
    assert result["budget_exhausted"] is False
    assert result["solution_origin"] == "scipy_result"


def test_exact_probe_policy_and_clipped_start_without_verification_residual(monkeypatch):
    problem = QuadraticProblem()

    def minimize(objective, start, *, method, bounds, options):
        assert method == "L-BFGS-B"
        assert options == dict(maxiter=48, maxfun=625, eps=0.001,
                               ftol=2.220446049250313e-9, gtol=1e-5, maxls=20, maxcor=10)
        np.testing.assert_array_equal(start, [-1.0, 1.0])
        np.testing.assert_array_equal(bounds, np.array([problem.lower, problem.upper]).T)
        return returned(objective, start)

    monkeypatch.setattr(training, "minimize", minimize)
    result = training.fit(problem, [-9.0, 9.0])
    assert len(problem.calls) == result["evaluations"] == 1
    assert result["optimizer_policy"] == training.fit.policy == annotation_training_policy()
    result["optimizer_policy"]["options"]["eps"] = 99
    assert training.fit.policy["options"]["eps"] == 0.001
    assert training.fit(problem, [-9.0, 9.0])["optimizer_policy"]["options"]["eps"] == 0.001


def test_physical_cap_counts_finite_difference_calls_and_returns_best_seen(monkeypatch):
    problem = QuadraticProblem()

    def exhaust(objective, start, **kwargs):
        objective(np.array([0.2, -0.3]))
        for _ in range(208):
            objective(start)
            objective(start + [0.001, 0.0])
            objective(start + [0.0, 0.001])
        objective(start)
        pytest.fail("Physical residual cap ignored")

    monkeypatch.setattr(training, "minimize", exhaust)
    result = training.fit(problem)
    assert result["evaluations"] == len(problem.calls) == 625
    assert len(result["history"]) == 625
    np.testing.assert_array_equal(result["parameters"], [0.2, -0.3])
    assert result["score"] == 16.0
    assert result["scipy_result"] is None
    assert result["converged"] is False
    assert result["budget_exhausted"] is True
    assert result["stationarity"]["satisfied"] is None
    assert result["solution_origin"] == "lowest evaluated score after physical call cap"
    assert result["stopped"] == "physical residual call cap reached"
    assert len(problem.calculations) == 1


@pytest.mark.parametrize("nit,success,budget", [(48, False, True), (2, False, False),
                                                 (2, True, False)])
def test_status_and_stationarity_do_not_equate_relative_reduction_to_stationarity(
    monkeypatch, nit, success, budget
):
    def minimize(objective, start, **kwargs):
        return returned(objective, start, nit=nit, success=success, status=0 if success else 1,
                        message="RELATIVE REDUCTION OF F", jac=np.array([0.5, -0.7]))

    monkeypatch.setattr(training, "minimize", minimize)
    result = training.fit(QuadraticProblem())
    assert result["converged"] is (success and not budget)
    assert result["budget_exhausted"] is budget
    assert result["scipy_result"]["success"] is success
    assert "RELATIVE REDUCTION" in result["stopped"]
    assert result["convergence_kind"] == "scipy-reported success within budget"
    assert result["stationarity"] == dict(source="scipy_result.jac",
                                           projected_gradient_inf_norm=0.7,
                                           gtol=1e-5, satisfied=False)


def test_bound_projected_gradient_uses_no_extra_evaluations(monkeypatch):
    def minimize(objective, start, **kwargs):
        return returned(objective, start, jac=np.array([5.0, -7.0]))

    monkeypatch.setattr(training, "minimize", minimize)
    result = training.fit(QuadraticProblem(), [-1.0, 1.0])
    assert result["stationarity"]["projected_gradient_inf_norm"] == 0.0
    assert result["stationarity"]["satisfied"] is True
    assert result["evaluations"] == 1


def test_optimizer_exception_is_not_presented_as_convergence(monkeypatch):
    problem = QuadraticProblem()

    def fail(objective, start, **kwargs):
        objective(start)
        raise RuntimeError("optimizer failure")

    monkeypatch.setattr(training, "minimize", fail)
    with pytest.raises(RuntimeError, match="optimizer failure"):
        training.fit(problem)
    assert len(problem.calls) == 1
    assert problem.calculations == []


def test_real_abnormal_return_recovers_recorded_score_without_claiming_success(monkeypatch):
    problem = QuadraticProblem()
    problem.lower, problem.upper = np.array([-1., -1.]), np.array([1., 1.])

    def residual(at):
        problem.calls.append(at.copy())
        return np.r_[at - problem.target, 1.]

    problem.residual = residual
    minimize = training.minimize

    def one_line_search(objective, start, **kwargs):
        kwargs['options'] = dict(kwargs['options'], maxls=1)
        return minimize(objective, start, **kwargs)

    monkeypatch.setattr(training, 'minimize', one_line_search)
    result = training.fit(problem)
    np.testing.assert_array_equal(result['parameters'], [0., 0.])
    assert result['score'] == 1.13
    assert result['scipy_result']['reported_fun'] != result['score']
    assert result['scipy_result']['status'] == 2
    assert result['scipy_result']['success'] is result['converged'] is False
    assert result['budget_exhausted'] is False
    assert result['score_correction'] == dict(
        reason='abnormal line search restored parameters', recorded_score=1.13,
        reported_score=result['scipy_result']['reported_fun'], additional_residual_evaluations=0)
    assert result['evaluations'] == len(problem.calls) == 6
    assert result['solution_origin'] == 'scipy_result_with_recorded_score'


@pytest.mark.parametrize('changes', [dict(success=True), dict(status=1),
                                    dict(message='unknown failure'), dict(x=[.3, .3])])
def test_unexplained_mismatches_still_fail(monkeypatch, changes):
    def minimize(objective, start, **kwargs):
        values = dict(fun=999., success=False, status=2, message='ABNORMAL: ')
        values.update(changes)
        return returned(objective, start, **values)

    monkeypatch.setattr(training, 'minimize', minimize)
    with pytest.raises(ValueError):
        training.fit(QuadraticProblem())


def test_abnormal_return_cannot_choose_between_conflicting_scores_at_same_point(monkeypatch):
    problem = QuadraticProblem()

    def residual(at):
        problem.calls.append(at.copy())
        return np.array([float(len(problem.calls))])

    problem.residual = residual

    def minimize(objective, start, **kwargs):
        objective(start)
        objective(start)
        return OptimizeResult(x=start, fun=999., nfev=2, njev=0, nit=0,
                              success=False, status=2, message='ABNORMAL: ', jac=np.zeros(2))

    monkeypatch.setattr(training, 'minimize', minimize)
    with pytest.raises(ValueError, match='evaluated point and score'):
        training.fit(problem)


@pytest.mark.parametrize("start,lower,upper", [
    ([0.0], [-1.0, -2.0], [2.0, 1.0]),
    ([np.nan, 0.0], [-1.0, -2.0], [2.0, 1.0]),
    ([0.0, 0.0], [-1.0], [2.0, 1.0]),
    ([0.0, 0.0], [-1.0, -2.0], [2.0, np.inf]),
    ([0.0, 0.0], [2.0, -2.0], [2.0, 1.0]),
])
def test_invalid_start_or_bounds_fail_before_work(start, lower, upper):
    problem = QuadraticProblem()
    problem.lower, problem.upper = lower, upper
    with pytest.raises(ValueError):
        training.fit(problem, start)
    assert problem.calls == problem.calculations == []


def test_changed_iteration_budget_fails_before_work():
    problem = QuadraticProblem()
    with pytest.raises(ValueError, match="48 position steps"):
        training.fit(problem, iterations=47)
    assert problem.calls == problem.calculations == []


@pytest.mark.parametrize("value", [[], 1.0, [[1.0]], [np.nan], [np.inf], [1e308]])
def test_invalid_residuals_fail_without_final_calculation(value):
    problem = QuadraticProblem()
    problem.residual = lambda at: value
    with pytest.raises(ValueError):
        training.fit(problem)
    assert problem.calculations == []


def test_residual_length_cannot_change_during_derivatives():
    problem = QuadraticProblem()
    calls = []

    def residual(at):
        calls.append(at)
        return np.ones(len(calls))

    problem.residual = residual
    with pytest.raises(ValueError, match="Invariant residual length"):
        training.fit(problem)
    assert len(calls) == 2
    assert problem.calculations == []


@pytest.mark.parametrize("changes", [
    dict(x=[np.nan, 0.0]), dict(x=[5.0, 0.0]), dict(x=[0.0]), dict(fun=np.nan),
    dict(x=[0.1, 0.0]), dict(fun=999.0), dict(nfev=2), dict(nfev=-1), dict(nfev=1.0),
    dict(njev=2), dict(nit=-1), dict(jac=[np.inf, 0.0]), dict(jac=[0.0]),
    dict(status=0.5), dict(success="yes"),
])
def test_invalid_optimizer_returns_cannot_be_reported_as_fits(monkeypatch, changes):
    def minimize(objective, start, **kwargs):
        return returned(objective, start, **changes)

    monkeypatch.setattr(training, "minimize", minimize)
    problem = QuadraticProblem()
    with pytest.raises(ValueError):
        training.fit(problem)
    assert len(problem.calls) == 1
    assert problem.calculations == []


@pytest.mark.parametrize("field,value", [
    ("conditional_residual_hz", [np.nan, 1.0, 1.0]),
    ("conditional_residual_hz", [[1.0, 2.0, 3.0]]),
    ("conditional_residual_hz", [1.0, 2.0]),
    ("conditional_residual_hz", [1e308, 1.0, 1e308]),
    ("normalization_constant", np.inf), ("negative_twice_elbo", np.nan),
    ("normalization_constant", [1.0]),
])
def test_final_metadata_must_be_finite_and_consistent(monkeypatch, field, value):
    monkeypatch.setattr(training, "minimize", lambda objective, start, **kwargs:
                        returned(objective, start))
    problem = QuadraticProblem()
    calculate = problem.calculate

    def invalid(at):
        return dict(calculate(at), **{field: value})

    problem.calculate = invalid
    with pytest.raises(ValueError):
        training.fit(problem)
    assert len(problem.calls) == len(problem.calculations) == 1


@pytest.mark.parametrize("keep", [[False, False, False], [1, 0, 1], [True, False]])
def test_final_metadata_requires_nonempty_matching_boolean_mask(monkeypatch, keep):
    monkeypatch.setattr(training, "minimize", lambda objective, start, **kwargs:
                        returned(objective, start))
    problem = QuadraticProblem()
    problem.keep = np.asarray(keep)
    with pytest.raises(ValueError, match="boolean mask"):
        training.fit(problem)
    assert len(problem.calls) == len(problem.calculations) == 1


def test_history_and_policy_copies_cannot_mutate_other_fit_results():
    first = training.fit(QuadraticProblem())
    second = training.fit(QuadraticProblem())
    expected = deepcopy(second)
    first["parameters"][0] = 99.0
    first["history"][0]["parameters"][0] = 99.0
    first["optimizer_policy"]["options"]["maxiter"] = 99
    assert second["optimizer_policy"] == expected["optimizer_policy"]
    np.testing.assert_array_equal(second["parameters"], expected["parameters"])
    np.testing.assert_array_equal(second["history"][0]["parameters"],
                                  expected["history"][0]["parameters"])
