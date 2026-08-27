from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.research.trajectory_qin_injection import (
    PiecewiseLinearCfoTrajectory,
    TrajectoryQinInjectionConfig,
    evaluate_exact_qin_trajectory_frames,
    inject_exact_qin_trajectory,
)


def _config(**changes: object) -> TrajectoryQinInjectionConfig:
    config = TrajectoryQinInjectionConfig(
        scenario_id="orbit-truth-test",
        sample_rate_hz=2_500_000,
        sample_count=10_000,
        frame_count=3,
        snr_db=20.0,
        frame_occupancy=1.0,
        seed=731,
        frame_cfo_search_half_width_hz=2_500.0,
        profile_step_hz=50.0,
        minimum_exact_coherence=0.02,
        minimum_coherence_margin=0.0,
    )
    return replace(config, **changes)  # type: ignore[arg-type]


def _trajectory() -> PiecewiseLinearCfoTrajectory:
    return PiecewiseLinearCfoTrajectory(
        trajectory_id="response-free-orbit-curve",
        knot_times_s=(-0.01, 0.0, 0.01, 0.02),
        knot_cfo_hz=(99_900.0, 100_000.0, 100_200.0, 100_500.0),
    )


def test_piecewise_linear_phase_is_exact_and_differentiates_to_cfo() -> None:
    trajectory = PiecewiseLinearCfoTrajectory(
        trajectory_id="analytic",
        knot_times_s=(0.0, 1.0, 2.0),
        knot_cfo_hz=(0.0, 2.0, 0.0),
    )

    np.testing.assert_allclose(
        trajectory.phase_cycles((0.0, 0.5, 1.0, 1.5, 2.0)), (0, 0.25, 1, 1.75, 2)
    )
    center = np.linspace(0.01, 1.99, 25)
    step = 1e-6
    numerical = (
        trajectory.phase_cycles(center + step) - trajectory.phase_cycles(center - step)
    ) / (2 * step)
    np.testing.assert_allclose(numerical, trajectory.cfo_hz(center), rtol=0.0, atol=2e-6)


def test_trajectory_rejects_noncanonical_or_out_of_support_queries() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        PiecewiseLinearCfoTrajectory("bad", (0.0, 0.0), (1.0, 2.0))
    with pytest.raises(ValueError, match="outside"):
        _trajectory().phase_cycles((-0.011,))


def test_exact_qin_trajectory_uses_public_parity_split_measurement() -> None:
    generator = np.random.default_rng(73)
    background = np.asarray(
        1e-3 * (generator.normal(size=10_000) + 1j * generator.normal(size=10_000)),
        dtype=np.complex64,
    )

    injected, occupancy, diagnostics = inject_exact_qin_trajectory(
        background,
        _trajectory(),
        _config(),
    )
    evidence = evaluate_exact_qin_trajectory_frames(
        injected,
        occupancy,
        _trajectory(),
        _config(),
        absolute_span_start_sample=20_000_000,
    )

    assert diagnostics.occupied_frame_count == 3
    assert evidence[0].status == "incomplete_guard"
    assert all(item.training_supported for item in evidence[1:])
    assert all(item.even_canonical_cfo_hz is not None for item in evidence[1:])
    assert all(item.odd_canonical_cfo_hz is not None for item in evidence[1:])
    for item in evidence[1:]:
        assert item.even_canonical_cfo_hz is not None
        assert abs(item.even_canonical_cfo_hz - item.receiver_truth_cfo_hz) <= 75.0


def test_occupancy_and_injected_bytes_are_deterministic() -> None:
    background = np.full(10_000, 1e-3 + 2e-3j, dtype=np.complex64)
    config = _config(frame_occupancy=2 / 3)

    first = inject_exact_qin_trajectory(background, _trajectory(), config)
    second = inject_exact_qin_trajectory(background, _trajectory(), config)

    np.testing.assert_array_equal(first[0], second[0])
    np.testing.assert_array_equal(first[1], second[1])
    assert first[2] == second[2]
    assert int(np.sum(first[1])) == 2


def test_background_and_lattice_fail_closed_before_injection() -> None:
    with pytest.raises(ValueError, match="exact configured span"):
        inject_exact_qin_trajectory(np.ones(9_999, dtype=np.complex64), _trajectory(), _config())
    with pytest.raises(ValueError, match="lattice exceeds"):
        inject_exact_qin_trajectory(
            np.ones(10_000, dtype=np.complex64),
            _trajectory(),
            _config(frame_count=4),
        )
