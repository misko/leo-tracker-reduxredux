"""Reset-safe iterative modeling of 750 Hz known-pilot frame dynamics.

This module deliberately separates two claims:

* even-Qin frame-local CFO is an independently observable measurement and is
  the primary source for frequency and Doppler rate;
* carrier phase and eight-tone fractional delay are optional locklet
  diagnostics whose feedback is promoted only after fit-withheld odd-Qin
  validation.  Corpus-level region selection remains a separate conditioning
  step that callers must disclose.

One call fits one RF-contiguous locklet.  Acquisition remains authoritative
for the frame epoch and CFO alias, and callers must split unknown refills,
device-time gaps, source changes, and reacquisitions before calling this code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from leo.analysis.starlink import NumericalStatus
from leo.analysis.starlink.templates import FRAME_RATE_HZ, StarlinkEdge, edge_frequencies_hz


@dataclass(frozen=True, slots=True)
class FrameLatticePoint:
    """One exact frame coordinate before and after integer sample selection."""

    frame_index: int
    ideal_start_sample: float
    rounded_start_sample: int
    rounded_minus_ideal_samples: float

    @property
    def fractional_residual_samples(self) -> float:
        """Continuous coordinate minus selected integer, in ``[-0.5, 0.5]``."""

        return -self.rounded_minus_ideal_samples


def frame_lattice_point(
    epoch_sample: int,
    frame_index: int,
    sample_rate_hz: float,
    *,
    timing_offset_samples: float = 0.0,
) -> FrameLatticePoint:
    """Return ``u=e+m*Fs/750+tau`` and its one-time nearest integer.

    The integer coordinate is always derived from the continuous coordinate;
    rounded increments are never accumulated.  Python's nearest-even tie rule
    is explicit here.  A future persisted standard should freeze a tie rule
    before admitting sample rates that can land exactly on half a sample.
    """

    if not isinstance(epoch_sample, (int, np.integer)):
        raise ValueError("frame epoch must be an integer sample")
    if not isinstance(frame_index, (int, np.integer)) or frame_index < 0:
        raise ValueError("frame index must be a nonnegative integer")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample rate must be finite and positive")
    if not math.isfinite(timing_offset_samples):
        raise ValueError("timing offset must be finite")
    ideal = float(
        int(epoch_sample)
        + int(frame_index) * sample_rate_hz / FRAME_RATE_HZ
        + timing_offset_samples
    )
    rounded = round(ideal)
    return FrameLatticePoint(
        frame_index=int(frame_index),
        ideal_start_sample=ideal,
        rounded_start_sample=int(rounded),
        rounded_minus_ideal_samples=float(rounded - ideal),
    )


@dataclass(frozen=True, slots=True)
class FramePhaseRateConfig:
    """Frozen gates for one offline frame phase/rate locklet."""

    minimum_frames: int = 8
    minimum_span_s: float = 0.008
    maximum_gap_s: float = 0.012
    maximum_iterations: int = 4
    enable_relative_timing: bool = True
    frequency_sigma_floor_hz: float = 5.0
    huber_tuning: float = 1.345
    frequency_convergence_hz: float = 0.05
    rate_convergence_hz_s: float = 1.0
    timing_convergence_samples: float = 0.01
    timing_rate_convergence_samples_s: float = 1.0
    relative_delay_half_width_samples: float = 0.75
    relative_delay_grid_points: int = 301
    maximum_delay_boundary_fraction: float = 0.10
    minimum_channel_similarity: float = 0.65
    maximum_training_phase_rms_rad: float = 0.35
    maximum_validation_phase_rms_rad: float = 0.35
    minimum_validation_stack_efficiency: float = 0.90
    maximum_phase_rate_disagreement_hz_s: float = 500.0

    def __post_init__(self) -> None:
        if not isinstance(self.enable_relative_timing, bool):
            raise ValueError("relative-timing switch must be boolean")
        if not 3 <= self.minimum_frames <= 10_000:
            raise ValueError("minimum frame count must lie in [3, 10000]")
        if not 1 <= self.maximum_iterations <= 20:
            raise ValueError("maximum iterations must lie in [1, 20]")
        if not 3 <= self.relative_delay_grid_points <= 4_001:
            raise ValueError("relative-delay grid must contain 3..4001 points")
        if self.relative_delay_grid_points % 2 == 0:
            raise ValueError("relative-delay grid point count must be odd")
        positive = (
            self.minimum_span_s,
            self.maximum_gap_s,
            self.frequency_sigma_floor_hz,
            self.huber_tuning,
            self.frequency_convergence_hz,
            self.rate_convergence_hz_s,
            self.timing_convergence_samples,
            self.timing_rate_convergence_samples_s,
            self.relative_delay_half_width_samples,
            self.maximum_delay_boundary_fraction,
            self.minimum_channel_similarity,
            self.maximum_training_phase_rms_rad,
            self.maximum_validation_phase_rms_rad,
            self.minimum_validation_stack_efficiency,
            self.maximum_phase_rate_disagreement_hz_s,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("frame phase/rate gates must be finite and positive")
        if self.minimum_channel_similarity > 1.0:
            raise ValueError("minimum channel similarity cannot exceed one")
        if self.minimum_validation_stack_efficiency > 1.0:
            raise ValueError("minimum stack efficiency cannot exceed one")
        if self.maximum_delay_boundary_fraction > 1.0:
            raise ValueError("maximum delay boundary fraction cannot exceed one")
        if self.maximum_training_phase_rms_rad > math.pi / 2:
            raise ValueError("modulo-pi training phase gate cannot exceed pi/2")


@dataclass(frozen=True, slots=True)
class FramePhaseRateObservation:
    """One acquisition-bound parity-split frame observation.

    The even fields are the only training inputs.  Odd fields are optional and
    are consumed only after all parameters, membership, iteration count, and
    ambiguity bits have frozen.
    """

    frame_index: int
    frame_start_sample: int
    reference_sample: float
    continuity_segment: int
    training_supported: bool
    even_absolute_cfo_hz: float
    even_frequency_uncertainty_hz: float
    even_exact_coherence: float
    even_control_coherence: float
    even_channel_vector: np.ndarray = field(repr=False)
    odd_absolute_cfo_hz: float | None = None
    odd_channel_vector: np.ndarray | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class FramePhaseRateFrame:
    """One frame's frozen training diagnostics and held-out response."""

    frame_index: int
    frame_start_sample: int
    reference_sample: float
    rounded_minus_ideal_samples: float
    predicted_frequency_hz: float
    even_frequency_innovation_hz: float
    relative_timing_samples: float
    phase_ambiguity_bit: int
    training_phase_residual_modulo_pi_rad: float
    channel_similarity: float
    odd_frequency_error_hz: float | None
    phase_candidate_odd_frequency_error_hz: float | None
    odd_phase_residual_rad: float | None


