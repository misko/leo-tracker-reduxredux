from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.starlink.adaptive_dual_rx_phase import SYMBOL_ALIAS_HZ
from leo.analysis.starlink.adaptive_dual_rx_phase_extract import (
    ReceiverPhaseSeed,
    extract_dual_receiver_phase,
    extract_dual_receiver_phase_branch_lifted,
    extract_dual_receiver_phase_with_offset_authority,
    shared_frame_starts,
)
from leo.analysis.starlink.templates import FRAME_RATE_HZ, qin_edge_pilot_frame

RATE = 2_500_000.0


def _synthetic_dual_iq() -> tuple[np.ndarray, int, tuple[ReceiverPhaseSeed, ReceiverPhaseSeed]]:
    template = np.asarray(qin_edge_pilot_frame(RATE, "lower"), np.complex128)
    epoch = 40_000
    starts = shared_frame_starts(100_000, RATE, epoch, frame_radius=9)
    references = (epoch - 316.63, epoch + 210.58)
    acquired = (-82_000.0, -701_000.0)
    actual = (-82_137.25, -701_296.75)
    receiver_phase = (-0.37, 0.91)
    common = np.random.default_rng(721).uniform(-np.pi, np.pi, len(starts))
    iq = np.zeros((100_000, 2), dtype=np.complex128)
    local = np.arange(len(template))
    for frame_index, start in enumerate(starts):
        absolute = start + local
        for receiver in (0, 1):
            phase = (
                common[frame_index]
                + receiver_phase[receiver]
                + 2 * np.pi * actual[receiver] * (absolute - references[receiver]) / RATE
            )
            iq[absolute, receiver] += template * np.exp(1j * phase)
    seeds = tuple(
        ReceiverPhaseSeed(acquired_cfo_hz=acquired[index], reference_sample=references[index])
        for index in (0, 1)
    )
    return iq, epoch, seeds  # type: ignore[return-value]


def test_extracts_phase_from_same_indices_and_restores_cfo_once() -> None:
    iq, epoch, seeds = _synthetic_dual_iq()

    result = extract_dual_receiver_phase(iq, RATE, "lower", epoch, seeds)

    assert result.receivers[0].frame_starts == result.receivers[1].frame_starts
    assert result.relative_frequency_hz == pytest.approx(-619159.5, abs=0.08)
    assert result.relative_frequency_standard_error_hz < 0.1
    expected = (
        0.91
        - (-0.37)
        + 2
        * np.pi
        * (
            -701296.75 * (result.center_sample - seeds[1].reference_sample)
            - -82137.25 * (result.center_sample - seeds[0].reference_sample)
        )
        / RATE
    )
    error_deg = np.degrees(np.angle(np.exp(1j * (result.wrapped_phase_rad - expected))))
    assert error_deg == pytest.approx(0.0, abs=0.04)

    assert result.resultant_length > 0.999999
    assert min(r.exact_to_control_power_ratio for r in result.receivers) > 10


def test_receiver_swap_negates_local_observable() -> None:
    iq, epoch, seeds = _synthetic_dual_iq()
    forward = extract_dual_receiver_phase(iq, RATE, "lower", epoch, seeds)
    reverse = extract_dual_receiver_phase(iq[:, ::-1], RATE, "lower", epoch, seeds[::-1])

    assert reverse.relative_frequency_hz == pytest.approx(-forward.relative_frequency_hz)
    assert np.angle(np.exp(1j * (reverse.wrapped_phase_rad + forward.wrapped_phase_rad))) == (
        pytest.approx(0.0, abs=1e-10)
    )


