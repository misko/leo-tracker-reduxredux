from __future__ import annotations

import math

import numpy as np
import pytest

from leo.analysis.research.pilot_locklet_prototypes import (
    LockletState,
    PiecewiseLockletConfig,
    PilotFrameObservation,
    RobustBlockConfig,
    compare_radio_only_polynomials,
    robust_blockwise_cfo_rate,
    track_piecewise_locklets,
)


def _observations(
    times: np.ndarray,
    cfo: np.ndarray,
    *,
    sigma_hz: float = 20.0,
    support: np.ndarray | None = None,
    phases: np.ndarray | None = None,
) -> tuple[PilotFrameObservation, ...]:
    support_values = np.ones(len(times)) if support is None else support
    return tuple(
        PilotFrameObservation(
            time_s=float(time_s),
            cfo_hz=float(cfo_hz),
            cfo_sigma_hz=sigma_hz,
            support=float(support_value),
            phase_modulo_pi_rad=None if phases is None else float(phases[index] % np.pi),
            phase_sigma_rad=None if phases is None else 0.08,
        )
        for index, (time_s, cfo_hz, support_value) in enumerate(
            zip(times, cfo, support_values, strict=True)
        )
    )


def test_robust_blockwise_rate_resists_frame_and_whole_block_outliers() -> None:
    generator = np.random.default_rng(0xC0FFEE)
    times = np.arange(0.0, 4.0, 0.00125)
    true_intercept = 81_000.0
    true_rate = -2_650.0
    clean = true_intercept + true_rate * times
    measured = clean + generator.normal(0.0, 24.0, len(times))

    # Contaminate isolated frames and every frame in two complete blocks.  The
    # latter exercises the second robust layer, not merely within-block Huber.
    isolated = generator.choice(len(times), size=150, replace=False)
    measured[isolated] += generator.choice((-1.0, 1.0), len(isolated)) * 8_000.0
    measured[(times >= 1.50) & (times < 1.575)] += 4_000.0
    measured[(times >= 3.00) & (times < 3.075)] -= 5_000.0
    observations = _observations(times, measured, sigma_hz=24.0)
    config = RobustBlockConfig(block_duration_s=0.075, minimum_observations_per_block=20)

    fit = robust_blockwise_cfo_rate(observations, config=config)
    naive_rate = float(np.polyfit(times, measured, 1)[0])

    assert len(fit.blocks) == 54
    assert fit.rate_at_reference_hz_s == pytest.approx(true_rate, abs=12.0)
    assert abs(fit.rate_at_reference_hz_s - true_rate) < abs(naive_rate - true_rate)
    assert 0.0 < fit.rate_sigma_at_reference_hz_s < 20.0
    assert fit.effective_block_count < len(fit.blocks)
    assert sum(weight < 0.5 for weight in fit.robust_weights) >= 2


def test_empirical_covariance_and_prediction_coverage_are_not_overconfident() -> None:
    generator = np.random.default_rng(0x51A6A)
    times = np.arange(0.0, 6.0, 0.00125)
    true_rate = 1_850.0
    measured = 120_000.0 + true_rate * times + generator.normal(0.0, 35.0, len(times))
    # Correlated block offsets are the failure mode that frame-independent
    # covariance misses.  The outer residual calibration must absorb them.
    block = np.floor(times / 0.075).astype(int)
    block_offsets = generator.normal(0.0, 90.0, block.max() + 1)
    measured += block_offsets[block]
    observations = _observations(times, measured, sigma_hz=35.0)

    fit = robust_blockwise_cfo_rate(
        observations,
        config=RobustBlockConfig(
            block_duration_s=0.075,
            minimum_observations_per_block=20,
        ),
    )

    error = abs(fit.rate_at_reference_hz_s - true_rate)
    assert fit.reduced_chi_squared > 10.0
    assert error <= 3.0 * fit.rate_sigma_at_reference_hz_s
    assert 0.45 <= fit.one_sigma_coverage <= 0.85
    assert 0.85 <= fit.two_sigma_coverage <= 1.0


