import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location("recovery_solver_test", Path(__file__).with_name("solver.py"))
solver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(solver)


def case():
    return (SimpleNamespace(x=np.array([1e-5, -1e-5, 0.]), fun=1e-10,
                            jac=np.array([1e-5, -1e-5, 0.]), success=False),
            dict(qualified=False, boundary=False, gradient_max_abs=1e-5,
                 gradient_audit_max_abs=1e-6), np.array([[-12, 12], [-12, 12], [-5, 5]]))


@pytest.mark.parametrize("kind", ["success", "boundary", "nonfinite", "gradient", "audit"])
def test_ineligible_fit_never_invokes_second_solver(kind):
    result, q, bounds = case()
    if kind == "success": result.success = True
    if kind == "boundary": result.x[0] = 12
    if kind == "nonfinite": result.fun = float("nan")
    if kind == "gradient": q["gradient_max_abs"] = .02
    if kind == "audit": q["gradient_audit_max_abs"] = .03
    with pytest.raises(ValueError, match="near-stationary"):
        solver.recover(None, result, q, bounds, None,
                       minimize_fn=lambda *a, **kw: pytest.fail("unexpected continuation"))


@pytest.mark.parametrize("success,qualified,fun,accepted", [
    (True, True, 0., True), (False, False, 0., False),
    (True, False, 0., False), (True, True, 1e-3, False)])
def test_one_continuation_preserves_success_and_nonworsening_requirements(success, qualified, fun, accepted):
    original, q, bounds = case()
    calls = []
    def minimize(objective, x, **kwargs):
        calls.append(x.copy())
        np.testing.assert_array_equal(x, original.x)
        assert kwargs["method"] == "SLSQP" and kwargs["jac"] is True
        assert kwargs["options"] == dict(maxiter=100, ftol=1e-12, disp=False)
        return SimpleNamespace(x=x, fun=fun, success=success)
    result, check, actual = solver.recover(None, original, q, bounds,
        lambda *a: {"qualified": qualified}, minimize_fn=minimize)
    assert len(calls) == 1 and actual is accepted


def test_real_slsqp_on_smooth_quadratic_reaches_stationary_point():
    class Model:
        def evaluate(self, x, gradient=True):
            return dict(score=-.5*float(x@x), gradient=-x)
    original, q, bounds = case()
    def qualify(result, *args):
        return dict(qualified=bool(result.success and np.max(np.abs(result.x)) < 1e-8))
    result, check, accepted = solver.recover(Model(), original, q, bounds, qualify)
    assert accepted and np.linalg.norm(result.x) < 1e-8