@pytest.mark.parametrize(
    ("receiver_residuals_hz", "expected_alias_index"),
    [
        ((0.0, 1_000.0), 1),
        ((500.0, -750.0), -2),
        ((10_000.0, 12_000.0), 3),
    ],
)
def test_branch_lifted_extractor_uses_within_frame_frequency_authority(
    receiver_residuals_hz: tuple[float, float], expected_alias_index: int
) -> None:
    template = np.asarray(qin_edge_pilot_frame(RATE, "lower"), np.complex128)
    epoch = 40_000
    starts = shared_frame_starts(100_000, RATE, epoch, frame_radius=9)
    references = (epoch - 316.63, epoch + 210.58)
    acquired = (-80_000.0, -700_000.0)
    actual = tuple(acquired[index] + receiver_residuals_hz[index] for index in (0, 1))
    receiver_phase = (-0.37, 0.91)
    rng = np.random.default_rng(22)
    common = rng.uniform(-np.pi, np.pi, len(starts))
    amplitudes = np.linspace(0.2, 2.0, len(starts))
    iq = np.zeros((100_000, 2), dtype=np.complex128)
    local = np.arange(len(template))
    for frame_index, start in enumerate(starts):
        absolute = start + local
        for receiver in (0, 1):
            phase = (
                common[frame_index]
                + receiver_phase[receiver]
                + 2 * np.pi * actual[receiver] * (absolute - references[receiver]) / RATE
            )
            iq[absolute, receiver] += (
                amplitudes[frame_index] * (1 + 0.2 * receiver) * template * np.exp(1j * phase)
            )
    iq += 0.01 * (rng.normal(size=iq.shape) + 1j * rng.normal(size=iq.shape))
    seeds = tuple(
        ReceiverPhaseSeed(acquired_cfo_hz=acquired[index], reference_sample=references[index])
        for index in (0, 1)
    )

    legacy = extract_dual_receiver_phase(iq, RATE, "lower", epoch, seeds)  # type: ignore[arg-type]
    result = extract_dual_receiver_phase_branch_lifted(
        iq,
        RATE,
        "lower",
        epoch,
        seeds,  # type: ignore[arg-type]
    )
    strided = extract_dual_receiver_phase_branch_lifted(
        iq,
        RATE,
        "lower",
        epoch,
        seeds,  # type: ignore[arg-type]
        symbol_indices=np.arange(2, 66, 2),
    )

    expected_frequency_hz = actual[1] - actual[0]
    assert legacy.frame_frequency_branch_lift is None
    assert abs(legacy.relative_frequency_hz - expected_frequency_hz) >= 749.0
    assert result.relative_frequency_hz == pytest.approx(expected_frequency_hz, abs=0.02)
    assert strided.relative_frequency_hz == pytest.approx(expected_frequency_hz, abs=0.04)
    resolution = result.frame_frequency_branch_lift
    assert resolution is not None
    assert resolution.selected_frame_alias_index == expected_alias_index
    assert resolution.within_frame_receiver_residual_difference_hz == pytest.approx(
        receiver_residuals_hz[1] - receiver_residuals_hz[0], abs=0.25
    )
    assert abs(resolution.authority_disagreement_hz) < 0.25
    assert resolution.branch_selection_gap_hz > 749.0
    expected_phase = (
        receiver_phase[1]
        - receiver_phase[0]
        + 2
        * np.pi
        * (
            actual[1] * (result.center_sample - references[1])
            - actual[0] * (result.center_sample - references[0])
        )
        / RATE
    )
    phase_error_deg = np.degrees(np.angle(np.exp(1j * (result.wrapped_phase_rad - expected_phase))))
    assert phase_error_deg == pytest.approx(0.0, abs=0.03)
    strided_expected_phase = (
        receiver_phase[1]
        - receiver_phase[0]
        + 2
        * np.pi
        * (
            actual[1] * (strided.center_sample - references[1])
            - actual[0] * (strided.center_sample - references[0])
        )
        / RATE
    )
    strided_phase_error_deg = np.degrees(
        np.angle(np.exp(1j * (strided.wrapped_phase_rad - strided_expected_phase)))
    )
    assert strided_phase_error_deg == pytest.approx(0.0, abs=0.07)