def test_polynomial_comparison_uses_identical_blocks_and_prefers_curvature() -> None:
    generator = np.random.default_rng(0xB10C)
    times = np.arange(0.0, 5.0, 0.00125)
    relative = times - 2.5
    measured = 70_000.0 - 2_100.0 * relative + 180.0 * relative**2
    measured += generator.normal(0.0, 22.0, len(times))
    observations = _observations(times, measured, sigma_hz=22.0)

    result = compare_radio_only_polynomials(
        observations,
        config=RobustBlockConfig(minimum_observations_per_block=20),
    )

    assert result.preferred_degree_by_bic == 2
    assert {row.block_count for row in result.rows} == {len(result.shared_blocks)}
    assert all(row.fit.blocks is result.shared_blocks for row in result.rows)
    degree_one, degree_two = result.rows[1:]
    assert degree_two.full_rms_hz < degree_one.full_rms_hz / 5.0
    assert degree_two.fit.coefficients_hz[2] == pytest.approx(180.0, abs=3.0)


def test_piecewise_tracker_coasts_over_outlier_then_reacquires_after_change_and_gap() -> None:
    generator = np.random.default_rng(0x10CC)
    dt_s = 0.002
    first_times = np.arange(0.0, 0.160, dt_s)
    second_times = np.arange(0.160, 0.320, dt_s)
    gap_times = np.arange(0.320, 0.370, dt_s)
    third_times = np.arange(0.370, 0.530, dt_s)
    times = np.concatenate((first_times, second_times, gap_times, third_times))
    support = np.ones(len(times))
    support[len(first_times) + len(second_times) : -len(third_times)] = 0.0

    first = 30_000.0 - 1_300.0 * first_times
    # A coherent 1.8 kHz step is a change point, while the isolated 8 kHz
    # corruption in the first episode must only produce a short coast.
    second = 31_800.0 - 1_300.0 * second_times
    third = 28_500.0 + 900.0 * (third_times - third_times[0])
    cfo = np.concatenate((first, second, np.full(len(gap_times), 0.0), third_times * 0.0 + third))
    cfo += generator.normal(0.0, 12.0, len(cfo))
    cfo[25] += 8_000.0
    phases = np.empty(len(times))
    phases[0] = 0.3
    for index in range(1, len(times)):
        phases[index] = phases[index - 1] + 2.0 * math.pi * cfo[index - 1] * (
            times[index] - times[index - 1]
        )
    observations = _observations(times, cfo, sigma_hz=15.0, support=support, phases=phases)

    result = track_piecewise_locklets(
        observations,
        config=PiecewiseLockletConfig(
            acquisition_observations=5,
            maximum_acquisition_gap_s=0.006,
            maximum_coast_s=0.015,
            frequency_gate_sigma=5.0,
            phase_gate_rad=1.2,
            frequency_noise_floor_hz=25.0,
            change_point_confirmations=3,
        ),
    )

    assert len(result.locklets) == 3
    assert result.reacquisition_count == 2
    assert result.change_point_count == 1
    assert result.locklets[0].ended_by_change_point
    assert not result.locklets[1].ended_by_change_point
    assert result.locklets[1].reacquired and result.locklets[2].reacquired
    assert result.locklets[0].rate_hz_s == pytest.approx(-1_300.0, abs=80.0)
    assert result.locklets[1].rate_hz_s == pytest.approx(-1_300.0, abs=80.0)
    assert result.locklets[2].rate_hz_s == pytest.approx(900.0, abs=80.0)
    assert result.decisions[25].state is LockletState.COAST
    assert not result.decisions[25].accepted
    assert any(decision.change_point for decision in result.decisions)
    assert any(decision.state is LockletState.REACQUIRE for decision in result.decisions)


def test_inputs_fail_closed() -> None:
    with pytest.raises(ValueError, match="support"):
        PilotFrameObservation(0.0, 1.0, 1.0, 1.1)
    with pytest.raises(ValueError, match="phase uncertainty"):
        PilotFrameObservation(0.0, 1.0, 1.0, 1.0, phase_modulo_pi_rad=0.1)
    with pytest.raises(ValueError, match="strictly increasing"):
        robust_blockwise_cfo_rate(
            (
                PilotFrameObservation(0.0, 1.0, 1.0, 1.0),
                PilotFrameObservation(0.0, 2.0, 1.0, 1.0),
            )
        )
