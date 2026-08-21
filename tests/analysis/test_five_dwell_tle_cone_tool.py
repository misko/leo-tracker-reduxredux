from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_five_dwell_tle_cone.py"
    spec = importlib.util.spec_from_file_location("five_dwell_tle_cone_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_linear_rate_is_polynomial_rate_at_reference_time() -> None:
    tool = _tool()

    assert tool._linear_rate_hz_s((12.0, 3.0)) == 12.0
    assert tool._linear_rate_hz_s((0.5, -2_000.0, 9.0)) == -2_000.0
    assert tool._linear_rate_hz_s((0.2, 0.5, -3_000.0, 9.0)) == -3_000.0


def test_linear_rate_rejects_invalid_or_nonfinite_polynomials() -> None:
    tool = _tool()

    with pytest.raises(ValueError, match="two to four"):
        tool._linear_rate_hz_s((1.0,))
    with pytest.raises(ValueError, match="finite"):
        tool._linear_rate_hz_s((np.inf, 0.0))


def test_track_rate_evaluates_complete_polynomial_derivative() -> None:
    tool = _tool()
    track = SimpleNamespace(
        start_s=12.0,
        row=SimpleNamespace(
            start_s=2.0,
            reference_time_s=4.0,
            absolute_coefficients_hz=(0.2, 0.5, -3_000.0, 9.0),
        ),
    )

    dwell_times = np.asarray([12.0, 13.0, 15.0])
    rates = tool._track_rate(track, dwell_times)

    np.testing.assert_allclose(rates, np.polyval((0.6, 1.0, -3_000.0), (-2.0, -1.0, 1.0)))


def test_interval_rate_metrics_fit_both_series_on_identical_overlap() -> None:
    tool = _tool()
    track = SimpleNamespace(
        start_s=0.0,
        end_s=10.0,
        duration_s=10.0,
        row=SimpleNamespace(
            start_s=0.0,
            reference_time_s=5.0,
            absolute_coefficients_hz=(-2_000.0, 0.0),
        ),
    )
    satellite = tool.ConeSatellite(
        0,
        "STARLINK-TEST",
        123,
        85.0,
        0,
        0.0,
        (tool.ThresholdInterval(2.0, 8.0, False, False),),
    )
    times = np.linspace(0.0, 10.0, 101)

    metrics = tool._interval_rate_metrics(track, satellite, times, -1_500.0 * times)

    assert metrics is not None
    assert metrics["overlap_duration_s"] == pytest.approx(6.0)
    assert metrics["overlap_fraction"] == pytest.approx(0.6)
    assert metrics["measured_linear_rate_hz_s"] == pytest.approx(-2_000.0)
    assert metrics["predicted_linear_rate_hz_s"] == pytest.approx(-1_500.0)
    assert metrics["signed_linear_rate_difference_hz_s"] == pytest.approx(-500.0)
    assert metrics["instantaneous_rate_rms_difference_hz_s"] == pytest.approx(500.0)


def test_held_out_matching_recovers_curve_timing_and_nuisance(monkeypatch) -> None:
    tool = _tool()
    prediction_times = np.arange(-35.0, 55.01, 0.05)

    def truth(values: np.ndarray) -> np.ndarray:
        return 0.8 * values**3 - 20.0 * values**2 - 2_500.0 * values + 1_000.0

    def decoy(values: np.ndarray) -> np.ndarray:
        return -0.5 * values**3 + 80.0 * values**2 - 500.0 * values - 4_000.0

    observation_times = np.arange(0.0, 20.01, 0.1)
    measured = truth(observation_times + 0.35) + 80_000.0 + 12.0 * (
        observation_times - 10.0
    )
    coefficients = tuple(np.polyfit(observation_times - 10.0, measured, 3))
    track = tool.FinalTrack(
        "T1",
        SimpleNamespace(label="stream/RX0"),
        SimpleNamespace(
            start_s=0.0,
            end_s=20.0,
            reference_time_s=10.0,
            absolute_coefficients_hz=coefficients,
        ),
        0.0,
        20.0,
    )
    satellites = (
        tool.ConeSatellite(
            0,
            "STARLINK-TRUTH",
            101,
            89.0,
            0,
            0.0,
            (tool.ThresholdInterval(0.0, 20.0, True, True),),
        ),
        tool.ConeSatellite(
            1,
            "STARLINK-DECOY",
            202,
            88.0,
            0,
            0.0,
            (tool.ThresholdInterval(0.0, 20.0, True, True),),
        ),
    )
    monkeypatch.setattr(
        tool,
        "_track_observations",
        lambda _track: tool.TrackObservations(observation_times, measured),
    )

    result = tool._analyze_track_matches(
        track,
        satellites,
        prediction_times,
        {101: truth(prediction_times), 202: decoy(prediction_times)},
    )

    assert result["trajectory_matches"][0]["catalog_number"] == 101
    assert result["trajectory_matches"][0]["epoch_adjustment_s"] == pytest.approx(0.35)
    assert result["trajectory_matches"][0]["nuisance_drift_hz_s"] == pytest.approx(12.0)
    assert result["trajectory_matches"][0]["holdout_residual_rms_hz"] < 1e-5
    assert result["stability"]["same_catalog_number_across_cases"]
    assert result["classification"] == "stable_candidate_association"
