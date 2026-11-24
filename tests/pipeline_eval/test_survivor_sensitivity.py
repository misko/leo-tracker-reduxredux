from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants.compact_cavity_optimizer import _forward_points

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from survivor_sensitivity import endpoint_step


def problem(residual):
    return SimpleNamespace(residual=residual, lower=np.full(2, -1.), upper=np.full(2, 1.))


@pytest.mark.parametrize("shift,reason,calls", [(.005, None, 4), (.015, "predicted_step_over_10_m", 3), (.0004, None, 3)])
def test_unthresholded_move_and_exact_trial(shift, reason, calls):
    p = problem(lambda point: np.array([point[0] - shift, point[1] * 2, 30.]))
    result = endpoint_step(p, np.zeros(2), _forward_points)
    assert result["reason"] == reason
    assert result["evaluations"] == calls
    assert result["movement_km"] == pytest.approx(shift)
    if calls == 4:
        assert result["exact_objective_decrease"] == pytest.approx(shift ** 2)


def test_reject_a_bad_local_prediction():
    def misfit(point):
        x, y = point
        return np.array([x - .005 + 2500 * x * (x - .001), y])

    result = endpoint_step(problem(misfit), np.zeros(2), _forward_points)
    assert result["reason"] == "exact_objective_did_not_improve"
    assert result["evaluations"] == 4


def test_rank_deficiency_and_boundary_retain_original_fit():
    p = problem(lambda point: np.array([point[0], 0.]))
    inside = endpoint_step(p, np.zeros(2), _forward_points)
    edge = endpoint_step(p, np.array([1., 0.]), _forward_points)
    assert inside["reason"] == "ill_conditioned_horizontal_information"
    assert edge == dict(reason="nonfinite_or_boundary_warm_endpoint", evaluations=0)
