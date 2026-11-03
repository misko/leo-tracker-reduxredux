from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ds11_source_loo_exact_test", HERE / "exact_audit.py")
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


class FakeGeometry:
    def __init__(self, document, config):
        del document, config

    def prediction(self, track, x):
        return np.zeros((2, len(track["y"]))), np.ones(2, dtype=bool)


def test_common_held_scorer_uses_training_profile_once_and_joint_minus_train():
    calls = []

    def profile(residual, mask):
        calls.append((residual.copy(), mask.copy()))
        # Values deliberately make reprofiled held-only or averaged candidate scoring differ.
        return (np.asarray([0.0, -2.0]), np.asarray([1.0, 3.0]),
                [{"converged": True}, {"converged": True}], np.asarray([10.0, 20.0]))

    document = {"tracks": [{"track_id": "a", "y": np.asarray([1.0, 2.0, 3.0]),
                            "mask": np.asarray([True, True, False])}]}
    result = audit.common_held_score(
        document, [0], np.zeros(3), stationary_factory=FakeGeometry, profile_fn=profile
    )
    expected = np.logaddexp(1.0, 3.0) - np.logaddexp(0.0, -2.0)
    assert len(calls) == 1
    np.testing.assert_array_equal(calls[0][1], [True, True, False])
    assert abs(result["score"] - expected) < 1e-12
    assert result["held_observation_count"] == 1


def test_comparison_uses_frozen_exact_thresholds():
    exact = np.asarray([1.0, 0.0, 0.1])
    influence = np.asarray([0.91, 0.0, 0.085])
    result = audit.comparison(exact, influence, np.zeros(3), 4.0, 4.05)
    assert result["en_limit_km"] == 0.1
    assert result["passes_tolerances"]
    failed = audit.comparison(exact, np.asarray([0.89, 0.0, 0.1]), np.zeros(3), 4.0, 4.0)
    assert not failed["passes_tolerances"]


def test_selected_jobs_requires_complete_frozen_selection():
    families = []
    for family in ("iid_t4_scale100", "source_receiver_equal", "robust_t8_scale100",
                   "robust_t4_scale200"):
        families.append({"family": family, "selection": {
            "selection_complete": True, "largest_norad": 1, "lower_median_norad": 2,
        }})
    jobs = audit.selected_jobs({"families": families})
    assert len(jobs) == 8
    families[0]["selection"]["selection_complete"] = False
    try:
        audit.selected_jobs({"families": families})
    except ValueError as exc:
        assert "incomplete" in str(exc)
    else:
        raise AssertionError("incomplete selection accepted")


class QuadraticModel:
    def evaluate(self, x, gradient=True):
        x = np.asarray(x)
        return {"score": float(-0.5 * x @ x), "gradient": -x}


class Result:
    x = np.asarray([0.001, -0.002, 0.0005])
    jac = -QuadraticModel().evaluate(x)["gradient"]
    fun = 0.5 * float(x @ x)
    success = True
    message = "ok"


def test_qualification_uses_score_gradient_sign_and_central_audit():
    result = audit.qualify(Result(), QuadraticModel(), np.asarray([[-12, 12], [-12, 12], [-5, 5]]))
    assert result["qualified"]
    assert result["gradient_audit_max_abs"] < 1e-9
