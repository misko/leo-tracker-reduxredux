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


def test_piecewise_linear_audit_recovers_rates_steps_and_raw_alias_state(monkeypatch) -> None:
    tool = _tool()
    times = np.arange(0.0, 40.0, 0.25)
    rates = (-1_000.0, -2_000.0, -3_000.0, -4_000.0)
    jumps = (-5_000.0, -6_000.0, -7_000.0)
    values = np.empty_like(times)
    intercept = 20_000.0
    previous_boundary_value = None
    for index, (start, end, rate) in enumerate(
        zip((0.0, 10.0, 20.0, 30.0), (10.0, 20.0, 30.0, 40.0), rates, strict=True)
    ):
        selected = (times >= start) & (times < end)
        if index:
            assert previous_boundary_value is not None
            intercept = previous_boundary_value + jumps[index - 1]
        values[selected] = intercept + rate * (times[selected] - start)
        previous_boundary_value = intercept + rate * (end - start)
    values += 0.2 * np.sin(times)
    observations = tool.TrackObservations(times, values)
    canonical = [
        SimpleNamespace(
            observation_id=f"observation-{index}",
            alias_index=0,
            raw_cfo_hz=float(value),
            component_cfo_hz=float(value),
        )
        for index, value in enumerate(values)
    ]
    track = SimpleNamespace(
        row=SimpleNamespace(
            trajectory_id="piecewise-track",
            observation_ids=tuple(item.observation_id for item in canonical),
        ),
        path=SimpleNamespace(dealiased_bank=SimpleNamespace(observations=canonical)),
    )
    monkeypatch.setattr(tool, "_track_observations", lambda _track: observations)

    result = tool._piecewise_linear_radio_analysis(track, (10.0, 20.0, 30.0))

    assert [row["rate_hz_s"] for row in result["segments"]] == pytest.approx(
        rates, abs=0.02
    )
    assert result["frequency_steps_hz"] == pytest.approx(jumps, abs=0.2)
    assert result["piecewise_residual_rms_hz"] < 1.0
    assert result["bic_delta_piecewise_minus_global"] < -100.0
    assert result["alias_audit"]["all_alias_indices_zero"] is True
    assert result["alias_audit"]["raw_equals_component_cfo"] is True


def test_initial_glrt_observations_use_raw_trajectory_membership() -> None:
    tool = _tool()
    detections = []
    wanted_ids = []
    for index, (time_s, cfo_hz) in enumerate(((1.0, 12_000.0), (2.0, 8_000.0))):
        sample_start = 100 * (index + 1)
        wanted_ids.append(
            tool.canonical_digest(
                {
                    "sample_start": sample_start,
                    "candidate_rank": 0,
                    "method": "glrt64",
                }
            )
        )
        detections.append(
            {
                "sample_start": sample_start,
                "time_s": time_s,
                "candidates": [
                    {
                        "rank": 0,
                        "scores": [
                            {"method": "glrt64", "tracking_cfo_hz": cfo_hz},
                            {"method": "anchor8", "tracking_cfo_hz": cfo_hz + 1.0},
                        ],
                    }
                ],
            }
        )
    track = SimpleNamespace(
        start_s=0.25,
        row=SimpleNamespace(start_s=0.0),
        path=SimpleNamespace(
            pilot_scan={"detections": detections},
            trajectory_bank={
                "trajectories": [
                    {
                        "trajectory_id": "raw-linear",
                        "observation_ids": wanted_ids,
                    }
                ]
            },
        ),
    )

    observations = tool._initial_glrt_observations(track, "raw-linear")

    assert observations.time_s.tolist() == pytest.approx([1.25, 2.25])
    assert observations.cfo_hz.tolist() == pytest.approx([12_000.0, 8_000.0])


def test_piecewise_tle_matching_ranks_per_piece_and_one_common_identity(monkeypatch) -> None:
    tool = _tool()
    audit = {
        "segments": [
            {"piece": 1, "start_s": 0.0, "end_s": 2.0, "midpoint_s": 1.0, "rate_hz_s": -1_000.0},
            {"piece": 2, "start_s": 2.0, "end_s": 4.0, "midpoint_s": 3.0, "rate_hz_s": -2_000.0},
        ]
    }

    def skies(*_args, track_midpoint_utc_ns, **_kwargs):
        second_piece = track_midpoint_utc_ns == 3_000_000_000
        return (
            {
                "time_shift_s": 0.0,
                "satellites": [
                    {
                        "catalog_number": 1,
                        "object_name": "STARLINK-COMMON",
                        "elevation_deg": 60.0,
                        "predicted_rate_hz_s": -1_050.0 if not second_piece else -1_950.0,
                    },
                    {
                        "catalog_number": 2,
                        "object_name": "STARLINK-PIECE",
                        "elevation_deg": 55.0,
                        "predicted_rate_hz_s": -1_000.0 if not second_piece else -1_600.0,
                    },
                ],
            },
        )

    monkeypatch.setattr(tool, "_sky_rate_evaluations", skies)

    result = tool._piecewise_tle_rate_matching(
        audit,
        SimpleNamespace(),
        SimpleNamespace(),
        dwell_start_ns=0,
        rf_frequency_hz=11.69e9,
        horizon_deg=10.0,
    )

    assert result["pieces"][0]["top_candidates"][0]["catalog_number"] == 2
    assert result["best_single_satellites"][0]["catalog_number"] == 1
    assert result["best_single_satellites"][0]["rate_error_rms_hz_s"] == pytest.approx(50.0)


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
        azimuth_deg=np.asarray([[10.0, 11.0, 12.0], [20.0, 21.0, 22.0], [30.0, 31.0, 32.0]]),
        elevation_deg=np.asarray([[20.0, 20.0, 20.0], [5.0, 5.0, 5.0], [70.0, 70.0, 70.0]]),
        range_km=np.full((3, 3), 1_000.0),
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
    assert result[0]["satellites"][0]["element_epoch_utc_ns"] == 0
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


