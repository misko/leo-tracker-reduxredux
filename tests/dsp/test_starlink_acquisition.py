from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from leo.analysis.starlink import (
    NumericalStatus,
    ReceiverFrequencyCalibration,
    acquire_symbolwise,
    align_known_pilot_frames,
    qin_edge_pilot_frame,
)
from leo.contracts.states import StarlinkEdge

RATE = 2_500_000.0


def test_acquisition_has_no_implicit_edge() -> None:
    with pytest.raises(TypeError, match="edge"):
        acquire_symbolwise(
            np.zeros(14_000, dtype=np.complex64),
            RATE,
            ReceiverFrequencyCalibration("rx", 0.0, "0" * 64),
        )


@pytest.mark.parametrize("source_edge", tuple(StarlinkEdge))
def test_symbolwise_acquisition_discriminates_the_exact_capture_edge(
    source_edge: StarlinkEdge,
) -> None:
    template = qin_edge_pilot_frame(RATE, source_edge)
    samples = np.zeros(14_000, dtype=np.complex128)
    indexes = np.arange(template.size)
    for frame in range(4):
        start = 37 + round(frame * RATE / 750.0)
        samples[start + indexes] += template
    other_edge = StarlinkEdge.UPPER if source_edge is StarlinkEdge.LOWER else StarlinkEdge.LOWER
    calibration = ReceiverFrequencyCalibration("rx", 0.0, "9" * 64)

    matched = acquire_symbolwise(samples, RATE, calibration, edge=source_edge)
    mismatched = acquire_symbolwise(samples, RATE, calibration, edge=other_edge)

    assert matched.winner is not None
    assert matched.winner.refined_epoch_sample == 37
    assert matched.winner.verify_score > 0.99
    assert matched.winner.verify_minus_control_margin > 0.95
    assert mismatched.winner is not None
    assert mismatched.winner.verify_score < 0.05
    assert mismatched.winner.verify_minus_control_margin < 0.03


def _injected(*, epoch: int, residual_cfo_hz: float, receiver_center_hz: float) -> np.ndarray:
    rng = np.random.default_rng(20260819)
    values = (
        rng.normal(0, 0.1 / np.sqrt(2), 14_000) + 1j * rng.normal(0, 0.1 / np.sqrt(2), 14_000)
    ).astype(np.complex128)
    template = qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)
    indexes = np.arange(template.size)
    absolute_cfo_hz = receiver_center_hz + residual_cfo_hz
    for frame in range(4):
        start = epoch + round(frame * RATE / 750.0)
        values[start + indexes] += (
            2 * np.exp(2j * np.pi * absolute_cfo_hz * (start + indexes) / RATE) * template
        )
    return values


