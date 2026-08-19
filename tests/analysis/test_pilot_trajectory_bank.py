from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.starlink import trajectories as trajectory_module
from leo.analysis.starlink.acquisition import (
    NumericalStatus,
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    conditioned_pilot_method_scores,
)
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from leo.analysis.starlink.trajectories import (
    PolynomialTrajectory,
    TrajectoryBankConfig,
    TrajectoryMethodConfig,
    TrajectoryObservation,
    correct_polynomial_cfo,
    default_trajectory_bank_config,
    fit_trajectory_bank,
)


def test_conditioned_detector_family_scores_one_identical_probe() -> None:
    sample_rate_hz = 2_500_000
    frame = qin_edge_pilot_frame(sample_rate_hz, "lower")
    samples = np.tile(frame, 20)[:50_000]

    scores = conditioned_pilot_method_scores(
        samples,
        sample_rate_hz,
        epoch_sample=0,
        acquired_cfo_hz=0.0,
        symbolwise_exact=0.9,
        symbolwise_control=0.1,
        qam_accuracy=0.95,
    )

    assert tuple(item.method for item in scores) == tuple(PilotMethod)
    assert next(item for item in scores if item.method is PilotMethod.ANCHOR8).margin > 0
    assert next(item for item in scores if item.method is PilotMethod.SYMBOLWISE).margin == 0.8
    assert next(item for item in scores if item.method is PilotMethod.QAM_ACCURACY).margin == 0.95


def test_all_methods_get_linear_quadratic_and_cubic_configuration() -> None:
    config = default_trajectory_bank_config()

    assert tuple(item.method for item in config.methods) == tuple(PilotMethod)
    assert config.polynomial_degrees == (1, 2, 3)


def test_trajectory_bank_fits_all_degrees_and_deduplicates_family() -> None:
    observations = tuple(
        TrajectoryObservation(
            f"obs-{index}",
            PilotMethod.GLRT64,
            index * 250_000,
            index * 0.1,
            400_000.0 - 2_000.0 * (index * 0.1) + 20.0 * (index * 0.1) ** 2,
            0.8,
            0.1,
            0.7,
        )
        for index in range(50)
    )
    method = TrajectoryMethodConfig(
        PilotMethod.GLRT64,
        high_gate=0.5,
        local_residual_gate_hz=500.0,
        final_residual_gate_hz=500.0,
        minimum_local_points=5,
        minimum_high_points=2,
        maximum_merge_gap_s=1.1,
        endpoint_gate_hz=1_000.0,
        endpoint_growth_hz_per_s=500.0,
        maximum_slope_difference_hz_per_s=5_000.0,
    )
    result = fit_trajectory_bank(
        observations,
        TrajectoryBankConfig((method,), deduplication_frequency_gate_hz=1_000.0),
    )

    assert {item.polynomial_degree for item in result.trajectories} == {1, 2, 3}
    assert len(result.families) == 1
    assert len(result.families[0].member_trajectory_ids) == 3


def test_polynomial_cfo_correction_integrates_cubic_frequency() -> None:
    sample_rate_hz = 10_000.0
    trajectory = PolynomialTrajectory(
        "trajectory",
        PilotMethod.GLRT64,
        3,
        0.5,
        (5.0, -20.0, 100.0, 750.0),
        0.0,
        1.0,
        ("one", "two"),
        2,
        0.0,
        0.0,
        0.5,
        1,
    )
    times = np.arange(10_000) / sample_rate_hz
    samples = np.exp(2j * np.pi * trajectory.phase_cycles(times))

    corrected = correct_polynomial_cfo(samples, sample_rate_hz, 0, trajectory)

    assert np.max(np.abs(corrected - 1.0)) < 1e-12