@dataclass(frozen=True, slots=True)
class FramePhaseRateResult:
    """Frequency-primary result with an independently qualified phase layer."""

    status: NumericalStatus
    reason: str
    frame_count: int
    validation_frame_count: int
    reference_time_s: float | None
    frequency_only_cfo_hz: float | None
    frequency_only_doppler_rate_hz_s: float | None
    frequency_only_rate_sigma_hz_s: float | None
    phase_candidate_cfo_hz: float | None
    phase_candidate_doppler_rate_hz_s: float | None
    relative_timing_samples: float | None
    relative_timing_rate_samples_s: float | None
    relative_timing_boundary_fraction: float | None
    iteration_count: int
    converged: bool
    training_phase_rms_rad: float | None
    odd_cfo_rms_hz: float | None
    phase_candidate_odd_cfo_rms_hz: float | None
    odd_phase_rms_rad: float | None
    odd_stack_efficiency: float | None
    odd_validation_valid: bool
    odd_validation_reason: str
    phase_arc_qualified: bool
    phase_arc_reason: str
    phase_feedback_qualified: bool
    phase_feedback_reason: str
    frames: tuple[FramePhaseRateFrame, ...]
    odd_symbols_influenced_fit: bool = False
    primary_rate_source: str = "independent even-Qin frame CFO"
    carrier_phase_period_rad: float = math.pi
    absolute_carrier_phase_resolved: bool = False
    frame_timing_is_receiver_relative: bool = True


@dataclass(frozen=True, slots=True)
class _OddValidation:
    valid: bool
    reason: str
    count: int
    cfo_rms_hz: float | None
    candidate_cfo_rms_hz: float | None
    phase_rms_rad: float | None
    stack_efficiency: float | None
    frequency_errors: tuple[float | None, ...]
    candidate_frequency_errors: tuple[float | None, ...]
    phase_residuals: tuple[float | None, ...]