@pytest.mark.parametrize("wrong_alias_hz", [SYMBOL_ALIAS_HZ / 2, SYMBOL_ALIAS_HZ])
def test_offset_authority_recorrelates_a_common_symbol_alias_and_reference(
    wrong_alias_hz: float,
) -> None:
    iq, epoch, original_seeds = _synthetic_dual_iq()
    wrong_rx1_alias = ReceiverPhaseSeed(
        original_seeds[1].acquired_cfo_hz + wrong_alias_hz,
        original_seeds[1].reference_sample,
    )
    supplied_seeds = (original_seeds[0], wrong_rx1_alias)
    actual_hz = (-82_137.25, -701_296.75)
    receiver_offset_hz = actual_hz[1] - actual_hz[0]

    bound = extract_dual_receiver_phase_with_offset_authority(
        iq,
        RATE,
        "lower",
        epoch,
        supplied_seeds,
        receiver_offset_hz,
    )

    result = bound.observation
    assert bound.original_seeds == supplied_seeds
    assert bound.applied_seeds[0].reference_sample == bound.applied_seeds[1].reference_sample
    assert bound.applied_seeds[1].acquired_cfo_hz - bound.applied_seeds[0].acquired_cfo_hz == (
        pytest.approx(receiver_offset_hz)
    )
    assert result.relative_frequency_hz == pytest.approx(receiver_offset_hz, abs=0.08)
    branch = result.frame_frequency_branch_lift
    assert branch is not None
    assert branch.selected_frame_alias_index == 0
    assert abs(branch.authority_disagreement_hz) < 0.08
    expected = (
        0.91
        - (-0.37)
        + 2
        * np.pi
        * (
            actual_hz[1] * (result.center_sample - original_seeds[1].reference_sample)
            - actual_hz[0] * (result.center_sample - original_seeds[0].reference_sample)
        )
        / RATE
    )
    error_deg = np.degrees(np.angle(np.exp(1j * (result.wrapped_phase_rad - expected))))
    assert error_deg == pytest.approx(0.0, abs=0.04)

    shifted_reference = extract_dual_receiver_phase_with_offset_authority(
        iq,
        RATE,
        "lower",
        epoch,
        supplied_seeds,
        receiver_offset_hz,
        common_reference_sample=original_seeds[0].reference_sample + 12_345.67,
    ).observation
    assert shifted_reference.relative_frequency_hz == pytest.approx(
        result.relative_frequency_hz, abs=1e-6
    )
    assert np.angle(
        np.exp(1j * (shifted_reference.wrapped_phase_rad - result.wrapped_phase_rad))
    ) == pytest.approx(0.0, abs=1e-8)

    reverse = extract_dual_receiver_phase_with_offset_authority(
        iq[:, ::-1],
        RATE,
        "lower",
        epoch,
        supplied_seeds[::-1],
        -receiver_offset_hz,
    ).observation
    assert reverse.relative_frequency_hz == pytest.approx(-result.relative_frequency_hz)
    assert np.angle(np.exp(1j * (reverse.wrapped_phase_rad + result.wrapped_phase_rad))) == (
        pytest.approx(0.0, abs=1e-8)
    )


def test_offset_authority_remains_explicit_when_the_supplied_symbol_branch_is_wrong() -> None:
    iq, epoch, seeds = _synthetic_dual_iq()
    rng = np.random.default_rng(87)
    noisy = iq + 0.01 * (rng.normal(size=iq.shape) + 1j * rng.normal(size=iq.shape))
    actual_receiver_offset_hz = -701_296.75 - -82_137.25
    wrong_authority_hz = actual_receiver_offset_hz + SYMBOL_ALIAS_HZ

    bound = extract_dual_receiver_phase_with_offset_authority(
        noisy,
        RATE,
        "lower",
        epoch,
        seeds,
        wrong_authority_hz,
    )

    assert bound.receiver_offset_authority_hz == wrong_authority_hz
    assert abs(bound.observation.relative_frequency_hz - actual_receiver_offset_hz) > 200_000
    # Local pilot coherence cannot certify an externally supplied symbol branch.
    assert bound.observation.resultant_length > 0.95
    assert min(item.exact_to_control_power_ratio for item in bound.observation.receivers) > 10


def test_frame_lattice_is_bounded_and_shared() -> None:
    starts = shared_frame_starts(20_000, RATE, 2_000, frame_radius=9)
    assert np.all(starts >= 0)
    assert np.all(starts + round(RATE / FRAME_RATE_HZ) <= 20_000)
    assert len(starts) < 19


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (np.zeros(20, dtype=np.complex64), "two complex receiver columns"),
        (np.zeros((20, 3), dtype=np.complex64), "two complex receiver columns"),
        (np.zeros((20, 2), dtype=np.float64), "two complex receiver columns"),
    ],
)
def test_rejects_non_dual_complex_iq(values: np.ndarray, message: str) -> None:
    seeds = (ReceiverPhaseSeed(0.0, 0.0), ReceiverPhaseSeed(0.0, 0.0))
    with pytest.raises(ValueError, match=message):
        extract_dual_receiver_phase(values, RATE, "lower", 0, seeds)
