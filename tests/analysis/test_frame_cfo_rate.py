from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.research.frame_cfo_rate import (
    FrameCfoProfile,
    FrameCfoRateMethod,
    FrameCfoRateSearchConfig,
    fit_frame_cfo_rate,
    trailing_frame_windows,
)

_GRID_HZ = np.arange(-700.0, 700.1, 5.0)
_CFO_ORIGIN_HZ = 100_000.0
_TRUTH_CFO_HZ = 100_120.0
_TRUTH_RATE_HZ_S = -1_875.0


def _curve(center_hz: float, *, sigma_hz: float) -> np.ndarray:
    return -0.5 * ((_GRID_HZ - center_hz) / sigma_hz) ** 2


def _profiles(
    *,
    frame_count: int = 31,
    continuity_segment: int = 0,
    truth_cfo_hz: float = _TRUTH_CFO_HZ,
    truth_rate_hz_s: float = _TRUTH_RATE_HZ_S,
) -> tuple[FrameCfoProfile, ...]:
    times = np.arange(frame_count, dtype=float) / 750.0
    reference_time_s = float(np.mean(times))
    control = np.full_like(_GRID_HZ, -8.0)
    output = []
    for index, time_s in enumerate(times):
        residual_hz = truth_cfo_hz + truth_rate_hz_s * (time_s - reference_time_s) - _CFO_ORIGIN_HZ
        output.append(
            FrameCfoProfile(
                frame_start_sample=index * 3_333,
                reference_time_s=float(time_s),
                continuity_segment=continuity_segment,
                cfo_origin_hz=_CFO_ORIGIN_HZ,
                residual_grid_hz=_GRID_HZ,
                even_exact_log_likelihood=_curve(residual_hz, sigma_hz=35.0),
                even_control_log_likelihood=control,
                odd_exact_log_likelihood=_curve(residual_hz, sigma_hz=40.0),
                odd_control_log_likelihood=control,
            )
        )
    return tuple(output)


def _config() -> FrameCfoRateSearchConfig:
    return FrameCfoRateSearchConfig(
        cfo_half_width_hz=350.0,
        rate_half_width_hz_s=7_000.0,
        coarse_cfo_step_hz=25.0,
        coarse_rate_step_hz_s=250.0,
        fine_cfo_step_hz=5.0,
        fine_rate_step_hz_s=25.0,
        occupancy_outlier_fraction=0.20,
        minimum_frames=10,
        minimum_span_s=0.012,
    )


def _fit(
    frames: tuple[FrameCfoProfile, ...],
    method: FrameCfoRateMethod,
):
    return fit_frame_cfo_rate(
        frames,
        initial_cfo_hz=_CFO_ORIGIN_HZ,
        initial_rate_hz_s=0.0,
        method=method,
        config=_config(),
    )


def test_summed_profile_recovers_the_joint_cfo_rate_objective() -> None:
    result = _fit(_profiles(), FrameCfoRateMethod.SUMMED_PROFILE)

    assert result.cfo_hz == pytest.approx(_TRUTH_CFO_HZ, abs=2.5)
    assert result.rate_hz_s == pytest.approx(_TRUTH_RATE_HZ_S, abs=12.5)
    assert result.conditional_rate_sigma_hz_s is not None
    assert result.conditional_rate_sigma_hz_s > 0.0
    assert result.even_exact_minus_control > 100.0
    assert result.odd_exact_minus_control > 100.0
    assert result.odd_cfo_rms_hz < 1.0
    assert not result.cfo_search_boundary
    assert not result.rate_search_boundary
    assert result.profile_support_complete
    assert result.fit_symbols == "even Qin"
    assert result.validation_symbols == "odd Qin"
    assert not result.carrier_phase_connected
    assert not result.odd_symbols_influenced_fit


def test_odd_and_control_profiles_cannot_change_the_even_trained_fit() -> None:
    frames = _profiles()
    baseline = _fit(frames, FrameCfoRateMethod.SUMMED_PROFILE)
    times = np.asarray([frame.reference_time_s for frame in frames])
    reference_time_s = float(np.mean(times))
    poisoned = tuple(
        replace(
            frame,
            even_control_log_likelihood=_curve(500.0, sigma_hz=3.0),
            odd_exact_log_likelihood=_curve(
                -300.0 + 6_000.0 * (frame.reference_time_s - reference_time_s),
                sigma_hz=2.0,
            ),
            odd_control_log_likelihood=_curve(-500.0, sigma_hz=4.0),
        )
        for frame in frames
    )

    changed = _fit(poisoned, FrameCfoRateMethod.SUMMED_PROFILE)

    assert changed.cfo_hz == baseline.cfo_hz
    assert changed.rate_hz_s == baseline.rate_hz_s
    assert changed.training_objective == baseline.training_objective
    assert changed.conditional_rate_sigma_hz_s == baseline.conditional_rate_sigma_hz_s
    assert changed.frame_count == baseline.frame_count
    assert changed.span_s == baseline.span_s
    assert changed.odd_cfo_rms_hz > baseline.odd_cfo_rms_hz + 100.0
    assert changed.even_exact_minus_control != baseline.even_exact_minus_control
    assert changed.odd_exact_minus_control != baseline.odd_exact_minus_control
    assert not changed.odd_symbols_influenced_fit