def fit_iterative_frame_phase_rate(
    observations: tuple[FramePhaseRateObservation, ...],
    *,
    sample_rate_hz: float,
    epoch_sample: int,
    edge: StarlinkEdge | str,
    config: FramePhaseRateConfig | None = None,
) -> FramePhaseRateResult:
    """Fit one continuity-safe locklet without allowing phase to bend primary rate."""

    settings = config or FramePhaseRateConfig()
    selected_edge = StarlinkEdge(edge)
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample rate must be finite and positive")
    if not isinstance(epoch_sample, (int, np.integer)):
        raise ValueError("frame epoch must be an integer sample")
    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (item.reference_sample, item.frame_start_sample, item.frame_index),
        )
    )
    if len({item.frame_start_sample for item in ordered}) != len(ordered):
        raise ValueError("frame starts must be unique inside one locklet")
    if len({item.frame_index for item in ordered}) != len(ordered):
        raise ValueError("frame indices must be unique inside one locklet")
    if any(
        right.frame_index <= left.frame_index
        for left, right in zip(ordered, ordered[1:], strict=False)
    ):
        raise ValueError("frame indices must increase with reference time")
    if any(
        right.frame_start_sample <= left.frame_start_sample
        for left, right in zip(ordered, ordered[1:], strict=False)
    ):
        raise ValueError("frame starts must increase with reference time")
    reference_offsets = np.asarray(
        [item.reference_sample - item.frame_start_sample for item in ordered],
        dtype=float,
    )
    if ordered and float(np.ptp(reference_offsets)) > 1e-6:
        raise ValueError("frame reference offsets must be constant inside one locklet")
    if len({item.continuity_segment for item in ordered}) > 1:
        raise ValueError("one phase/rate fit cannot cross a continuity boundary")

    training = tuple(item for item in ordered if item.training_supported)
    if len(training) < settings.minimum_frames:
        return _empty_result("too few independently supported even-Qin frames", len(training))
    _validate_observations(training)
    times_s = np.asarray([item.reference_sample / sample_rate_hz for item in training])
    if times_s[-1] - times_s[0] < settings.minimum_span_s:
        return _empty_result("supported locklet span is too short", len(training))
    if np.any(np.diff(times_s) > settings.maximum_gap_s):
        return _empty_result("supported locklet contains an unqualified gap", len(training))

    reference_time_s = float(times_s[0])
    local_time_s = times_s - reference_time_s
    cfo_hz = np.asarray([item.even_absolute_cfo_hz for item in training])
    sigma_hz = np.asarray([item.even_frequency_uncertainty_hz for item in training])
    coherence = np.asarray([item.even_exact_coherence for item in training])
    base_weight = coherence / np.maximum(sigma_hz, settings.frequency_sigma_floor_hz) ** 2
    frequency_design = np.column_stack((np.ones(len(training)), local_time_s))
    frequency_coefficients, frequency_covariance, _frequency_weights = _robust_solve(
        frequency_design,
        cfo_hz,
        base_weight,
        huber_tuning=settings.huber_tuning,
        scale_floor=settings.frequency_sigma_floor_hz,
    )
    frequency_only_cfo_hz = float(frequency_coefficients[0])
    frequency_only_rate_hz_s = float(frequency_coefficients[1])
    frequency_only_rate_sigma_hz_s = float(math.sqrt(max(float(frequency_covariance[1, 1]), 0.0)))

    channel = np.asarray([item.even_channel_vector for item in training], dtype=np.complex128)
    channel /= np.maximum(np.linalg.norm(channel, axis=1), np.finfo(float).tiny)[:, None]
    tone_hz = edge_frequencies_hz(selected_edge)
    selected_minus_ideal_samples = np.asarray(
        [
            _selected_minus_ideal(
                item,
                epoch_sample=epoch_sample,
                sample_rate_hz=sample_rate_hz,
            )
            for item in training
        ]
    )

    # Integer recentering contains a coarse timing observation.  Fitting it
    # first lets the fractional channel projection remain inside its local
    # basin even when timing drift crosses several integer samples.
    if settings.enable_relative_timing:
        coarse_timing, _coarse_timing_covariance, _coarse_timing_weights = _robust_solve(
            frequency_design,
            selected_minus_ideal_samples,
            base_weight,
            huber_tuning=settings.huber_tuning,
            scale_floor=0.25,
        )
    else:
        coarse_timing = np.zeros(2, dtype=float)

    candidate_cfo_hz = frequency_only_cfo_hz
    candidate_rate_hz_s = frequency_only_rate_hz_s
    timing_offset_samples = float(coarse_timing[0])
    timing_rate_samples_s = float(coarse_timing[1])
    delay_values = np.zeros(len(training), dtype=float)
    bits = np.zeros(len(training), dtype=int)
    phase_residual = np.zeros(len(training), dtype=float)
    similarities = np.ones(len(training), dtype=float)
    reference_channel = _initial_channel_reference(
        channel,
        local_time_s,
        selected_minus_ideal_samples,
        tone_hz,
        sample_rate_hz,
        candidate_cfo_hz,
        candidate_rate_hz_s,
        timing_offset_samples,
        timing_rate_samples_s,
    )
    converged = False
    iteration_count = 0
    delay_boundary_fraction = 0.0

    offsets = np.linspace(
        -settings.relative_delay_half_width_samples,
        settings.relative_delay_half_width_samples,
        settings.relative_delay_grid_points,
    )
    for iteration in range(1, settings.maximum_iterations + 1):
        iteration_count = iteration
        previous_timing_offset_samples = timing_offset_samples
        previous_timing_rate_samples_s = timing_rate_samples_s
        if settings.enable_relative_timing:
            predicted_delay = timing_offset_samples + timing_rate_samples_s * local_time_s
            delay_values, similarities, delay_boundaries = _delay_observations(
                channel,
                reference_channel,
                predicted_delay,
                selected_minus_ideal_samples,
                offsets,
                tone_hz,
                sample_rate_hz,
            )
            timing_design = frequency_design
            timing_coefficients, _timing_covariance, _timing_weights = _robust_solve(
                timing_design,
                delay_values,
                base_weight * np.maximum(similarities, 1e-6),
                huber_tuning=settings.huber_tuning,
                scale_floor=max(
                    0.01,
                    2 * settings.relative_delay_half_width_samples / (len(offsets) - 1),
                ),
            )
            timing_offset_samples = float(timing_coefficients[0])
            timing_rate_samples_s = float(timing_coefficients[1])
            delay_boundary_fraction = float(np.mean(delay_boundaries))
        else:
            delay_values = np.zeros(len(training), dtype=float)
            similarities = np.abs(
                _delay_align(
                    channel,
                    selected_minus_ideal_samples,
                    tone_hz,
                    sample_rate_hz,
                )
                @ np.conj(reference_channel)
            )

        delay_aligned = _delay_align(
            channel,
            selected_minus_ideal_samples
            - (timing_offset_samples + timing_rate_samples_s * local_time_s),
            tone_hz,
            sample_rate_hz,
        )
        predicted_phase = _integrated_phase(
            local_time_s,
            candidate_cfo_hz,
            candidate_rate_hz_s,
        )
        projection = delay_aligned @ np.conj(reference_channel)
        observed_phase = np.angle(projection)
        phase_residual = _wrap_period(observed_phase - predicted_phase, math.pi)
        phase_design = np.column_stack(
            (
                np.ones(len(training)),
                2 * math.pi * local_time_s,
                math.pi * local_time_s**2,
            )
        )
        phase_coefficients, _phase_covariance, _phase_weights = _robust_solve(
            phase_design,
            phase_residual,
            base_weight * np.maximum(similarities, 1e-6),
            huber_tuning=settings.huber_tuning,
            scale_floor=0.02,
        )
        updated_cfo_hz = float(candidate_cfo_hz + phase_coefficients[1])
        updated_rate_hz_s = float(candidate_rate_hz_s + phase_coefficients[2])
        updated_phase = _integrated_phase(local_time_s, updated_cfo_hz, updated_rate_hz_s)
        updated_residual = _wrap_period(observed_phase - updated_phase, math.pi)
        bits = np.mod(
            np.rint((observed_phase - updated_phase - updated_residual) / math.pi).astype(int),
            2,
        )
        signed = 1 - 2 * bits
        fully_aligned = delay_aligned * np.exp(-1j * updated_phase)[:, None]
        fully_aligned *= signed[:, None]
        root_weight = base_weight * np.maximum(similarities, 1e-6)
        updated_channel = np.sum(root_weight[:, None] * fully_aligned, axis=0)
        norm = float(np.linalg.norm(updated_channel))
        if norm <= np.finfo(float).tiny:
            return _empty_result("iterative channel reference collapsed", len(training))
        updated_channel /= norm
        frequency_change = abs(updated_cfo_hz - candidate_cfo_hz)
        rate_change = abs(updated_rate_hz_s - candidate_rate_hz_s)
        timing_change = abs(timing_offset_samples - previous_timing_offset_samples)
        timing_rate_change = abs(timing_rate_samples_s - previous_timing_rate_samples_s)
        candidate_cfo_hz = updated_cfo_hz
        candidate_rate_hz_s = updated_rate_hz_s
        reference_channel = updated_channel
        phase_residual = updated_residual
        if (
            frequency_change <= settings.frequency_convergence_hz
            and rate_change <= settings.rate_convergence_hz_s
            and (
                not settings.enable_relative_timing
                or (
                    timing_change <= settings.timing_convergence_samples
                    and timing_rate_change <= settings.timing_rate_convergence_samples_s
                )
            )
        ):
            converged = True
            break

    final_delay = timing_offset_samples + timing_rate_samples_s * local_time_s
    final_delay_aligned = _delay_align(
        channel,
        selected_minus_ideal_samples - final_delay,
        tone_hz,
        sample_rate_hz,
    )
    final_phase = _integrated_phase(local_time_s, candidate_cfo_hz, candidate_rate_hz_s)
    final_projection = final_delay_aligned @ np.conj(reference_channel)
    final_observed_phase = np.angle(final_projection)
    phase_residual = _wrap_period(final_observed_phase - final_phase, math.pi)
    bits = np.mod(
        np.rint((final_observed_phase - final_phase - phase_residual) / math.pi).astype(int),
        2,
    )
    similarities = np.abs(final_projection)
    training_phase_rms = _weighted_rms(phase_residual, base_weight)

    validation = _odd_validation(
        training,
        local_time_s=local_time_s,
        predicted_frequency_hz=frequency_only_cfo_hz + frequency_only_rate_hz_s * local_time_s,
        candidate_frequency_hz=candidate_cfo_hz + candidate_rate_hz_s * local_time_s,
        candidate_phase=final_phase,
        bits=bits,
        final_delay=final_delay,
        selected_minus_ideal_samples=selected_minus_ideal_samples,
        reference_channel=reference_channel,
        tone_hz=tone_hz,
        sample_rate_hz=sample_rate_hz,
        base_weight=base_weight,
    )
    rate_agreement_limit = max(
        settings.maximum_phase_rate_disagreement_hz_s,
        3 * frequency_only_rate_sigma_hz_s,
    )
    phase_failures = []
    if not converged:
        phase_failures.append("phase iteration did not converge")
    if training_phase_rms > settings.maximum_training_phase_rms_rad:
        phase_failures.append("training modulo-pi phase RMS exceeds gate")
    if float(np.median(similarities)) < settings.minimum_channel_similarity:
        phase_failures.append("median channel similarity is below gate")
    if delay_boundary_fraction > settings.maximum_delay_boundary_fraction:
        phase_failures.append("relative-delay search reaches its local boundary too often")
    if not validation.valid:
        phase_failures.append(validation.reason)
    if validation.count < settings.minimum_frames:
        phase_failures.append("too few fit-withheld odd-Qin validation frames")
    validation_phase_rms = validation.phase_rms_rad
    if (
        validation_phase_rms is None
        or not math.isfinite(validation_phase_rms)
        or validation_phase_rms > settings.maximum_validation_phase_rms_rad
    ):
        phase_failures.append("odd-Qin phase RMS exceeds gate")
    validation_stack_efficiency = validation.stack_efficiency
    if (
        validation_stack_efficiency is None
        or not math.isfinite(validation_stack_efficiency)
        or validation_stack_efficiency < settings.minimum_validation_stack_efficiency
    ):
        phase_failures.append("odd-Qin coherent-stack efficiency is below gate")
    if abs(candidate_rate_hz_s - frequency_only_rate_hz_s) > rate_agreement_limit:
        phase_failures.append("phase candidate disagrees with independent frame-CFO rate")
    feedback_failures = list(phase_failures)
    candidate_validation_rms = validation.candidate_cfo_rms_hz
    frequency_validation_rms = validation.cfo_rms_hz
    if (
        candidate_validation_rms is None
        or frequency_validation_rms is None
        or not math.isfinite(candidate_validation_rms)
        or not math.isfinite(frequency_validation_rms)
        or candidate_validation_rms >= frequency_validation_rms
    ):
        feedback_failures.append("phase candidate does not improve fit-withheld odd-Qin CFO")

    odd_frequency_errors = validation.frequency_errors
    candidate_odd_frequency_errors = validation.candidate_frequency_errors
    odd_phase_residuals = validation.phase_residuals
    frames = tuple(
        FramePhaseRateFrame(
            frame_index=item.frame_index,
            frame_start_sample=item.frame_start_sample,
            reference_sample=item.reference_sample,
            rounded_minus_ideal_samples=float(rounding),
            predicted_frequency_hz=float(frequency_only_cfo_hz + frequency_only_rate_hz_s * time_s),
            even_frequency_innovation_hz=float(
                item.even_absolute_cfo_hz
                - (frequency_only_cfo_hz + frequency_only_rate_hz_s * time_s)
            ),
            relative_timing_samples=float(delay),
            phase_ambiguity_bit=int(bit),
            training_phase_residual_modulo_pi_rad=float(residual),
            channel_similarity=float(similarity),
            odd_frequency_error_hz=_optional_float(odd_frequency_errors[index]),
            phase_candidate_odd_frequency_error_hz=_optional_float(
                candidate_odd_frequency_errors[index]
            ),
            odd_phase_residual_rad=_optional_float(odd_phase_residuals[index]),
        )
        for index, (item, time_s, rounding, delay, bit, residual, similarity) in enumerate(
            zip(
                training,
                local_time_s,
                selected_minus_ideal_samples,
                final_delay,
                bits,
                phase_residual,
                similarities,
                strict=True,
            )
        )
    )
    return FramePhaseRateResult(
        status=NumericalStatus.COMPLETE,
        reason=("even-Qin CFO fit complete; optional phase/timing are separately qualified"),
        frame_count=len(training),
        validation_frame_count=validation.count,
        reference_time_s=reference_time_s,
        frequency_only_cfo_hz=frequency_only_cfo_hz,
        frequency_only_doppler_rate_hz_s=frequency_only_rate_hz_s,
        frequency_only_rate_sigma_hz_s=frequency_only_rate_sigma_hz_s,
        phase_candidate_cfo_hz=candidate_cfo_hz,
        phase_candidate_doppler_rate_hz_s=candidate_rate_hz_s,
        relative_timing_samples=timing_offset_samples,
        relative_timing_rate_samples_s=timing_rate_samples_s,
        relative_timing_boundary_fraction=delay_boundary_fraction,
        iteration_count=iteration_count,
        converged=converged,
        training_phase_rms_rad=training_phase_rms,
        odd_cfo_rms_hz=validation.cfo_rms_hz,
        phase_candidate_odd_cfo_rms_hz=validation.candidate_cfo_rms_hz,
        odd_phase_rms_rad=validation.phase_rms_rad,
        odd_stack_efficiency=validation.stack_efficiency,
        odd_validation_valid=validation.valid,
        odd_validation_reason=validation.reason,
        phase_arc_qualified=not phase_failures,
        phase_arc_reason=(
            "fit-withheld odd-Qin modulo-pi phase arc qualified"
            if not phase_failures
            else "; ".join(phase_failures)
        ),
        phase_feedback_qualified=not feedback_failures,
        phase_feedback_reason=(
            "fit-withheld odd-Qin phase feedback improves frame-CFO rate"
            if not feedback_failures
            else "; ".join(feedback_failures)
        ),
        frames=frames,
    )


