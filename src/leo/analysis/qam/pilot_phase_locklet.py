"""Leakage-safe local modulo-pi phase qualification from known Qin pilots.

The within-frame pilot phase slope and the phase advance between consecutive
frames are distinct measured observables.  Measured Starlink locklets contain a
locally stable offset between them, identifiable modulo half the frame rate.
This module estimates that nuisance offset on a fixed training prefix and
qualifies phase only on later frames.  It never feeds phase back into the
independently measured carrier-frequency or carrier-rate states.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from leo.analysis.qam.pilot import (
    _complete_frame_starts,
    _fit_phase_slope_frame,
    _KnownPilotDemodulator,
)
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    edge_frequencies_hz,
    qin_edge_pilot_symbols,
)


@dataclass(frozen=True, slots=True)
class PilotPhaseLockletConfig:
    """Bounded policy for one prefix-trained, held-out phase locklet."""

    minimum_exact_coherence: float = 0.02
    minimum_coherence_margin: float = 0.0
    minimum_channel_similarity: float = 0.65
    training_interval_count: int = 12
    minimum_held_out_interval_count: int = 20
    phase_innovation_gate_rad: float = 1.2
    minimum_held_out_gate_pass_fraction: float = 0.80
    minimum_training_circular_concentration: float = 0.65
    maximum_training_rms_rad: float = 0.50
    maximum_held_out_rms_rad: float = 0.50
    maximum_fractional_timing_samples: float = 0.75
    fractional_timing_grid_points: int = 301

    def __post_init__(self) -> None:
        unit_interval = (
            self.minimum_exact_coherence,
            self.minimum_channel_similarity,
            self.minimum_held_out_gate_pass_fraction,
            self.minimum_training_circular_concentration,
        )
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in unit_interval):
            raise ValueError("phase-locklet coherence, similarity, and fraction must be in [0, 1]")
        finite = (
            self.minimum_coherence_margin,
            self.phase_innovation_gate_rad,
            self.maximum_training_rms_rad,
            self.maximum_held_out_rms_rad,
            self.maximum_fractional_timing_samples,
        )
        if any(not math.isfinite(value) for value in finite):
            raise ValueError("phase-locklet thresholds must be finite")
        if self.phase_innovation_gate_rad <= 0 or self.phase_innovation_gate_rad > math.pi / 2:
            raise ValueError("modulo-pi phase innovation gate must lie in (0, pi/2]")
        if self.maximum_training_rms_rad <= 0 or self.maximum_held_out_rms_rad <= 0:
            raise ValueError("phase-locklet RMS threshold must be positive")
        if self.maximum_fractional_timing_samples <= 0:
            raise ValueError("phase-locklet timing span must be positive")
        if not 3 <= self.training_interval_count <= 40:
            raise ValueError("phase-locklet training prefix must contain 3..40 intervals")
        if not 3 <= self.minimum_held_out_interval_count <= 80:
            raise ValueError("phase-locklet held-out set must contain at least three intervals")
        if (
            not 3 <= self.fractional_timing_grid_points <= 4_001
            or self.fractional_timing_grid_points % 2 == 0
        ):
            raise ValueError("phase-locklet fractional timing grid must have an odd bounded size")


@dataclass(frozen=True, slots=True)
class PilotPhaseLockletFrame:
    """Independent full-Qin intraframe carrier measurement."""

    frame_index: int
    reference_sample: float
    absolute_cfo_measurement_hz: float
    exact_coherence: float
    control_coherence: float
    coherence_margin: float
    measurement_supported: bool


@dataclass(frozen=True, slots=True)
class PilotPhaseLockletInterval:
    """One adjacent-frame phase comparison in the residual-CFO gauge."""

    previous_frame_index: int
    frame_index: int
    previous_reference_sample: float
    reference_sample: float
    time_delta_s: float
    channel_similarity: float
    previous_intraframe_residual_cfo_hz: float
    intraframe_residual_cfo_hz: float
    measured_phase_advance_modulo_pi_rad: float
    expected_phase_advance_modulo_pi_rad: float
    uncentered_innovation_modulo_pi_rad: float
    centered_innovation_modulo_pi_rad: float | None
    training: bool
    held_out: bool
    gate_passed: bool


@dataclass(frozen=True, slots=True)
class PilotPhaseLockletResult:
    """Prefix-trained nuisance estimate and later-frame phase qualification."""

    status: NumericalStatus
    frames: tuple[PilotPhaseLockletFrame, ...]
    intervals: tuple[PilotPhaseLockletInterval, ...]
    complete_frame_count: int
    supported_frame_count: int
    adjacent_supported_interval_count: int
    training_interval_count: int
    held_out_interval_count: int
    held_out_gate_pass_count: int
    phase_bias_hz_modulo: float | None
    phase_bias_period_hz: float
    training_phase_rms_rad: float | None
    training_circular_concentration: float | None
    held_out_gate_pass_fraction: float | None
    held_out_phase_rms_rad: float | None
    held_out_maximum_absolute_innovation_rad: float | None
    held_out_circular_concentration: float | None
    phase_trackability_qualified: bool
    phase_trackability_reason: str
    carrier_phase_period_rad: float = math.pi
    absolute_carrier_phase_resolved: bool = False
    phase_does_not_update_cfo_or_rate: bool = True
    training_excluded_from_held_out_scoring: bool = True
    held_out_used_for_nuisance_fit: bool = False
    adjacent_one_step_innovations: bool = True
    held_out_gate_does_not_control_future_reference: bool = True
    known_symbols_only: bool = True
    candidate_only: bool = True


@dataclass(frozen=True, slots=True)
class _FrameObservation:
    frame_index: int
    reference_sample: float
    residual_cfo_hz: float
    exact_coherence: float
    control_coherence: float
    supported: bool
    channel: np.ndarray


@dataclass(frozen=True, slots=True)
class _IntervalObservation:
    previous_frame_index: int
    frame_index: int
    previous_reference_sample: float
    reference_sample: float
    time_delta_s: float
    channel_similarity: float
    previous_intraframe_residual_cfo_hz: float
    intraframe_residual_cfo_hz: float
    measured_phase_advance: float
    expected_phase_advance: float
    innovation: float


def analyze_contiguous_pilot_phase_locklet(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    epoch_sample: int,
    initial_absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    maximum_residual_cfo_hz: float = 2_000.0,
    expected_symbol_roll: int = 0,
    config: PilotPhaseLockletConfig | None = None,
) -> PilotPhaseLockletResult:
    """Qualify local modulo-pi phase without allowing it to steer CFO/rate."""

    values = np.asarray(samples, dtype=np.complex128)
    selected_edge = StarlinkEdge(edge)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample rate must be finite and positive")
    if epoch_sample < 0 or not math.isfinite(initial_absolute_cfo_hz):
        raise ValueError("epoch must be nonnegative and initial CFO finite")
    if (
        not math.isfinite(maximum_residual_cfo_hz)
        or maximum_residual_cfo_hz <= 0
        or maximum_residual_cfo_hz > 0.5 / OFDM_SYMBOL_DURATION_S
    ):
        raise ValueError("maximum residual CFO is unsupported")
    if not isinstance(expected_symbol_roll, int):
        raise ValueError("expected symbol roll must be an integer")
    settings = config or PilotPhaseLockletConfig()
    starts = _complete_frame_starts(values.size, sample_rate_hz, epoch_sample)
    if not starts:
        return _empty_result(
            NumericalStatus.INSUFFICIENT,
            "window contains no complete known-pilot frame",
        )
    if float(np.mean(np.abs(values) ** 2)) <= np.finfo(float).tiny:
        return _empty_result(
            NumericalStatus.NO_RESULT,
            "window has zero signal energy",
            complete_frame_count=len(starts),
        )

    expected = qin_edge_pilot_symbols(selected_edge, symbol_roll=expected_symbol_roll)
    control_roll = CONTROL_SYMBOL_ROLL if expected_symbol_roll == 0 else 0
    control = qin_edge_pilot_symbols(selected_edge, symbol_roll=control_roll)
    symbol_times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    reference_offset_s = float(np.mean(symbol_times_s))
    centered_times_s = symbol_times_s - reference_offset_s
    demodulator = _KnownPilotDemodulator(
        values,
        sample_rate_hz,
        selected_edge,
        initial_absolute_cfo_hz,
    )
    frames: list[_FrameObservation] = []
    for frame_index, start in enumerate(starts):
        pilots = demodulator.frame(start)
        fit = _fit_phase_slope_frame(
            pilots * np.conj(expected),
            pilots * np.conj(control),
            centered_times_s,
            maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        )
        channel = np.asarray(fit.channel_vector, dtype=np.complex128)
        norm = float(np.linalg.norm(channel))
        supported = bool(
            norm > np.finfo(float).tiny
            and fit.exact_coherence >= settings.minimum_exact_coherence
            and fit.exact_coherence - fit.control_coherence >= settings.minimum_coherence_margin
        )
        if norm > np.finfo(float).tiny:
            channel = channel / norm
        frames.append(
            _FrameObservation(
                frame_index=frame_index,
                reference_sample=float(start + reference_offset_s * sample_rate_hz),
                residual_cfo_hz=float(fit.residual_cfo_hz),
                exact_coherence=float(fit.exact_coherence),
                control_coherence=float(fit.control_coherence),
                supported=supported,
                channel=_freeze(channel),
            )
        )

    timing_grid_samples = np.linspace(
        -settings.maximum_fractional_timing_samples,
        settings.maximum_fractional_timing_samples,
        num=settings.fractional_timing_grid_points,
    )
    timing_grid_s = timing_grid_samples / sample_rate_hz
    frequencies_hz = edge_frequencies_hz(selected_edge)
    frequencies_hz = frequencies_hz - float(np.mean(frequencies_hz))
    timing_ramps = np.exp(-2j * np.pi * timing_grid_s[:, None] * frequencies_hz[None, :])
    observations: list[_IntervalObservation] = []
    for previous, current in zip(frames, frames[1:], strict=False):
        if not previous.supported or not current.supported:
            continue
        candidates = timing_ramps * current.channel[None, :]
        projections = candidates @ np.conj(previous.channel)
        inner = complex(projections[int(np.argmax(np.abs(projections)))])
        dt_s = float((current.reference_sample - previous.reference_sample) / sample_rate_hz)
        measured = _wrap_period(float(np.angle(inner)), math.pi)
        mean_residual_cfo_hz = 0.5 * (previous.residual_cfo_hz + current.residual_cfo_hz)
        expected_advance = _wrap_period(2 * math.pi * mean_residual_cfo_hz * dt_s, math.pi)
        observations.append(
            _IntervalObservation(
                previous_frame_index=previous.frame_index,
                frame_index=current.frame_index,
                previous_reference_sample=previous.reference_sample,
                reference_sample=current.reference_sample,
                time_delta_s=dt_s,
                channel_similarity=float(abs(inner)),
                previous_intraframe_residual_cfo_hz=previous.residual_cfo_hz,
                intraframe_residual_cfo_hz=current.residual_cfo_hz,
                measured_phase_advance=measured,
                expected_phase_advance=expected_advance,
                innovation=_wrap_period(measured - expected_advance, math.pi),
            )
        )

    # The nuisance fit owns an immutable chronological prefix.  Do not skip a
    # weak early interval and silently recruit later evidence into training:
    # doing so would let held-out support change the fitted model.
    observation_by_frames = {
        (item.previous_frame_index, item.frame_index): item for item in observations
    }
    training_candidates = tuple(
        observation_by_frames.get((index, index + 1))
        for index in range(settings.training_interval_count)
    )
    if any(
        item is None or item.channel_similarity < settings.minimum_channel_similarity
        for item in training_candidates
    ):
        return _insufficient_result(
            starts,
            frames,
            observations,
            initial_absolute_cfo_hz,
            "fixed training prefix lacks channel-supported adjacent intervals",
        )
    training = tuple(item for item in training_candidates if item is not None)
    training_stop_frame = training[-1].frame_index
    held_out = tuple(
        item
        for item in observations
        if item.previous_frame_index >= training_stop_frame
        and item.frame_index == item.previous_frame_index + 1
    )
    bias_hz, training_residuals, training_concentration = _fit_phase_bias_hz(training)
    training_rms = float(np.sqrt(np.mean(training_residuals**2)))
    held_out_residuals = np.asarray(
        [
            _wrap_period(
                item.innovation
                - 2
                * math.pi
                * bias_hz
                * (item.frame_index - item.previous_frame_index)
                / FRAME_RATE_HZ,
                math.pi,
            )
            for item in held_out
        ],
        dtype=float,
    )
    held_out_gate_passes = np.asarray(
        [
            item.channel_similarity >= settings.minimum_channel_similarity
            and abs(residual) <= settings.phase_innovation_gate_rad
            for item, residual in zip(held_out, held_out_residuals, strict=True)
        ],
        dtype=bool,
    )
    held_out_count = len(held_out)
    gate_pass_count = int(np.count_nonzero(held_out_gate_passes))
    gate_pass_fraction = gate_pass_count / held_out_count if held_out_count else None
    rms = float(np.sqrt(np.mean(held_out_residuals**2))) if held_out_count else None
    maximum = float(np.max(np.abs(held_out_residuals))) if held_out_count else None
    concentration = float(abs(np.mean(np.exp(2j * held_out_residuals)))) if held_out_count else None
    failures: list[str] = []
    if training_concentration < settings.minimum_training_circular_concentration:
        failures.append("training phase nuisance is not circularly identifiable")
    if training_rms > settings.maximum_training_rms_rad:
        failures.append("training centered modulo-pi RMS above threshold")
    if held_out_count < settings.minimum_held_out_interval_count:
        failures.append("too few held-out adjacent intervals")
    if (
        gate_pass_fraction is None
        or gate_pass_fraction < settings.minimum_held_out_gate_pass_fraction
    ):
        failures.append("held-out phase gate-pass fraction below threshold")
    if rms is None or rms > settings.maximum_held_out_rms_rad:
        failures.append("held-out centered modulo-pi RMS above threshold")

    training_ids = {(item.previous_frame_index, item.frame_index) for item in training}
    training_by_id = {
        (item.previous_frame_index, item.frame_index): float(residual)
        for item, residual in zip(training, training_residuals, strict=True)
    }
    held_out_by_id = {
        (item.previous_frame_index, item.frame_index): (residual, bool(passed))
        for item, residual, passed in zip(
            held_out,
            held_out_residuals,
            held_out_gate_passes,
            strict=True,
        )
    }
    intervals = tuple(
        PilotPhaseLockletInterval(
            previous_frame_index=item.previous_frame_index,
            frame_index=item.frame_index,
            previous_reference_sample=item.previous_reference_sample,
            reference_sample=item.reference_sample,
            time_delta_s=item.time_delta_s,
            channel_similarity=item.channel_similarity,
            previous_intraframe_residual_cfo_hz=(item.previous_intraframe_residual_cfo_hz),
            intraframe_residual_cfo_hz=item.intraframe_residual_cfo_hz,
            measured_phase_advance_modulo_pi_rad=item.measured_phase_advance,
            expected_phase_advance_modulo_pi_rad=item.expected_phase_advance,
            uncentered_innovation_modulo_pi_rad=item.innovation,
            centered_innovation_modulo_pi_rad=(
                float(held_out_by_id[(item.previous_frame_index, item.frame_index)][0])
                if (item.previous_frame_index, item.frame_index) in held_out_by_id
                else training_by_id.get((item.previous_frame_index, item.frame_index))
            ),
            training=(item.previous_frame_index, item.frame_index) in training_ids,
            held_out=(item.previous_frame_index, item.frame_index) in held_out_by_id,
            gate_passed=(
                held_out_by_id[(item.previous_frame_index, item.frame_index)][1]
                if (item.previous_frame_index, item.frame_index) in held_out_by_id
                else False
            ),
        )
        for item in observations
    )
    qualified = not failures
    return PilotPhaseLockletResult(
        status=NumericalStatus.COMPLETE,
        frames=_public_frames(frames, initial_absolute_cfo_hz),
        intervals=intervals,
        complete_frame_count=len(starts),
        supported_frame_count=sum(item.supported for item in frames),
        adjacent_supported_interval_count=len(observations),
        training_interval_count=len(training),
        held_out_interval_count=held_out_count,
        held_out_gate_pass_count=gate_pass_count,
        phase_bias_hz_modulo=bias_hz,
        phase_bias_period_hz=FRAME_RATE_HZ / 2,
        training_phase_rms_rad=training_rms,
        training_circular_concentration=training_concentration,
        held_out_gate_pass_fraction=gate_pass_fraction,
        held_out_phase_rms_rad=rms,
        held_out_maximum_absolute_innovation_rad=maximum,
        held_out_circular_concentration=concentration,
        phase_trackability_qualified=qualified,
        phase_trackability_reason=(
            "qualified held-out adjacent modulo-pi phase trackability"
            if qualified
            else "; ".join(failures)
        ),
    )


def _fit_phase_bias_hz(
    intervals: tuple[_IntervalObservation, ...],
) -> tuple[float, np.ndarray, float]:
    """Return the closed-form doubled-angle bias modulo 375 Hz."""

    innovations = np.asarray([item.innovation for item in intervals], dtype=float)
    resultant = complex(np.mean(np.exp(2j * innovations)))
    doubled_angle = float(np.angle(resultant))
    if math.isclose(abs(doubled_angle), math.pi, abs_tol=1e-12):
        doubled_angle = -math.pi
    bias_hz = FRAME_RATE_HZ * doubled_angle / (4 * math.pi)
    half_period_hz = FRAME_RATE_HZ / 4
    if bias_hz >= half_period_hz:
        bias_hz -= FRAME_RATE_HZ / 2
    residuals = np.asarray(
        [
            _wrap_period(
                item.innovation
                - 2
                * math.pi
                * bias_hz
                * (item.frame_index - item.previous_frame_index)
                / FRAME_RATE_HZ,
                math.pi,
            )
            for item in intervals
        ],
        dtype=float,
    )
    return float(bias_hz), residuals, float(abs(resultant))


def _insufficient_result(
    starts: tuple[int, ...],
    frames: list[_FrameObservation],
    observations: list[_IntervalObservation],
    initial_absolute_cfo_hz: float,
    reason: str,
) -> PilotPhaseLockletResult:
    return PilotPhaseLockletResult(
        status=NumericalStatus.INSUFFICIENT,
        frames=_public_frames(frames, initial_absolute_cfo_hz),
        intervals=tuple(
            PilotPhaseLockletInterval(
                previous_frame_index=item.previous_frame_index,
                frame_index=item.frame_index,
                previous_reference_sample=item.previous_reference_sample,
                reference_sample=item.reference_sample,
                time_delta_s=item.time_delta_s,
                channel_similarity=item.channel_similarity,
                previous_intraframe_residual_cfo_hz=(item.previous_intraframe_residual_cfo_hz),
                intraframe_residual_cfo_hz=item.intraframe_residual_cfo_hz,
                measured_phase_advance_modulo_pi_rad=item.measured_phase_advance,
                expected_phase_advance_modulo_pi_rad=item.expected_phase_advance,
                uncentered_innovation_modulo_pi_rad=item.innovation,
                centered_innovation_modulo_pi_rad=None,
                training=False,
                held_out=False,
                gate_passed=False,
            )
            for item in observations
        ),
        complete_frame_count=len(starts),
        supported_frame_count=sum(item.supported for item in frames),
        adjacent_supported_interval_count=len(observations),
        training_interval_count=0,
        held_out_interval_count=0,
        held_out_gate_pass_count=0,
        phase_bias_hz_modulo=None,
        phase_bias_period_hz=FRAME_RATE_HZ / 2,
        training_phase_rms_rad=None,
        training_circular_concentration=None,
        held_out_gate_pass_fraction=None,
        held_out_phase_rms_rad=None,
        held_out_maximum_absolute_innovation_rad=None,
        held_out_circular_concentration=None,
        phase_trackability_qualified=False,
        phase_trackability_reason=reason,
    )


def _empty_result(
    status: NumericalStatus,
    reason: str,
    *,
    complete_frame_count: int = 0,
) -> PilotPhaseLockletResult:
    return PilotPhaseLockletResult(
        status=status,
        frames=(),
        intervals=(),
        complete_frame_count=complete_frame_count,
        supported_frame_count=0,
        adjacent_supported_interval_count=0,
        training_interval_count=0,
        held_out_interval_count=0,
        held_out_gate_pass_count=0,
        phase_bias_hz_modulo=None,
        phase_bias_period_hz=FRAME_RATE_HZ / 2,
        training_phase_rms_rad=None,
        training_circular_concentration=None,
        held_out_gate_pass_fraction=None,
        held_out_phase_rms_rad=None,
        held_out_maximum_absolute_innovation_rad=None,
        held_out_circular_concentration=None,
        phase_trackability_qualified=False,
        phase_trackability_reason=reason,
    )


def _wrap_period(value: float, period: float) -> float:
    return float((value + 0.5 * period) % period - 0.5 * period)


def _public_frames(
    frames: list[_FrameObservation],
    initial_absolute_cfo_hz: float,
) -> tuple[PilotPhaseLockletFrame, ...]:
    return tuple(
        PilotPhaseLockletFrame(
            frame_index=item.frame_index,
            reference_sample=item.reference_sample,
            absolute_cfo_measurement_hz=initial_absolute_cfo_hz + item.residual_cfo_hz,
            exact_coherence=item.exact_coherence,
            control_coherence=item.control_coherence,
            coherence_margin=item.exact_coherence - item.control_coherence,
            measurement_supported=item.supported,
        )
        for item in frames
    )


def _freeze(values: np.ndarray) -> np.ndarray:
    output = np.asarray(values).copy()
    output.flags.writeable = False
    return output


__all__ = [
    "PilotPhaseLockletConfig",
    "PilotPhaseLockletFrame",
    "PilotPhaseLockletInterval",
    "PilotPhaseLockletResult",
    "analyze_contiguous_pilot_phase_locklet",
]
