from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.qam import estimate_edge_pilot_frame_complex_split
from leo.analysis.research.frame_phase_rate import (
    FramePhaseRateConfig,
    FramePhaseRateObservation,
    fit_iterative_frame_phase_rate,
    frame_lattice_point,
)
from leo.analysis.starlink import NumericalStatus, qin_edge_pilot_frame
from leo.analysis.starlink.templates import (
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    edge_frequencies_hz,
)

RATE = 2_500_000.0
EPOCH = 37
REFERENCE_OFFSET_SAMPLES = 1_672.0


def _observations(
    *,
    frame_count: int = 60,
    cfo_hz: float = 100_320.0,
    rate_hz_s: float = -1_800.0,
    timing_samples: float = 0.12,
    timing_rate_samples_s: float = 100.0,
    independent_phase: bool = False,
    timing_recentered: bool = True,
) -> tuple[FramePhaseRateObservation, ...]:
    generator = np.random.default_rng(0x750_1333)
    tones_hz = edge_frequencies_hz(StarlinkEdge.LOWER)
    static_channel = np.exp(1j * generator.uniform(-np.pi, np.pi, size=8))
    static_channel /= np.linalg.norm(static_channel)
    starts = []
    references = []
    for frame_index in range(frame_count):
        local_time_s = frame_index / 750.0
        timing = timing_samples + timing_rate_samples_s * local_time_s
        ideal = EPOCH + frame_index * RATE / 750.0
        start = round(ideal + timing) if timing_recentered else round(ideal)
        starts.append(start)
        references.append(start + REFERENCE_OFFSET_SAMPLES)
    reference_time_s = references[0] / RATE
    random_phase = generator.uniform(-np.pi, np.pi, size=frame_count)
    output = []
    for frame_index, (start, reference_sample) in enumerate(zip(starts, references, strict=True)):
        time_s = reference_sample / RATE - reference_time_s
        nominal_time_s = frame_index / 750.0
        timing = timing_samples + timing_rate_samples_s * nominal_time_s
        selected_minus_ideal = start - (EPOCH + frame_index * RATE / 750.0)
        extraction_delay = selected_minus_ideal - timing
        ambiguity_bit = (frame_index // 3 + frame_index // 11) % 2
        phase = (
            random_phase[frame_index]
            if independent_phase
            else 2 * np.pi * (cfo_hz * time_s + 0.5 * rate_hz_s * time_s**2) + np.pi * ambiguity_bit
        )
        channel = static_channel * np.exp(1j * phase)
        channel *= np.exp(2j * np.pi * tones_hz * extraction_delay / RATE)
        even_channel = channel + 0.002 * (generator.normal(size=8) + 1j * generator.normal(size=8))
        odd_channel = channel + 0.002 * (generator.normal(size=8) + 1j * generator.normal(size=8))
        even_channel.flags.writeable = False
        odd_channel.flags.writeable = False
        true_frequency = cfo_hz + rate_hz_s * time_s
        output.append(
            FramePhaseRateObservation(
                frame_index=frame_index,
                frame_start_sample=start,
                reference_sample=reference_sample,
                continuity_segment=4,
                training_supported=True,
                even_absolute_cfo_hz=float(true_frequency + generator.normal(scale=2.0)),
                even_frequency_uncertainty_hz=2.0,
                even_exact_coherence=0.80,
                even_control_coherence=0.02,
                even_channel_vector=even_channel,
                odd_absolute_cfo_hz=float(true_frequency + generator.normal(scale=2.0)),
                odd_channel_vector=odd_channel,
            )
        )
    return tuple(output)


def test_exact_750_hz_lattice_never_accumulates_rounded_increments() -> None:
    points = [frame_lattice_point(EPOCH, index, RATE) for index in range(61)]

    assert [item.rounded_start_sample - EPOCH for item in points[:4]] == [0, 3333, 6667, 10000]
    assert np.diff([item.rounded_start_sample for item in points[:7]]).tolist() == [
        3333,
        3334,
        3333,
        3333,
        3334,
        3333,
    ]
    assert [item.rounded_minus_ideal_samples for item in points[:3]] == pytest.approx(
        [0.0, -1 / 3, 1 / 3]
    )
    fixed_increment_start = EPOCH + 60 * round(RATE / 750.0)
    assert points[60].rounded_start_sample - fixed_increment_start == 20


def test_empty_locklet_returns_typed_insufficient_result() -> None:
    result = fit_iterative_frame_phase_rate(
        (),
        sample_rate_hz=RATE,
        epoch_sample=EPOCH,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.INSUFFICIENT
    assert result.frame_count == 0
    assert result.reason == "too few independently supported even-Qin frames"
    assert not result.phase_arc_qualified


def test_raw_qin_frames_recover_global_phase_and_doppler_rate_end_to_end() -> None:
    epoch = 1_000
    cfo_hz = 100_000.0
    rate_hz_s = -1_800.0
    frame_count = 30
    frame_content = round(302 * RATE * OFDM_SYMBOL_DURATION_S)
    template = np.asarray(qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER))[:frame_content]
    observations = []
    for frame_index in range(frame_count):
        frame_start = round(epoch + frame_index * RATE / 750.0)
        absolute_samples = frame_start + np.arange(frame_content)
        time_s = absolute_samples / RATE
        ambiguity_bit = (frame_index // 3 + frame_index // 11) % 2
        guarded = np.zeros(frame_content + 2, dtype=np.complex128)
        guarded[1:-1] = template * np.exp(
            2j * np.pi * (cfo_hz * time_s + 0.5 * rate_hz_s * time_s**2)
            + 1j * np.pi * ambiguity_bit
        )
        split = estimate_edge_pilot_frame_complex_split(
            guarded,
            RATE,
            frame_start_sample=frame_start,
            acquisition_absolute_cfo_hz=cfo_hz,
            edge=StarlinkEdge.LOWER,
        )
        assert split.training_supported and split.even is not None and split.odd is not None
        observations.append(
            FramePhaseRateObservation(
                frame_index=frame_index,
                frame_start_sample=frame_start,
                reference_sample=split.reference_sample,
                continuity_segment=0,
                training_supported=True,
                even_absolute_cfo_hz=split.even.absolute_cfo_hz,
                even_frequency_uncertainty_hz=max(split.even.frequency_uncertainty_hz, 1.0),
                even_exact_coherence=split.even.exact_coherence,
                even_control_coherence=split.even.control_coherence,
                even_channel_vector=split.even.channel_vector,
                odd_absolute_cfo_hz=split.odd.absolute_cfo_hz,
                odd_channel_vector=split.odd.channel_vector,
            )
        )

    result = fit_iterative_frame_phase_rate(
        tuple(observations),
        sample_rate_hz=RATE,
        epoch_sample=epoch,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.reference_time_s is not None
    expected_reference_cfo = cfo_hz + rate_hz_s * result.reference_time_s
    assert result.frequency_only_cfo_hz == pytest.approx(expected_reference_cfo, abs=1.0)
    assert result.frequency_only_doppler_rate_hz_s == pytest.approx(rate_hz_s, abs=0.2)
    assert result.phase_candidate_cfo_hz == pytest.approx(expected_reference_cfo, abs=0.02)
    assert result.phase_candidate_doppler_rate_hz_s == pytest.approx(rate_hz_s, abs=0.02)
    assert result.phase_arc_qualified
    assert result.odd_phase_rms_rad is not None and result.odd_phase_rms_rad < 0.01
    assert result.odd_stack_efficiency is not None and result.odd_stack_efficiency > 0.999
    assert not result.absolute_carrier_phase_resolved


def test_iterative_locklet_recovers_rate_pi_state_and_timing_recentering() -> None:
    observations = _observations()

    result = fit_iterative_frame_phase_rate(
        observations,
        sample_rate_hz=RATE,
        epoch_sample=EPOCH,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.converged
    assert result.phase_arc_qualified
    assert not result.phase_feedback_qualified
    assert result.odd_symbols_influenced_fit is False
    assert result.frequency_only_doppler_rate_hz_s == pytest.approx(-1_800.0, abs=30.0)
    assert result.phase_candidate_doppler_rate_hz_s == pytest.approx(-1_800.0, abs=5.0)
    assert result.relative_timing_rate_samples_s == pytest.approx(100.0, abs=1.0)
    assert result.training_phase_rms_rad is not None
    assert result.training_phase_rms_rad < 0.01
    assert result.odd_phase_rms_rad is not None and result.odd_phase_rms_rad < 0.01
    assert result.odd_stack_efficiency is not None and result.odd_stack_efficiency > 0.999
    assert max(item.rounded_minus_ideal_samples for item in result.frames) > 8.0


def test_independent_frame_phase_cannot_bend_primary_frequency_rate() -> None:
    observations = _observations(independent_phase=True)

    result = fit_iterative_frame_phase_rate(
        observations,
        sample_rate_hz=RATE,
        epoch_sample=EPOCH,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.frequency_only_doppler_rate_hz_s == pytest.approx(-1_800.0, abs=30.0)
    assert not result.phase_feedback_qualified
    assert result.training_phase_rms_rad is not None
    assert result.training_phase_rms_rad > 0.35
    assert "phase RMS" in result.phase_feedback_reason
    assert result.primary_rate_source == "independent even-Qin frame CFO"


def test_odd_corruption_changes_validation_but_not_fit_membership_or_iterations() -> None:
    clean = _observations()
    corrupted = tuple(
        replace(
            item,
            odd_absolute_cfo_hz=(
                None if item.odd_absolute_cfo_hz is None else item.odd_absolute_cfo_hz + 5_000.0
            ),
            odd_channel_vector=(
                None
                if item.odd_channel_vector is None
                else np.asarray(item.odd_channel_vector) * np.exp(0.73j * item.frame_index)
            ),
        )
        for item in clean
    )
    clean_result = fit_iterative_frame_phase_rate(
        clean,
        sample_rate_hz=RATE,
        epoch_sample=EPOCH,
        edge=StarlinkEdge.LOWER,
    )
    corrupted_result = fit_iterative_frame_phase_rate(
        corrupted,
        sample_rate_hz=RATE,
        epoch_sample=EPOCH,
        edge=StarlinkEdge.LOWER,
    )

    training_fields = (
        "frame_count",
        "reference_time_s",
        "frequency_only_cfo_hz",
        "frequency_only_doppler_rate_hz_s",
        "frequency_only_rate_sigma_hz_s",
        "phase_candidate_cfo_hz",
        "phase_candidate_doppler_rate_hz_s",
        "relative_timing_samples",
        "relative_timing_rate_samples_s",
        "iteration_count",
        "converged",
        "training_phase_rms_rad",
    )
    for field_name in training_fields:
        assert getattr(corrupted_result, field_name) == pytest.approx(
            getattr(clean_result, field_name)
        )
    assert clean_result.phase_arc_qualified
    assert not corrupted_result.phase_arc_qualified
    assert not corrupted_result.phase_feedback_qualified
    assert corrupted_result.odd_cfo_rms_hz is not None
    assert clean_result.odd_cfo_rms_hz is not None
    assert corrupted_result.odd_cfo_rms_hz > clean_result.odd_cfo_rms_hz + 4_000.0


def test_timing_convergence_cannot_be_declared_from_frequency_alone() -> None:
    observations = _observations(
        timing_samples=0.1,
        timing_rate_samples_s=20.0,
        timing_recentered=False,
    )
    one_iteration = fit_iterative_frame_phase_rate(
        observations,
        sample_rate_hz=RATE,
        epoch_sample=EPOCH,
        edge=StarlinkEdge.LOWER,
        config=replace(FramePhaseRateConfig(), maximum_iterations=1),
    )
    converged = fit_iterative_frame_phase_rate(
        observations,
        sample_rate_hz=RATE,
        epoch_sample=EPOCH,
        edge=StarlinkEdge.LOWER,
        config=replace(FramePhaseRateConfig(), maximum_iterations=8),
    )

    assert not one_iteration.converged
    assert not one_iteration.phase_arc_qualified
    assert converged.converged
    assert converged.iteration_count > 1
    assert converged.relative_timing_rate_samples_s == pytest.approx(20.0, abs=1.0)
    assert converged.relative_timing_boundary_fraction is not None
    assert converged.relative_timing_boundary_fraction <= 0.10


def test_nonfinite_odd_validation_input_fails_closed() -> None:
    observations = _observations()
    malformed = (replace(observations[0], odd_absolute_cfo_hz=float("nan")),) + observations[1:]
    clean = fit_iterative_frame_phase_rate(
        observations,
        sample_rate_hz=RATE,
        epoch_sample=EPOCH,
        edge=StarlinkEdge.LOWER,
    )
    result = fit_iterative_frame_phase_rate(
        malformed,
        sample_rate_hz=RATE,
        epoch_sample=EPOCH,
        edge=StarlinkEdge.LOWER,
    )

    assert result.frequency_only_doppler_rate_hz_s == clean.frequency_only_doppler_rate_hz_s
    assert result.phase_candidate_doppler_rate_hz_s == clean.phase_candidate_doppler_rate_hz_s
    assert result.iteration_count == clean.iteration_count
    assert not result.odd_validation_valid
    assert result.validation_frame_count == 0
    assert not result.phase_arc_qualified
    assert not result.phase_feedback_qualified
    assert "malformed" in result.odd_validation_reason


def test_locklet_fails_closed_at_continuity_or_supported_frame_gap() -> None:
    observations = _observations(frame_count=20)
    mixed = observations[:10] + tuple(
        replace(item, continuity_segment=5) for item in observations[10:]
    )
    with pytest.raises(ValueError, match="continuity boundary"):
        fit_iterative_frame_phase_rate(
            mixed,
            sample_rate_hz=RATE,
            epoch_sample=EPOCH,
            edge=StarlinkEdge.LOWER,
        )

    gapped = tuple(
        replace(item, training_supported=False) if 5 <= item.frame_index <= 15 else item
        for item in observations
    )
    result = fit_iterative_frame_phase_rate(
        gapped,
        sample_rate_hz=RATE,
        epoch_sample=EPOCH,
        edge=StarlinkEdge.LOWER,
    )
    assert result.status is NumericalStatus.INSUFFICIENT
    assert result.reason == "supported locklet contains an unqualified gap"
    assert not result.phase_feedback_qualified


def test_mislabeled_or_inconsistent_frame_lattice_fails_closed() -> None:
    observations = _observations(frame_count=20)
    mislabeled = list(observations)
    mislabeled[10] = replace(mislabeled[10], frame_index=11)
    mislabeled[11] = replace(mislabeled[11], frame_index=10)
    with pytest.raises(ValueError, match="frame indices must increase"):
        fit_iterative_frame_phase_rate(
            tuple(mislabeled),
            sample_rate_hz=RATE,
            epoch_sample=EPOCH,
            edge=StarlinkEdge.LOWER,
        )

    shifted_reference = list(observations)
    shifted_reference[10] = replace(
        shifted_reference[10],
        reference_sample=shifted_reference[10].reference_sample + 0.25,
    )
    with pytest.raises(ValueError, match="reference offsets must be constant"):
        fit_iterative_frame_phase_rate(
            tuple(shifted_reference),
            sample_rate_hz=RATE,
            epoch_sample=EPOCH,
            edge=StarlinkEdge.LOWER,
        )