def test_range_acceleration_conversion_uses_actual_carrier() -> None:
    tool = _tool()

    acceleration = tool._range_acceleration_m_s2(-6_451.1, 11_690_312_500.0)

    assert acceleration == pytest.approx(165.435, abs=0.001)


def test_rate_distribution_excludes_nonlinear_raw_coefficients(monkeypatch) -> None:
    tool = _tool()
    path = SimpleNamespace(
        label="stream-0/RX1",
        raw_table={
            "trajectories": [
                {
                    "trajectory_id": "linear",
                    "polynomial_degree": 1,
                    "coefficients_hz": [-3_000.0, 10.0],
                    "start_s": 0.0,
                    "end_s": 4.0,
                    "point_count": 20,
                    "residual_rms_hz": 4.0,
                },
                {
                    "trajectory_id": "cubic",
                    "polynomial_degree": 3,
                    "coefficients_hz": [1.0, 2.0, -9_000.0, 10.0],
                    "start_s": 0.0,
                    "end_s": 4.0,
                    "point_count": 20,
                    "residual_rms_hz": 4.0,
                },
            ]
        },
    )
    track = SimpleNamespace(
        path=path,
        row=SimpleNamespace(trajectory_id="retained"),
        duration_s=4.0,
    )
    fit = tool.LinearRadioFit(2.0, 0.0, -3_100.0, 5.0, 1.0, -3_100.0, -3_100.0, 21)
    monkeypatch.setattr(tool, "_fit_linear_radio_track", lambda _track: fit)

    result = tool._linear_rate_distribution((path,), (track,))

    assert [item["trajectory_id"] for item in result["before_replay"]] == ["linear"]
    assert result["before_replay"][0]["rate_hz_s"] == -3_000.0
    assert result["after_replay"][0]["rate_hz_s"] == -3_100.0


def test_causal_snapshot_selection_rejects_post_capture_snapshot() -> None:
    tool = _tool()
    prior = SimpleNamespace(
        collected_utc_ns=1_000,
        digest="sha256:prior",
        byte_size=100,
    )
    future = SimpleNamespace(
        collected_utc_ns=2_100,
        digest="sha256:future",
        byte_size=100,
    )
    archive = SimpleNamespace(list_snapshots=lambda _provider: (prior, future))

    selected = tool._select_causal_space_track_snapshot(
        archive,
        anchor_utc_ns=2_000,
        provider="space-track",
    )

    assert selected is prior
    with pytest.raises(ValueError, match="requires 'space-track'"):
        tool._select_causal_space_track_snapshot(
            archive,
            anchor_utc_ns=2_000,
            provider="huggingface",
        )


def test_report_entry_point_uses_only_linear_dwell_path() -> None:
    tool = _tool()

    main_source = inspect.getsource(tool.main)
    dwell_source = inspect.getsource(tool._linear_dwell_document)

    assert "_linear_dwell_document" in main_source
    assert "\n            _dwell_document(" not in main_source
    assert "_track_rate(" not in dwell_source
    assert "_plot_overlay(" not in dwell_source
    assert "_analyze_track_matches(" not in dwell_source


def test_linear_report_explains_fine_time_scalar_match_limit() -> None:
    tool = _tool()

    source = inspect.getsource(tool._linear_markdown)

    assert "Piecewise-linear test of the −6.45 kHz/s track" in source
    assert "It fits the **single −6451.1 Hz/s scalar" in source
    assert "look-elsewhere effect" in source
    assert "±500 kHz rating" in source


def test_like_unit_multi_plots_share_doppler_rate_axes() -> None:
    tool = _tool()

    for plotter in (
        tool._plot_raw_linear,
        tool._plot_final_linear,
        tool._plot_linear_rate_field,
        tool._plot_linear_rate_time_overlay,
        tool._plot_linear_rate_distribution_by_dwell,
        tool._plot_error_source_audit,
    ):
        assert "sharey=True" in inspect.getsource(plotter)

    null_source = inspect.getsource(tool._plot_linear_null_controls)
    assert 'sharey="col"' in null_source