def test_receiver_center_is_immutable_and_absolute_is_center_plus_residual() -> None:
    calibration = ReceiverFrequencyCalibration("rx-a", 1_170.0, "1" * 64)
    result = acquire_symbolwise(
        _injected(epoch=37, residual_cfo_hz=200_000.0, receiver_center_hz=1_170.0),
        RATE,
        calibration,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.winner is not None
    assert result.winner.refined_epoch_sample == 37
    assert result.winner.residual_cfo_hz == pytest.approx(200_000.0, abs=1.0)
    assert result.winner.absolute_cfo_hz == pytest.approx(201_170.0, abs=1.0)
    assert result.winner.absolute_cfo_hz == pytest.approx(
        calibration.center_hz + result.winner.residual_cfo_hz,
        abs=1e-12,
    )
    assert result.winner.verify_minus_control_margin == pytest.approx(
        0.9832180261583393,
        abs=1e-10,
    )
    with pytest.raises(FrozenInstanceError):
        calibration.center_hz = 0.0  # type: ignore[misc]


def test_acquisition_retains_alias_basin_until_held_out_adjudication() -> None:
    rng = np.random.default_rng(18)
    values = (
        rng.normal(0, 0.05 / np.sqrt(2), 18_000) + 1j * rng.normal(0, 0.05 / np.sqrt(2), 18_000)
    ).astype(np.complex128)
    template = qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)

    def inject(epoch: int, cfo_hz: float, amplitude: float, *, acquire_only: bool) -> None:
        for frame in range(5):
            start = epoch + round(frame * RATE / 750.0)
            symbols = range(2, 302, 2) if acquire_only else (None,)
            for symbol in symbols:
                indexes = (
                    np.arange(template.size)
                    if symbol is None
                    else np.arange(
                        round(symbol * RATE * 4.4e-6),
                        round((symbol + 1) * RATE * 4.4e-6),
                    )
                )
                if start + indexes[-1] >= values.size:
                    continue
                values[start + indexes] += (
                    amplitude
                    * np.exp(2j * np.pi * cfo_hz * (start + indexes) / RATE)
                    * template[indexes]
                )

    inject(811, -160_000.0, 5.0, acquire_only=True)
    inject(127, 200_000.0, 1.5, acquire_only=False)
    result = acquire_symbolwise(
        values,
        RATE,
        ReceiverFrequencyCalibration("rx-alias", 0.0, "2" * 64),
        edge=StarlinkEdge.LOWER,
    )

    assert result.winner is not None
    assert len(result.candidates) == 8
    assert result.winner.refined_epoch_sample == 127
    assert result.winner.residual_cfo_hz == pytest.approx(200_000.0, abs=35.0)
    alias = next(
        item
        for item in result.candidates
        if item.refined_epoch_sample == 811 and abs(item.residual_cfo_hz + 160_000.0) < 35.0
    )
    assert alias.acquire_score > result.winner.acquire_score
    assert alias.verify_minus_control_margin < result.winner.verify_minus_control_margin


def test_null_and_short_windows_have_explicit_outcomes() -> None:
    calibration = ReceiverFrequencyCalibration("rx-null", 0.0, "3" * 64)
    short = acquire_symbolwise(
        np.zeros(4_000, dtype=np.complex64), RATE, calibration, edge=StarlinkEdge.LOWER
    )
    null = acquire_symbolwise(
        np.zeros(14_000, dtype=np.complex64), RATE, calibration, edge=StarlinkEdge.LOWER
    )

    assert short.status is NumericalStatus.INSUFFICIENT
    assert short.candidates == ()
    assert "two supported frames" in short.reason
    assert null.status is NumericalStatus.NO_RESULT
    assert null.winner is None


def test_known_cfo_alignment_searches_a_full_frame_and_ignores_frame_phase() -> None:
    epoch = round(RATE / 750.0) - 34
    cfo_hz = 23_400.0
    template = qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)
    indexes = np.arange(template.size)
    phases = (0.2, -2.4, 1.7, -0.8, 2.9)
    final_start = epoch + round((len(phases) - 1) * RATE / 750.0)
    samples = np.zeros(final_start + template.size + 2, dtype=np.complex128)
    for frame, phase in enumerate(phases):
        start = epoch + round(frame * RATE / 750.0)
        samples[start + indexes] += template * np.exp(
            1j * (phase + 2 * np.pi * cfo_hz * (start + indexes) / RATE)
        )

    alignment = align_known_pilot_frames(
        samples,
        RATE,
        absolute_cfo_hz=cfo_hz,
        edge=StarlinkEdge.LOWER,
        nominal_epoch_sample=0,
    )

    assert alignment.status is NumericalStatus.COMPLETE
    assert alignment.epoch_sample == epoch
    assert alignment.raw_offset_from_nominal_samples == epoch
    assert alignment.raw_offset_from_nominal_samples / RATE == pytest.approx(1.32e-3, abs=2e-6)
    assert alignment.circular_offset_from_nominal_samples == pytest.approx(epoch - RATE / 750.0)
    assert alignment.exact_score is not None and alignment.exact_score > 0.99
    assert alignment.exact_minus_control_margin is not None
    assert alignment.exact_minus_control_margin > 0.05
    assert alignment.phase_invariant
    assert not alignment.absolute_carrier_phase_resolved
    assert alignment.candidate_only
    assert alignment.expected_symbol_roll == 0
    assert alignment.control_epoch_sample is not None
    assert alignment.control_absolute_cfo_hz is not None
    assert alignment.control_frame_support >= 2


