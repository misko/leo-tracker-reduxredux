import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np


SPEC = importlib.util.spec_from_file_location(
    "screen_recovery_fit_policy_test", Path(__file__).with_name("fit_policy.py")
)
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)

BOUNDS = np.asarray(((-12.0, 12.0), (-12.0, 12.0), (-5.0, 5.0)))


class Quadratic:
    def __init__(self, center=(0.0, 0.0, 0.0)):
        self.center = np.asarray(center, dtype=float)
        self.hessian = np.diag((2.0, 3.0, 4.0))

    def evaluate(self, x, gradient=True):
        residual = np.asarray(x) - self.center
        return {
            "score": float(-0.5 * residual @ self.hessian @ residual),
            "gradient": -self.hessian @ residual,
        }


def result(x, *, success):
    x = np.asarray(x, dtype=float)
    return SimpleNamespace(
        x=x, fun=1.0, jac=np.asarray((1e-5, 1e-5, 1e-6)),
        success=success, message="status", nfev=5, nit=2,
    )


def qualification(qualified):
    return {
        "qualified": qualified,
        "success": qualified,
        "message": "status",
        "boundary": False,
        "gradient_max_abs": 1e-5,
        "gradient_audit_max_abs": 1e-6,
    }


def test_qualified_original_returns_without_recovery(monkeypatch):
    original = result((0, 0, 0), success=True)
    pilot = SimpleNamespace(fit_local=lambda *args: (original, qualification(True)))
    monkeypatch.setattr(policy.solver, "recover", lambda *args: (_ for _ in ()).throw(
        AssertionError("recovery must not run")))
    selected, checked, records = policy.fit_policy(
        Quadratic(), (0, 0, 0), BOUNDS, pilot, SimpleNamespace(qualify=object())
    )
    assert selected is original and checked["qualified"]
    assert len(records) == 1 and records[0]["returned"]


def test_gated_recovery_is_attempted_once_and_returned_when_accepted(monkeypatch):
    original = result((1e-6, -1e-6, 1e-7), success=False)
    recovered = result((0, 0, 0), success=True)
    old_q, new_q = qualification(False), qualification(True)
    pilot = SimpleNamespace(fit_local=lambda *args: (original, old_q))
    calls = []
    monkeypatch.setattr(policy.solver, "eligible", lambda *args: True)
    monkeypatch.setattr(policy.solver, "recover", lambda *args: (
        calls.append(args) or (recovered, new_q, True)))
    selected, checked, records = policy.fit_policy(
        Quadratic(), original.x, BOUNDS, pilot, SimpleNamespace(qualify=object())
    )
    assert selected is recovered and checked is new_q and len(calls) == 1
    assert len(records) == 2 and records[1]["attempted"] and records[1]["accepted"]
    assert records[1]["gate"]["passed"] and records[1]["returned"]


def test_large_newton_displacement_blocks_recovery(monkeypatch):
    original = result((0.1, 0.0, 0.0), success=False)
    old_q = qualification(False)
    pilot = SimpleNamespace(fit_local=lambda *args: (original, old_q))
    monkeypatch.setattr(policy.solver, "eligible", lambda *args: True)
    monkeypatch.setattr(policy.solver, "recover", lambda *args: (_ for _ in ()).throw(
        AssertionError("failed precision gate reached recovery")))
    selected, checked, records = policy.fit_policy(
        Quadratic(), original.x, BOUNDS, pilot, SimpleNamespace(qualify=object())
    )
    assert selected is original and checked is old_q
    assert not records[1]["attempted"] and not records[1]["gate"]["passed"]
    assert records[1]["gate"]["newton_en_displacement_m"] > 0.01


def test_ill_conditioned_hessian_blocks_recovery(monkeypatch):
    model = Quadratic()
    model.hessian = np.diag((1e-12, 1.0, 1.0))
    original = result((0.0, 0.0, 0.0), success=False)
    old_q = qualification(False)
    pilot = SimpleNamespace(fit_local=lambda *args: (original, old_q))
    monkeypatch.setattr(policy.solver, "eligible", lambda *args: True)
    monkeypatch.setattr(policy.solver, "recover", lambda *args: (_ for _ in ()).throw(
        AssertionError("ill-conditioned gate reached recovery")))
    selected, checked, records = policy.fit_policy(
        model, original.x, BOUNDS, pilot, SimpleNamespace(qualify=object())
    )
    assert selected is original and checked is old_q
    assert not records[1]["attempted"] and not records[1]["gate"]["passed"]
    assert records[1]["gate"]["original_condition_number"] > 1e10
    assert records[1]["gate"]["half_condition_number"] > 1e10


def test_rejected_or_exceptional_recovery_preserves_original(monkeypatch):
    original = result((1e-6, 0.0, 0.0), success=False)
    recovered = result((0, 0, 0), success=True)
    old_q, new_q = qualification(False), qualification(True)
    pilot = SimpleNamespace(fit_local=lambda *args: (original, old_q))
    monkeypatch.setattr(policy.solver, "eligible", lambda *args: True)
    monkeypatch.setattr(policy.solver, "recover", lambda *args: (recovered, new_q, False))
    selected, checked, records = policy.fit_policy(
        Quadratic(), original.x, BOUNDS, pilot, SimpleNamespace(qualify=object())
    )
    assert selected is original and checked is old_q
    assert records[1]["attempted"] and not records[1]["accepted"]

    monkeypatch.setattr(policy.solver, "recover", lambda *args: (_ for _ in ()).throw(
        RuntimeError("single attempt failed")))
    selected, checked, records = policy.fit_policy(
        Quadratic(), original.x, BOUNDS, pilot, SimpleNamespace(qualify=object())
    )
    assert selected is original and checked is old_q
    assert records[1]["attempted"] and "single attempt failed" in records[1]["failure"]
