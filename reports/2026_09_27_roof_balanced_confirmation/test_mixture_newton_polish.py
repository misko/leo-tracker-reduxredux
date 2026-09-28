import importlib.util
import math
from pathlib import Path
import sys

import numpy as np
import pytest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mixture_reception_core as core

PATH = HERE / "mixture_newton_polish.py"
SPEC = importlib.util.spec_from_file_location("mixture_newton_polish", PATH)
POLISH = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = POLISH
SPEC.loader.exec_module(POLISH)


def test_quadratic_polish_is_monotone_and_reaches_target():
    matrix = np.diag([2., 5.])
    center = np.array([1., -2.])
    def value_gradient(x):
        delta = x - center
        return .5 * float(delta @ matrix @ delta), matrix @ delta
    result = POLISH.newton_polish(
        [10., 10.], value_gradient, lambda _x: matrix,
        target_gradient=1e-10)
    assert result["accepted"]
    assert result["theta"] == pytest.approx(center)
    assert all(row["objective_after"] <= row["objective_before"]
               for row in result["history"] if row["accepted"])


def test_bad_curvature_is_not_accepted():
    result = POLISH.newton_polish(
        [1.], lambda x: (-float(x[0] ** 2), np.array([-2 * x[0]])),
        lambda _x: np.array([[-2.]]))
    assert not result["accepted"]
    assert result["accepted_steps"] == 0
    assert result["stop_reason"] == "nonpositive_or_weak_curvature"


def test_nonfinite_hessian_is_not_accepted():
    result = POLISH.newton_polish(
        [1.], lambda x: (float(x[0] ** 2), np.array([2 * x[0]])),
        lambda _x: np.array([[float("nan")]]))
    assert not result["accepted"]
    assert result["stop_reason"] == "nonfinite_hessian"


def test_failed_line_search_rejects_even_gradient_below_acceptance_gate():
    def value_gradient(x):
        if x[0] == 0.:
            return 0., np.array([1e-7])  # below 1e-6, above 1e-8 target
        return math.inf, np.array([1e-7])
    result = POLISH.newton_polish(
        [0.], value_gradient, lambda _x: np.array([[1.]]),
        max_line_search_steps=3)
    assert result["gradient_accepted"]
    assert result["fatal_stop"]
    assert not result["accepted"]
    assert result["stop_reason"] == "line_search_failed"


def test_nonfinite_initial_objective_raises_before_polish():
    with pytest.raises(ValueError, match="initial objective"):
        POLISH.newton_polish(
            [0.], lambda _x: (math.inf, np.array([0.])),
            lambda _x: np.array([[1.]]))


def test_step_cap_is_hard_and_preserves_monotonicity():
    # Deliberately inaccurate positive Hessian yields progress but not convergence.
    value_gradient = lambda x: (float((x[0] - 3.) ** 2),
                                np.array([2 * (x[0] - 3.)]))
    result = POLISH.newton_polish(
        [0.], value_gradient, lambda _x: np.array([[20.]]), max_steps=1)
    assert result["steps_attempted"] == 1
    assert result["accepted_steps"] == 1
    assert result["objective"] < 9.
    assert result["stop_reason"] == "maximum_steps"


def fixture():
    layout = core.ParameterLayout(2, 2, [False, True], [False, True])
    detection = np.array([
        [[1., -1.], [1., -.5], [1., .2], [1., .7]],
        [[1., 1.], [1., .5], [1., -.2], [1., -.7]],
    ])
    track = core.TrackData(
        [-math.log(2)] * 2, detection, [True, False, True, False],
        detection.copy(), [.2, 0., -.1, 0.])
    return layout, [track]


def test_actual_core_fixture_polish_never_increases_objective():
    layout, tracks = fixture()
    start = np.array([.1, -.1, .2, -.2, math.log(1.3)])
    before = core.objective_gradient(start, tracks, layout)[0]
    result = POLISH.newton_polish(
        start, lambda x: core.objective_gradient(x, tracks, layout),
        lambda x: core.numerical_hessian(x, tracks, layout), max_steps=4)
    assert result["objective"] <= before
    objectives = [row["objective_after"] for row in result["history"]
                  if row["accepted"]]
    assert objectives == sorted(objectives, reverse=True)


def test_multistart_preserves_raw_runs_and_reapplies_frozen_gates():
    layout, tracks = fixture()
    raw = [{"theta": value.tolist(),
            "objective": core.objective_gradient(value, tracks, layout)[0],
            "tag": index}
           for index, value in enumerate(core.default_starts(layout))]
    result = POLISH.polish_multistart(raw, tracks, layout, max_steps=2)
    assert len(result["runs"]) == 3
    assert [run["input_run"]["tag"] for run in result["runs"]] == [0, 1, 2]
    assert result["configuration"]["acceptance_gradient"] == 1e-6
    assert result["configuration"]["objective_stability_tolerance"] == 1e-7


def test_multistart_rejects_saved_objective_binding_mismatch():
    layout, tracks = fixture()
    raw = [{"theta": value.tolist(), "objective": 999.}
           for value in core.default_starts(layout)]
    with pytest.raises(ValueError, match="differs from reconstructed"):
        POLISH.polish_multistart(raw, tracks, layout)
