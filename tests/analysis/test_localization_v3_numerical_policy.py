from types import SimpleNamespace

import numpy as np
import pytest
from scipy.optimize import minimize

from leo.analysis.localization_v3 import numerical_policy as policy

BOX = [(-12.5, 12.5)] * 2


def problem():
    return SimpleNamespace(
        sky={"time_s": np.array([-20.0, 40.0])},
        flat_times=np.array([0.0, 1.0]),
        flat_labels=np.array([0, 0]),
        labels=[0],
        reference=np.array([-15.0]),
        linear_entries=[],
    )


@pytest.mark.parametrize("start", [[1.0, -2.0], [-12.5, 12.5], [12.5, -12.5]])
def test_centered_solver_counts_physical_calls_and_handles_box_boundaries(start):
    calls = []

    def objective(x, a, b):
        calls.append(tuple(x))
        return float((x[0] - a) ** 2 + 2 * (x[1] - b) ** 2)

    p = policy.NumericalPolicy()
    result = p.minimize(
        minimize,
        objective,
        start,
        args=(0.5, -0.25),
        method="L-BFGS-B",
        bounds=BOX,
        options=dict(maxfun=240, maxiter=48, eps=0.001, gtol=1e-4),
    )
    assert result.success
    np.testing.assert_allclose(result.x, [0.5, -0.25], atol=1e-4)
    assert len(calls) == len(set(calls)) == result.nfev <= 240
    assert all(-12.5 <= v <= 12.5 for x in calls for v in x)
    assert p.receipt["optimizer_calls"][0]["total_physical_objective_evaluations"] == len(calls)
    assert p.receipt["extra_optimizer_rounds"] == 0


def test_small_budget_returns_last_accepted_point_and_no_false_success():
    calls = []

    def objective(x):
        calls.append(x.copy())
        return float(x @ x)

    result = policy.centered_minimize(
        minimize, objective, [1.0, 2.0], bounds=BOX, options={"maxfun": 2}
    )
    assert not result.success
    assert result.nfev == len(calls) == 2
    assert not result.jac_available
    np.testing.assert_array_equal(result.x, [1.0, 2.0])
    assert result.fun == 5.0


@pytest.mark.parametrize("named", [True, False])
def test_callback_protocol_is_preserved(named):
    seen = []

    def callback(intermediate_result):
        seen.append((intermediate_result.x.copy(), intermediate_result.fun))

    def positional(x):
        seen.append((x.copy(), float(x @ x)))

    result = policy.centered_minimize(
        minimize,
        lambda x: float(x @ x),
        [1.0, 2.0],
        bounds=BOX,
        callback=callback if named else positional,
    )
    assert result.success and seen
    np.testing.assert_array_equal(seen[-1][0], result.x)


def test_reference_window_is_explicit_and_checks_actual_posterior_too():
    p = problem()
    numerics = policy.NumericalPolicy()
    numerics.problem_created(p)
    updated, check = numerics.refresh(p, [-15.2], p.reference)
    np.testing.assert_array_equal(updated, [-15.2])
    assert check["numerical_reference_limit_s"] == 30
    assert check["next_reference_domain"]["curved"]["in_domain"]
    assert numerics.receipt["reference_updates"][0]["caller_limit_s"] == 15
    # The clipped reference fits in the bank but the actual posterior does not.
    with pytest.raises(ValueError, match="no extrapolation"):
        numerics.refresh(p, [50.0], p.reference)
    assert len(numerics.receipt["reference_updates"]) == 1


def test_reference_owner_and_predictive_bank_are_checked(monkeypatch):
    p = problem()
    numerics = policy.NumericalPolicy()
    with pytest.raises(ValueError, match="reference owner"):
        numerics.refresh(p, [-15.2], [0.0])
    with pytest.raises(ValueError, match="shape mismatch"):
        numerics.refresh(p, [-15.2], [0.0, 0.0])
    p.reference = np.zeros(1)
    p.linear_entries = [{}]
    monkeypatch.setattr(
        policy,
        "linear_geometry",
        lambda *a: (SimpleNamespace(flat_times=np.array([-10.0]), flat_labels=np.array([0])),),
    )
    numerics.problem_created(p)
    with pytest.raises(ValueError, match="no extrapolation"):
        numerics.refresh(p, [-15.2], p.reference)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"method": "Powell", "bounds": BOX},
        {"method": "L-BFGS-B", "bounds": [(-1.0, 1.0)] * 2},
        {"method": "L-BFGS-B", "bounds": BOX, "jac": True},
    ],
)
def test_other_optimizations_are_forwarded_unchanged(kwargs):
    calls = []
    expected = object()

    def original(*a, **kw):
        calls.append((a, kw))
        return expected

    numerics = policy.NumericalPolicy()
    def fun(x):
        return x
    assert numerics.minimize(original, fun, [0.0, 0.0], **kwargs) is expected
    assert calls[0][0] == (fun, [0.0, 0.0])
    assert all(calls[0][1][k] == v for k, v in kwargs.items())
    assert numerics.receipt["optimizer_calls"] == []


def test_default_context_keeps_old_reference_policy_and_optimizer_arguments():
    updated, check = policy.refresh({}, object(), [-16.0], [0.0])
    np.testing.assert_array_equal(updated, [-15.0])
    assert check["phase_outside_reference_window"]
    seen = []
    policy.minimize({}, lambda *a, **kw: seen.append((a, kw)), "f", [0, 0], method="Powell")
    assert seen == [(("f", [0, 0]), {"method": "Powell"})]


def test_policy_does_not_mutate_global_optimizer_or_phase_function():
    import scipy.optimize

    from leo.analysis.localization_v3 import phase_reference

    original = phase_reference.phase_refresh
    policy.NumericalPolicy()
    assert scipy.optimize.minimize is minimize
    assert phase_reference.phase_refresh is original
    with pytest.raises(ValueError, match="explicit reference limit"):
        policy.NumericalPolicy(reference_limit_s=60)