def test_null_noise_and_tone_controls_remain_finite_candidate_only_evidence() -> None:
    sample_rate_hz = 2_500_000.0
    count = 14_000
    indexes = np.arange(count)
    generator = np.random.default_rng(20260819)
    controls = {
        "zero": np.zeros(count, dtype=np.complex128),
        "noise": generator.normal(size=count) + 1j * generator.normal(size=count),
        "tone": np.exp(2j * np.pi * 137_000.0 * indexes / sample_rate_hz),
    }
    calibration = ReceiverFrequencyCalibration("control", 0.0, "4" * 64)
    config = SymbolwiseAcquisitionConfig(maximum_probe_samples=count)

    results = {
        name: acquire_symbolwise(values, sample_rate_hz, calibration, config=config)
        for name, values in controls.items()
    }

    assert results["zero"].status is NumericalStatus.NO_RESULT
    assert results["zero"].candidates == ()
    assert all(result.candidate_only for result in results.values())
    for name in ("noise", "tone"):
        result = results[name]
        assert result.status is NumericalStatus.COMPLETE
        assert result.winner is not None
        assert all(
            np.isfinite(value)
            for candidate in result.candidates
            for value in (
                candidate.coarse_score,
                candidate.acquire_score,
                candidate.verify_score,
                candidate.conditioned_exact_score,
                candidate.conditioned_control_score,
                candidate.verify_minus_control_margin,
            )
        )
    assert results["noise"].winner.verify_minus_control_margin < 0.05
    assert results["tone"].winner.verify_minus_control_margin < 0.0


def test_cfo_feedback_controls_reject_wrong_unrelated_zero_gain_and_substitution() -> None:
    sample_rate_hz = 10_000.0
    count = 10_000
    times = np.arange(count) / sample_rate_hz
    expected = _control_trajectory("expected", (37.0, -140.0, 900.0))
    wrong_sign = _control_trajectory(
        "wrong-sign",
        tuple(-value for value in expected.coefficients_hz),
    )
    unrelated = _control_trajectory("unrelated", (-19.0, 81.0, -1_217.0))
    zero = _control_trajectory("zero", (0.0, 0.0, 0.0))
    substitute = _control_trajectory("substitute", (-53.0, 211.0, 1_733.0))
    samples = np.exp(2j * np.pi * expected.phase_cycles(times))
    substituted_samples = np.exp(2j * np.pi * substitute.phase_cycles(times))

    baseline = float(abs(np.mean(samples)))
    gains = {
        "expected": float(
            abs(np.mean(correct_polynomial_cfo(samples, sample_rate_hz, 0, expected)))
        ),
        "wrong-sign": float(
            abs(np.mean(correct_polynomial_cfo(samples, sample_rate_hz, 0, wrong_sign)))
        ),
        "unrelated": float(
            abs(np.mean(correct_polynomial_cfo(samples, sample_rate_hz, 0, unrelated)))
        ),
        "zero": float(abs(np.mean(correct_polynomial_cfo(samples, sample_rate_hz, 0, zero)))),
        "sample-substitution": float(
            abs(
                np.mean(
                    correct_polynomial_cfo(
                        substituted_samples,
                        sample_rate_hz,
                        0,
                        expected,
                    )
                )
            )
        ),
    }

    assert all(np.isfinite(value) for value in (baseline, *gains.values()))
    assert gains["expected"] == pytest.approx(1.0, abs=1e-12)
    assert gains["zero"] == pytest.approx(baseline, abs=1e-15)
    assert gains["wrong-sign"] < 0.02
    assert gains["unrelated"] < 0.02
    assert gains["sample-substitution"] < 0.02
    assert gains["expected"] - baseline > 0.95


def _control_trajectory(
    trajectory_id: str,
    coefficients_hz: tuple[float, float, float],
) -> PolynomialTrajectory:
    return PolynomialTrajectory(
        trajectory_id,
        PilotMethod.GLRT64,
        2,
        0.5,
        coefficients_hz,
        0.0,
        1.0,
        ("control-0", "control-1"),
        2,
        0.0,
        0.0,
        0.5,
        1,
    )


def test_family_representative_prefers_coverage_before_raw_bic() -> None:
    config = TrajectoryBankConfig((TrajectoryMethodConfig(PilotMethod.GLRT64, high_gate=0.5),))
    short = PolynomialTrajectory(
        "short",
        PilotMethod.GLRT64,
        1,
        0.5,
        (-1_000.0, 400_000.0),
        0.0,
        1.0,
        tuple(f"short-{index}" for index in range(10)),
        10,
        100.0,
        10.0,
        0.5,
        1,
    )
    long = PolynomialTrajectory(
        "long",
        PilotMethod.GLRT64,
        2,
        2.0,
        (0.0, -1_000.0, 398_500.0),
        0.0,
        4.0,
        tuple(f"long-{index}" for index in range(40)),
        40,
        200.0,
        100.0,
        0.5,
        1,
    )

    families = trajectory_module._trajectory_families((short, long), config)

    assert len(families) == 1
    assert families[0].representative_trajectory_id == "long"