def test_known_cfo_alignment_includes_the_noninteger_period_boundary() -> None:
    period_samples = RATE / 750.0
    epoch = math.floor(period_samples)
    template = qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)
    indexes = np.arange(template.size)
    final_start = epoch + round(4 * period_samples)
    samples = np.zeros(final_start + template.size + 2, dtype=np.complex128)
    for frame in range(5):
        start = epoch + round(frame * period_samples)
        samples[start + indexes] += template

    alignment = align_known_pilot_frames(
        samples,
        RATE,
        absolute_cfo_hz=0.0,
        edge=StarlinkEdge.LOWER,
        nominal_epoch_sample=epoch,
    )

    assert alignment.status is NumericalStatus.COMPLETE
    assert alignment.searched_epoch_count == math.ceil(period_samples)
    assert alignment.epoch_sample == epoch
    assert alignment.exact_score is not None and alignment.exact_score > 0.99
    assert alignment.circular_offset_from_nominal_samples == pytest.approx(0.0)


def test_known_cfo_alignment_preserves_two_frame_minimum_support() -> None:
    period_samples = RATE / 750.0
    template = qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)
    samples = np.zeros(round(period_samples) + template.size + 2, dtype=np.complex128)
    for frame in range(2):
        start = round(frame * period_samples)
        samples[start : start + template.size] += template

    alignment = align_known_pilot_frames(
        samples,
        RATE,
        absolute_cfo_hz=0.0,
        cfo_search_radius_hz=2_000.0,
        edge=StarlinkEdge.LOWER,
    )

    assert alignment.status is NumericalStatus.COMPLETE
    assert alignment.epoch_sample == 0
    assert alignment.frame_support == 2
    assert alignment.exact_score == pytest.approx(1.0)


def test_supported_epoch_survives_a_stronger_unsupported_peak_at_the_seam() -> None:
    generator = np.random.default_rng(1)
    period_samples = RATE / 750.0
    template = qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)
    samples = np.zeros(round(period_samples) + template.size + 2, dtype=np.complex128)
    noise = 0.05 * (
        generator.normal(size=template.size) + 1j * generator.normal(size=template.size)
    )
    samples[: template.size] += template + noise
    second = round(period_samples)
    samples[second : second + template.size] += template

    alignment = align_known_pilot_frames(
        samples,
        RATE,
        absolute_cfo_hz=0.0,
        edge=StarlinkEdge.LOWER,
    )

    assert alignment.status is NumericalStatus.COMPLETE
    assert alignment.epoch_sample == 0
    assert alignment.frame_support == 2


def test_known_cfo_alignment_uses_held_out_pilots_to_adjudicate_anchor_aliases() -> None:
    rng = np.random.default_rng(18)
    cfo_hz = 200_000.0
    template = qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)
    samples = (
        rng.normal(0.0, 0.02 / np.sqrt(2), 18_000) + 1j * rng.normal(0.0, 0.02 / np.sqrt(2), 18_000)
    ).astype(np.complex128)
    even_indexes = np.concatenate(
        tuple(
            np.arange(round(symbol * RATE * 4.4e-6), round((symbol + 1) * RATE * 4.4e-6))
            for symbol in range(2, 302, 2)
        )
    )
    full_indexes = np.arange(template.size)

    def inject(epoch: int, amplitude: float, indexes: np.ndarray) -> None:
        for frame in range(5):
            start = epoch + round(frame * RATE / 750.0)
            absolute = start + indexes
            samples[absolute] += (
                amplitude * template[indexes] * np.exp(2j * np.pi * cfo_hz * absolute / RATE)
            )

    inject(811, 5.0, even_indexes)
    inject(127, 1.5, full_indexes)
    alignment = align_known_pilot_frames(
        samples,
        RATE,
        absolute_cfo_hz=cfo_hz,
        edge=StarlinkEdge.LOWER,
    )

    assert alignment.status is NumericalStatus.COMPLETE
    assert alignment.adjudicated_candidate_count >= 2
    assert alignment.epoch_sample == 127
    assert alignment.exact_score is not None and alignment.exact_score > 0.45
    assert (
        alignment.exact_minus_control_margin is not None
        and alignment.exact_minus_control_margin > 0.15
    )
