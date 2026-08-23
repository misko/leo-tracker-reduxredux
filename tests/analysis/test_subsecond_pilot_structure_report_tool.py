from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


def _tool():
    path = Path(__file__).parents[2] / "tools" / "report_subsecond_pilot_structure.py"
    tools_path = str(path.parent)
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    spec = importlib.util.spec_from_file_location("subsecond_pilot_structure_report_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _frame(
    index: int,
    *,
    state: int,
    ordinary_hz: float | None,
    corrected_hz: float | None,
) -> dict:
    time_s = index / 750
    return {
        "reference_time_s": time_s,
        "pi_ambiguity_state": state,
        "phase_implied_frequency_error_hz": ordinary_hz,
        "pi_corrected_phase_implied_frequency_error_hz": corrected_hz,
        "exact_coherence": 0.8,
        "coherence_margin": 0.7,
        "frequency_fit_cfo_hz": 2_000 + 250 * time_s,
        "model_cfo_hz": 1_500 - 50 * time_s,
        "phase_measurement_rad": 0.4 + 2 * np.pi * 500 * time_s + np.pi * state,
    }


def test_binary_state_metrics_find_repeating_template() -> None:
    tool = _tool()
    template = np.asarray([1, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0])
    states = np.tile(template, 6)[:60]
    frames = [
        _frame(index, state=int(state), ordinary_hz=0.0, corrected_hz=0.0)
        for index, state in enumerate(states)
    ]

    metrics = tool._state_period_metrics(frames)

    assert metrics["strongest_repeat_lag_frames"] == len(template)
    assert metrics["template_agreement"] == pytest.approx(1.0)
    assert metrics["bit_sequence"].startswith("11000110000")


def test_pi_correction_collapses_transition_frequency_alias() -> None:
    tool = _tool()
    states = np.asarray([0, 0, 1, 1, 0, 1, 1, 0])
    frames = []
    for index, state in enumerate(states):
        if index == 0:
            ordinary = None
            corrected = None
        else:
            transition = state != states[index - 1]
            ordinary = 375.0 if transition else 0.0
            corrected = 0.0
        frames.append(_frame(index, state=int(state), ordinary_hz=ordinary, corrected_hz=corrected))

    metrics = tool._frequency_mode_metrics(frames)

    assert metrics["ordinary_modes_by_binary_transition"]["same_binary_state"]["median_hz"] == 0
    assert (
        metrics["ordinary_modes_by_binary_transition"]["binary_state_transition"]["median_hz"]
        == 375
    )
    assert metrics["pi_corrected_rms_hz"] == pytest.approx(0.0)


def test_local_linear_smoother_predicts_subsecond_ramp_and_step() -> None:
    tool = _tool()
    times = np.arange(0.0, 0.080, 1 / 750)
    truth = 3_200 * times + np.where(times >= 0.040, -180.0, 0.0)
    train = np.arange(len(times)) % 2 == 0
    test = ~train

    prediction = tool._weighted_local_linear_prediction(
        times[train],
        truth[train],
        np.ones(np.count_nonzero(train)),
        times[test],
        bandwidth_s=0.005,
    )
    error = truth[test] - prediction

    away_from_step = np.abs(times[test] - 0.040) > 0.010
    assert np.sqrt(np.mean(error[away_from_step] ** 2)) < 1.0
    assert tool._error_metrics(error)["rms_hz"] < 35.0


def test_error_metrics_ignore_nonfinite_values() -> None:
    tool = _tool()

    metrics = tool._error_metrics(np.asarray([3.0, -4.0, np.nan]))

    assert metrics == {
        "count": 2,
        "rms_hz": pytest.approx(np.sqrt(12.5)),
        "median_absolute_hz": pytest.approx(3.5),
        "p90_absolute_hz": pytest.approx(3.9),
    }