def test_glrt_context_discloses_upstream_odd_qin_influence() -> None:
    result = _fit(_profiles(), FrameCfoRateMethod.GLRT_RATE)

    assert result.fit_symbols == "upstream GLRT64 (even + odd Qin); local even-Qin intercept"
    assert result.validation_symbols == (
        "odd Qin response (not fit-withheld from upstream GLRT64 slope)"
    )
    assert result.odd_symbols_influenced_fit


def test_occupancy_mixture_rejects_a_narrow_minority_outlier_track() -> None:
    frame_count = 31
    times = np.arange(frame_count, dtype=float) / 750.0
    reference_time_s = float(np.mean(times))
    control = np.full_like(_GRID_HZ, -8.0)
    frames = []
    for index, time_s in enumerate(times):
        truth_residual_hz = 120.0 - 1_800.0 * (time_s - reference_time_s)
        outlier_residual_hz = -80.0 + 5_000.0 * (time_s - reference_time_s)
        frames.append(
            FrameCfoProfile(
                frame_start_sample=index * 3_333,
                reference_time_s=float(time_s),
                continuity_segment=0,
                cfo_origin_hz=_CFO_ORIGIN_HZ,
                residual_grid_hz=_GRID_HZ,
                even_exact_log_likelihood=(
                    _curve(outlier_residual_hz, sigma_hz=2.0)
                    if index < 5
                    else _curve(truth_residual_hz, sigma_hz=45.0)
                ),
                even_control_log_likelihood=control,
                odd_exact_log_likelihood=_curve(truth_residual_hz, sigma_hz=25.0),
                odd_control_log_likelihood=control,
            )
        )

    ordinary = _fit(tuple(frames), FrameCfoRateMethod.SUMMED_PROFILE)
    mixture = _fit(tuple(frames), FrameCfoRateMethod.OCCUPANCY_MIXTURE)

    assert abs(mixture.rate_hz_s + 1_800.0) <= 100.0
    assert abs(ordinary.rate_hz_s + 1_800.0) > 3_000.0
    assert mixture.odd_cfo_rms_hz < 5.0
    assert ordinary.odd_cfo_rms_hz > 100.0


def test_rate_fit_rejects_cross_segment_and_inconsistent_profile_support() -> None:
    frames = list(_profiles())
    frames[-1] = replace(frames[-1], continuity_segment=1)
    with pytest.raises(ValueError, match="continuity segment"):
        _fit(tuple(frames), FrameCfoRateMethod.SUMMED_PROFILE)

    frames = list(_profiles())
    shifted_grid = frames[-1].residual_grid_hz + 1.0
    frames[-1] = replace(frames[-1], residual_grid_hz=shifted_grid)
    with pytest.raises(ValueError, match="share one residual-frequency grid"):
        _fit(tuple(frames), FrameCfoRateMethod.SUMMED_PROFILE)


def test_trailing_windows_are_causal_and_stable_when_future_frames_arrive() -> None:
    duration_s = 0.020
    base_frames = _profiles(frame_count=40)
    extended_frames = _profiles(frame_count=45)

    base = trailing_frame_windows(base_frames, duration_s=duration_s, minimum_frames=10)
    extended = trailing_frame_windows(
        extended_frames,
        duration_s=duration_s,
        minimum_frames=10,
    )

    def signatures(
        windows: tuple[tuple[FrameCfoProfile, ...], ...],
    ) -> tuple[tuple[int, int, int], ...]:
        return tuple(
            (window[0].frame_start_sample, window[-1].frame_start_sample, len(window))
            for window in windows
        )

    base_signatures = signatures(base)
    extended_past = tuple(
        signature
        for signature in signatures(extended)
        if signature[1] <= base_frames[-1].frame_start_sample
    )
    assert base_signatures == extended_past
    assert len({window[-1].frame_start_sample for window in base}) == len(base)
    assert all(
        frame.reference_time_s <= window[-1].reference_time_s for window in base for frame in window
    )
    assert all(
        duration_s - 2.0 / 750.0
        <= window[-1].reference_time_s - window[0].reference_time_s
        <= duration_s + 1e-12
        for window in base
    )


@pytest.mark.parametrize(
    ("grid", "curve", "message"),
    (
        (np.asarray([-1.0, 0.0, 0.0]), np.zeros(3), "strictly increasing"),
        (np.asarray([-1.0, 0.0, 1.0]), np.zeros(2), "match the common grid"),
        (np.asarray([-1.0, 0.0, 1.0]), np.asarray([0.0, np.nan, 0.0]), "finite"),
    ),
)
def test_frame_profile_rejects_invalid_grids_and_curves(
    grid: np.ndarray,
    curve: np.ndarray,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        FrameCfoProfile(
            frame_start_sample=0,
            reference_time_s=0.0,
            continuity_segment=0,
            cfo_origin_hz=0.0,
            residual_grid_hz=grid,
            even_exact_log_likelihood=curve,
            even_control_log_likelihood=np.zeros_like(grid),
            odd_exact_log_likelihood=np.zeros_like(grid),
            odd_control_log_likelihood=np.zeros_like(grid),
        )


def test_rate_fit_fails_closed_on_insufficient_support_and_nonfinite_seed() -> None:
    with pytest.raises(ValueError, match="insufficient frames"):
        _fit(_profiles(frame_count=9), FrameCfoRateMethod.SUMMED_PROFILE)

    with pytest.raises(ValueError, match="initial CFO and rate must be finite"):
        fit_frame_cfo_rate(
            _profiles(),
            initial_cfo_hz=np.nan,
            initial_rate_hz_s=0.0,
            method=FrameCfoRateMethod.SUMMED_PROFILE,
            config=_config(),
        )
