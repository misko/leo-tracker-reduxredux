import numpy as np
import pytest

from tools.pipeline_eval import cavity_runtime
from tools.pipeline_eval.qualification import solver_reuse_build as install
from tools.pipeline_eval.variants import compact_endpoint as candidate


class Problem:
    def __init__(self):
        self.lower = np.array([-3.0, -3.0])
        self.upper = np.array([3.0, 3.0])
        self.keep = np.array([True, True, False])
        self.reference = np.array([0.0])
        self.phase_sigma = np.array([0.7])
        self.fitted_c = False
        self.members = [1]
        self.rows = [{"candidate_index": 12}]
        self.alias = [2]
        self.count = 0

    def calculate(self, x):
        self.count += 1
        return {"value": np.asarray(x).copy(), "call": self.count}

    def residual(self, x):
        return candidate.endpoint(self, x)["value"] - [0.3, 0.2]


def rejected_last(residual, start, lower, upper, *, iterations, on_accept=None):
    accepted = np.asarray(start)
    residual(accepted)
    if on_accept:
        on_accept(accepted)
    residual(np.array([1.0, 0.0]))
    return dict(
        parameters=accepted,
        history=[dict(parameters=accepted, score=7.0)],
        evaluations=2,
        stopped="no_accepted_trust_step",
        rejected_trials=1,
        jacobian_refreshes=1,
        secant_updates=0,
    )


def test_accepted_payload_survives_later_rejected_evaluation_and_guards_exact_view():
    p = Problem()
    candidate.reset(True)
    fit = candidate.optimize(p, rejected_last, [0.0, 0.0], 4)
    outcome = candidate.endpoint(p, fit["parameters"])
    assert outcome["call"] == 1
    assert p.count == 2
    assert "calculate" not in vars(p)
    assert candidate.endpoint(p, [-0.0, 0.0])["call"] == 3
    p.keep[0] = False
    assert candidate.endpoint(p, fit["parameters"])["call"] == 4
    assert candidate.receipt()["reporting_calculations_saved"] == 1


def test_optimizer_trajectory_and_terminal_functions_match_the_frozen_stock():
    baseline = cavity_runtime.release_files(cavity_runtime.RELEASE, "phase-release")
    overlaid = install.stage(dict(baseline), enabled=True)
    a, b = {}, {}
    exec(compile(baseline[install.OPTIMIZER], "stock", "exec"), a)
    exec(compile(overlaid[install.OPTIMIZER], "candidate", "exec"), b)
    result = []
    for enabled, solver in ((False, a), (True, b)):
        p = Problem()
        candidate.reset(enabled)
        fit = candidate.optimize(p, solver["bounded_secant"], [0.0, 0.0], 24)
        value = candidate.endpoint(p, fit["parameters"])["value"].tobytes()
        result.append((p.count, value, candidate.receipt()))
    assert result[0][0] == result[1][0] + 1
    assert result[0][1] == result[1][1]
    assert result[0][2]["fit_trajectory_sha256"] == result[1][2]["fit_trajectory_sha256"]


def test_existing_lru_is_excluded_and_temporary_calculation_restores_on_error():
    p = Problem()
    p._has_fit_cache = True
    candidate.reset(True)
    fit = candidate.optimize(p, rejected_last, [0.0, 0.0], 4)
    assert candidate.endpoint(p, fit["parameters"])["call"] == 3
    assert candidate.receipt().get("reporting_calculations_saved", 0) == 0

    def failed(residual, *args, **kwargs):
        residual(np.zeros(2))
        raise ValueError("invalid numerical input")

    replacement = p.calculate
    p.calculate = replacement
    p._has_fit_cache = False
    candidate.reset(True)
    with pytest.raises(ValueError, match="invalid numerical input"):
        candidate.optimize(p, failed, [0.0, 0.0], 4)
    assert p.calculate is replacement