def _validate_observations(observations: tuple[FramePhaseRateObservation, ...]) -> None:
    for item in observations:
        scalars = (
            item.reference_sample,
            item.even_absolute_cfo_hz,
            item.even_frequency_uncertainty_hz,
            item.even_exact_coherence,
            item.even_control_coherence,
        )
        if any(not math.isfinite(value) for value in scalars):
            raise ValueError("supported frame observation contains a nonfinite scalar")
        if item.even_frequency_uncertainty_hz <= 0.0:
            raise ValueError("frequency uncertainty must be positive")
        if not 0.0 <= item.even_exact_coherence <= 1.0:
            raise ValueError("exact coherence must lie in [0, 1]")
        channel = np.asarray(item.even_channel_vector)
        if channel.shape != (8,) or not np.all(np.isfinite(channel)):
            raise ValueError("even channel vector must contain eight finite complex tones")
        if float(np.linalg.norm(channel)) <= np.finfo(float).tiny:
            raise ValueError("even channel vector cannot have zero norm")


def _selected_minus_ideal(
    observation: FramePhaseRateObservation,
    *,
    epoch_sample: int,
    sample_rate_hz: float,
) -> float:
    lattice = frame_lattice_point(epoch_sample, observation.frame_index, sample_rate_hz)
    return float(observation.frame_start_sample - lattice.ideal_start_sample)


