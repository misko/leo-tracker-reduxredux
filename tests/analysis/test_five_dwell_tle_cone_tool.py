from __future__ import annotations

import importlib.util
import inspect
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


def test_linear_radio_fit_uses_observations_not_sealed_cubic(monkeypatch) -> None:
    tool = _tool()
    times = np.linspace(2.0, 12.0, 101)
    cfo = 40_000.0 - 3_200.0 * (times - 7.0)
    track = SimpleNamespace(
        row=SimpleNamespace(
            trajectory_id="track",
            absolute_coefficients_hz=(9e6, -8e6, 7e6, -6e6),
        )
    )
    monkeypatch.setattr(
        tool,
        "_track_observations",
        lambda _track: tool.TrackObservations(times, cfo),
    )

    fit = tool._fit_linear_radio_track(track)

    assert fit.rate_hz_s == pytest.approx(-3_200.0)
    assert fit.intercept_hz == pytest.approx(40_000.0)
    assert fit.residual_rms_hz < 1e-8
    assert fit.first_half_rate_hz_s == pytest.approx(-3_200.0)
    assert fit.second_half_rate_hz_s == pytest.approx(-3_200.0)


def test_linear_radio_fit_reports_half_to_half_instability(monkeypatch) -> None:
    tool = _tool()
    times = np.arange(8.0)
    cfo = np.concatenate((-1_000.0 * times[:4], -4_000.0 - 2_000.0 * (times[4:] - 4.0)))
    track = SimpleNamespace(row=SimpleNamespace(trajectory_id="track"))
    monkeypatch.setattr(
        tool,
        "_track_observations",
        lambda _track: tool.TrackObservations(times, cfo),
    )

    fit = tool._fit_linear_radio_track(track)

    assert fit.first_half_rate_hz_s == pytest.approx(-1_000.0)
    assert fit.second_half_rate_hz_s == pytest.approx(-2_000.0)
    assert fit.formal_rate_standard_error_hz_s > 0.0


def test_sky_rate_evaluation_applies_ten_degree_horizon(monkeypatch) -> None:
    tool = _tool()
    catalogue = SimpleNamespace(
        satellite_numbers=(101, 202, 303),
        names=("STARLINK-A", "STARLINK-B", "STARLINK-C"),
        element_epoch_utc_ns=lambda: (0, 0, 0),
    )
    observed = SimpleNamespace(
        usable=np.asarray([True, True, True]),
        altitude_km=np.full((3, 3), 550.0),
        elevation_deg=np.asarray(
            [[20.0, 20.0, 20.0], [5.0, 5.0, 5.0], [70.0, 70.0, 70.0]]
        ),
        range_rate_km_s=np.asarray(
            [[100.0, 0.0, -100.0], [200.0, 0.0, -200.0], [50.0, 0.0, -50.0]]
        ),
    )
    monkeypatch.setattr(tool, "propagate_grid", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(tool, "observe_grid", lambda *_args, **_kwargs: observed)
    monkeypatch.setattr(tool, "doppler_shift_hz", lambda _carrier, rate: rate)

    result = tool._sky_rate_evaluations(
        catalogue,
        SimpleNamespace(),
        track_midpoint_utc_ns=2_000_000_000,
        rf_frequency_hz=12e9,
        horizon_deg=10.0,
        shifts_s=np.asarray([0.0]),
    )

    assert [item["catalog_number"] for item in result[0]["satellites"]] == [101, 303]
    assert result[0]["satellites"][0]["predicted_rate_hz_s"] == pytest.approx(-100.0)
    assert result[0]["satellites"][1]["zenith_angle_deg"] == pytest.approx(20.0)


def test_linear_match_scores_true_time_against_wrong_time_nulls(monkeypatch) -> None:
    tool = _tool()
    fit = tool.LinearRadioFit(5.0, 0.0, -3_000.0, 10.0, 1.0, -3_000.0, -3_000.0, 10)
    track = SimpleNamespace(
        start_s=0.0,
        end_s=10.0,
        path=SimpleNamespace(rf_frequency_hz=12e9),
    )

    def satellite(catalog_number: int, rate: float) -> dict[str, float | int | str]:
        return {
            "catalogue_index": catalog_number,
            "catalog_number": catalog_number,
            "object_name": f"STARLINK-{catalog_number}",
            "elevation_deg": 70.0,
            "zenith_angle_deg": 20.0,
            "predicted_rate_hz_s": rate,
            "element_age_s": 0.0,
        }

    monkeypatch.setattr(
        tool,
        "_sky_rate_evaluations",
        lambda *_args, **_kwargs: (
            {"time_shift_s": -30.0, "satellites": [satellite(1, -2_800.0)]},
            {"time_shift_s": 0.0, "satellites": [satellite(2, -2_990.0), satellite(3, -2_900.0)]},
            {"time_shift_s": 30.0, "satellites": [satellite(4, -2_850.0)]},
        ),
    )

    result = tool._analyze_linear_rate_match(
        track,
        fit,
        SimpleNamespace(),
        SimpleNamespace(),
        dwell_start_ns=0,
        horizon_deg=10.0,
    )

    assert result["top_candidates"][0]["catalog_number"] == 2
    assert result["best_absolute_rate_error_hz_s"] == pytest.approx(10.0)
    assert result["true_time_empirical_p"] == pytest.approx(1 / 3)
    assert result["true_time_rank_among_true_and_null"] == 1


def test_report_entry_point_uses_only_linear_dwell_path() -> None:
    tool = _tool()

    main_source = inspect.getsource(tool.main)
    dwell_source = inspect.getsource(tool._linear_dwell_document)

    assert "_linear_dwell_document" in main_source
    assert "\n            _dwell_document(" not in main_source
    assert "_track_rate(" not in dwell_source
    assert "_plot_overlay(" not in dwell_source
    assert "_analyze_track_matches(" not in dwell_source