def _robust_solve(
    design: np.ndarray,
    values: np.ndarray,
    base_weight: np.ndarray,
    *,
    huber_tuning: float,
    scale_floor: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if design.ndim != 2 or values.shape != (len(design),):
        raise ValueError("robust solve dimensions disagree")
    weights = np.asarray(base_weight, dtype=float)
    if weights.shape != values.shape or np.any(~np.isfinite(weights)) or np.any(weights <= 0.0):
        raise ValueError("robust solve weights must be finite and positive")
    root = np.sqrt(weights)
    coefficients = np.linalg.lstsq(design * root[:, None], values * root, rcond=None)[0]
    for _iteration in range(50):
        residual = values - design @ coefficients
        center = float(np.median(residual))
        scale = max(scale_floor, 1.4826 * float(np.median(np.abs(residual - center))))
        normalized = np.abs(residual - center) / (huber_tuning * scale)
        robust = np.ones(len(values), dtype=float)
        tail = normalized > 1.0
        robust[tail] = 1.0 / normalized[tail]
        weights = base_weight * robust
        root = np.sqrt(weights)
        updated = np.linalg.lstsq(design * root[:, None], values * root, rcond=None)[0]
        if float(np.max(np.abs(updated - coefficients))) < 1e-9:
            coefficients = updated
            break
        coefficients = updated
    residual = values - design @ coefficients
    dof = max(1, len(values) - design.shape[1])
    variance = float(np.sum(weights * residual**2) / dof)
    covariance = np.linalg.pinv(design.T @ (weights[:, None] * design)) * variance
    return coefficients, covariance, weights


def _initial_channel_reference(
    channel: np.ndarray,
    local_time_s: np.ndarray,
    selected_minus_ideal_samples: np.ndarray,
    tone_hz: np.ndarray,
    sample_rate_hz: float,
    cfo_hz: float,
    rate_hz_s: float,
    timing_offset_samples: float,
    timing_rate_samples_s: float,
) -> np.ndarray:
    predicted_timing = timing_offset_samples + timing_rate_samples_s * local_time_s
    aligned = _delay_align(
        channel,
        selected_minus_ideal_samples - predicted_timing,
        tone_hz,
        sample_rate_hz,
    )
    phase = _integrated_phase(local_time_s, cfo_hz, rate_hz_s)
    first = aligned[0] * np.exp(-1j * phase[0])
    return first / max(float(np.linalg.norm(first)), np.finfo(float).tiny)


def _delay_observations(
    channel: np.ndarray,
    reference_channel: np.ndarray,
    predicted_delay: np.ndarray,
    selected_minus_ideal_samples: np.ndarray,
    offsets: np.ndarray,
    tone_hz: np.ndarray,
    sample_rate_hz: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    values = np.empty(len(channel), dtype=float)
    similarities = np.empty(len(channel), dtype=float)
    boundaries = np.empty(len(channel), dtype=bool)
    for index, vector in enumerate(channel):
        candidates = predicted_delay[index] + offsets
        total = selected_minus_ideal_samples[index] - candidates
        ramps = np.exp(-2j * np.pi * total[:, None] * tone_hz[None, :] / sample_rate_hz)
        projections = (ramps * vector[None, :]) @ np.conj(reference_channel)
        best = int(np.argmax(np.abs(projections)))
        values[index] = candidates[best]
        similarities[index] = float(abs(projections[best]))
        boundaries[index] = best in {0, len(offsets) - 1}
    return values, similarities, boundaries


def _delay_align(
    channel: np.ndarray,
    total_delay_samples: np.ndarray,
    tone_hz: np.ndarray,
    sample_rate_hz: float,
) -> np.ndarray:
    ramps = np.exp(-2j * np.pi * total_delay_samples[:, None] * tone_hz[None, :] / sample_rate_hz)
    return channel * ramps


def _integrated_phase(local_time_s: np.ndarray, cfo_hz: float, rate_hz_s: float) -> np.ndarray:
    cycles = cfo_hz * local_time_s + 0.5 * rate_hz_s * local_time_s**2
    return 2 * np.pi * np.remainder(cycles, 1.0)


def _wrap_period(values: npt.ArrayLike, period: float) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    return np.asarray((array + period / 2) % period - period / 2, dtype=float)


def _weighted_rms(values: np.ndarray, weights: np.ndarray) -> float:
    return float(math.sqrt(np.sum(weights * values**2) / np.sum(weights)))


def _optional_float(value: float | None) -> float | None:
    return None if value is None else float(value)


def _odd_validation(
    observations: tuple[FramePhaseRateObservation, ...],
    *,
    local_time_s: np.ndarray,
    predicted_frequency_hz: np.ndarray,
    candidate_frequency_hz: np.ndarray,
    candidate_phase: np.ndarray,
    bits: np.ndarray,
    final_delay: np.ndarray,
    selected_minus_ideal_samples: np.ndarray,
    reference_channel: np.ndarray,
    tone_hz: np.ndarray,
    sample_rate_hz: float,
    base_weight: np.ndarray,
) -> _OddValidation:
    frequency_errors: list[float | None] = [None] * len(observations)
    candidate_frequency_errors: list[float | None] = [None] * len(observations)
    phase_residuals: list[float | None] = [None] * len(observations)
    selected_frequency: list[float] = []
    selected_candidate_frequency: list[float] = []
    selected_phase: list[float] = []
    selected_projection: list[complex] = []
    selected_weight: list[float] = []
    for item in observations:
        if (item.odd_absolute_cfo_hz is None) != (item.odd_channel_vector is None):
            return _invalid_odd_validation(
                len(observations),
                "odd CFO and channel vector are not paired",
            )
        if item.odd_absolute_cfo_hz is None:
            continue
        odd = np.asarray(item.odd_channel_vector)
        if (
            not math.isfinite(item.odd_absolute_cfo_hz)
            or odd.shape != (8,)
            or not np.all(np.isfinite(odd))
            or float(np.linalg.norm(odd)) <= np.finfo(float).tiny
        ):
            return _invalid_odd_validation(
                len(observations),
                "odd-Qin validation contains a malformed held-out observation",
            )
    for index, item in enumerate(observations):
        if item.odd_absolute_cfo_hz is None or item.odd_channel_vector is None:
            continue
        odd_channel = np.asarray(item.odd_channel_vector, dtype=np.complex128).copy()
        norm = float(np.linalg.norm(odd_channel))
        if norm <= np.finfo(float).tiny:
            continue
        odd_channel /= norm
        total_delay = selected_minus_ideal_samples[index] - final_delay[index]
        ramp = np.exp(-2j * np.pi * total_delay * tone_hz / sample_rate_hz)
        projection = complex((odd_channel * ramp) @ np.conj(reference_channel))
        signed_projection = projection * (1 - 2 * int(bits[index]))
        dephased = signed_projection * np.exp(-1j * candidate_phase[index])
        residual = float(np.angle(dephased))
        frequency_error = float(item.odd_absolute_cfo_hz - predicted_frequency_hz[index])
        candidate_frequency_error = float(item.odd_absolute_cfo_hz - candidate_frequency_hz[index])
        frequency_errors[index] = frequency_error
        candidate_frequency_errors[index] = candidate_frequency_error
        phase_residuals[index] = residual
        selected_frequency.append(frequency_error)
        selected_candidate_frequency.append(candidate_frequency_error)
        selected_phase.append(residual)
        selected_projection.append(dephased)
        selected_weight.append(float(base_weight[index]))
    if not selected_frequency:
        return _OddValidation(
            valid=False,
            reason="no usable odd-Qin validation observations",
            count=0,
            cfo_rms_hz=None,
            candidate_cfo_rms_hz=None,
            phase_rms_rad=None,
            stack_efficiency=None,
            frequency_errors=tuple(frequency_errors),
            candidate_frequency_errors=tuple(candidate_frequency_errors),
            phase_residuals=tuple(phase_residuals),
        )
    weights = np.asarray(selected_weight)
    projections = np.asarray(selected_projection)
    stack_efficiency = float(
        abs(np.sum(weights * projections))
        / max(float(np.sum(weights * np.abs(projections))), np.finfo(float).tiny)
    )
    return _OddValidation(
        valid=True,
        reason="odd-Qin validation observations are finite and paired",
        count=len(selected_frequency),
        cfo_rms_hz=_weighted_rms(np.asarray(selected_frequency), weights),
        candidate_cfo_rms_hz=_weighted_rms(np.asarray(selected_candidate_frequency), weights),
        phase_rms_rad=_weighted_rms(np.asarray(selected_phase), weights),
        stack_efficiency=stack_efficiency,
        frequency_errors=tuple(frequency_errors),
        candidate_frequency_errors=tuple(candidate_frequency_errors),
        phase_residuals=tuple(phase_residuals),
    )


def _invalid_odd_validation(frame_count: int, reason: str) -> _OddValidation:
    return _OddValidation(
        valid=False,
        reason=reason,
        count=0,
        cfo_rms_hz=None,
        candidate_cfo_rms_hz=None,
        phase_rms_rad=None,
        stack_efficiency=None,
        frequency_errors=(None,) * frame_count,
        candidate_frequency_errors=(None,) * frame_count,
        phase_residuals=(None,) * frame_count,
    )


def _empty_result(reason: str, frame_count: int) -> FramePhaseRateResult:
    return FramePhaseRateResult(
        status=NumericalStatus.INSUFFICIENT,
        reason=reason,
        frame_count=frame_count,
        validation_frame_count=0,
        reference_time_s=None,
        frequency_only_cfo_hz=None,
        frequency_only_doppler_rate_hz_s=None,
        frequency_only_rate_sigma_hz_s=None,
        phase_candidate_cfo_hz=None,
        phase_candidate_doppler_rate_hz_s=None,
        relative_timing_samples=None,
        relative_timing_rate_samples_s=None,
        relative_timing_boundary_fraction=None,
        iteration_count=0,
        converged=False,
        training_phase_rms_rad=None,
        odd_cfo_rms_hz=None,
        phase_candidate_odd_cfo_rms_hz=None,
        odd_phase_rms_rad=None,
        odd_stack_efficiency=None,
        odd_validation_valid=False,
        odd_validation_reason="odd-Qin validation is unavailable without a complete locklet fit",
        phase_arc_qualified=False,
        phase_arc_reason="phase arc is unavailable without a complete locklet fit",
        phase_feedback_qualified=False,
        phase_feedback_reason="phase feedback is unavailable without a complete locklet fit",
        frames=(),
    )
