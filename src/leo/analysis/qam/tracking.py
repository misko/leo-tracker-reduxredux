"""Pilot-only carrier phase, Doppler/rate, and frame timing/rate tracking.

The block-diagonal five-state model follows Kozhaya, Saroufim, and Kassas:
phase, phase rate, phase acceleration, frame phase, and frame-rate error.
Unlike their receiver, this module uses only the known Qin edge-pilot sequence.
A slowly varying eight-subcarrier channel vector supplies modulo-pi carrier
phase and modulo-one-sample fractional-delay observations; no proprietary PNT
beacon, code-phase discriminator, or pseudorange is claimed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from leo.analysis.qam.pilot import (
    _complete_frame_starts,
    _fit_phase_slope_frame,
    _FrameSlopeFit,
    _KnownPilotDemodulator,
)
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    edge_frequencies_hz,
    qin_edge_pilot_symbols,
)


@dataclass(frozen=True, slots=True)
class PilotPhaseDopplerTrackingConfig:
    """Research defaults for the five-state wrapped pilot tracker."""

    minimum_exact_coherence: float = 0.02
    minimum_coherence_margin: float = 0.0
    minimum_channel_similarity: float = 0.65
    phase_innovation_gate_rad: float = 1.2
    frequency_innovation_gate_sigma: float = 8.0
    phase_reset_after_failures: int = 2
    maximum_phase_coast_s: float = 0.012
    maximum_frequency_coast_s: float = 0.050
    channel_reference_smoothing: float = 0.08
    minimum_phase_measurement_sigma_rad: float = 0.02
    maximum_phase_measurement_sigma_rad: float = 0.50
    minimum_frequency_measurement_sigma_hz: float = 1.0
    initial_doppler_rate_hz_s: float = 0.0
    initial_doppler_rate_sigma_hz_s: float = 20_000.0
    doppler_rate_process_sigma_hz_s_sqrt_s: float = 500.0
    phase_symmetry_order: int = 2
    compensate_fractional_delay: bool = True
    propagate_frequency_uncertainty_to_phase: bool = True
    maximum_fractional_delay_samples: float = 0.75
    fractional_delay_grid_size: int = 301
    frame_phase_measurement_sigma_samples: float = 0.05
    initial_frame_phase_sigma_samples: float = 0.25
    initial_frame_rate_sigma_samples_s: float = 500.0
    frame_rate_process_sigma_samples_s_sqrt_s: float = 5.0
    frame_innovation_gate_sigma: float = 6.0

    def __post_init__(self) -> None:
        unit_interval = (
            self.minimum_exact_coherence,
            self.minimum_channel_similarity,
            self.channel_reference_smoothing,
        )
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in unit_interval):
            raise ValueError("coherence, similarity, and smoothing must lie in [0, 1]")
        if not math.isfinite(self.minimum_coherence_margin):
            raise ValueError("minimum coherence margin must be finite")
        positive = (
            self.phase_innovation_gate_rad,
            self.frequency_innovation_gate_sigma,
            self.maximum_phase_coast_s,
            self.maximum_frequency_coast_s,
            self.minimum_phase_measurement_sigma_rad,
            self.maximum_phase_measurement_sigma_rad,
            self.minimum_frequency_measurement_sigma_hz,
            self.initial_doppler_rate_sigma_hz_s,
            self.doppler_rate_process_sigma_hz_s_sqrt_s,
            self.maximum_fractional_delay_samples,
            self.frame_phase_measurement_sigma_samples,
            self.initial_frame_phase_sigma_samples,
            self.initial_frame_rate_sigma_samples_s,
            self.frame_rate_process_sigma_samples_s_sqrt_s,
            self.frame_innovation_gate_sigma,
        )
        if any(not math.isfinite(value) or value <= 0 for value in positive):
            raise ValueError("tracking noise and gate parameters must be finite and positive")
        if self.minimum_phase_measurement_sigma_rad > self.maximum_phase_measurement_sigma_rad:
            raise ValueError("minimum phase sigma exceeds maximum phase sigma")
        if self.phase_reset_after_failures <= 0:
            raise ValueError("phase reset failure count must be positive")
        if self.phase_symmetry_order not in (1, 2):
            raise ValueError("phase symmetry order must be one or two")
        if self.fractional_delay_grid_size < 3 or self.fractional_delay_grid_size % 2 == 0:
            raise ValueError("fractional delay grid size must be an odd integer of at least three")
        if not math.isfinite(self.initial_doppler_rate_hz_s):
            raise ValueError("initial Doppler rate must be finite")


@dataclass(frozen=True, slots=True)
class PilotPhaseDopplerTrackFrame:
    frame_index: int
    frame_start_sample: int
    reference_sample: float
    phase_segment_id: int
    phase_measurement_rad: float
    residual_cfo_measurement_hz: float
    absolute_cfo_measurement_hz: float
    frequency_uncertainty_hz: float
    exact_coherence: float
    control_coherence: float
    coherence_margin: float
    channel_similarity: float
    phase_innovation_rad: float
    frequency_innovation_hz: float
    phase_update_applied: bool
    frequency_update_applied: bool
    phase_reset_detected: bool
    tracked_phase_rad: float
    tracked_residual_cfo_hz: float
    tracked_absolute_cfo_hz: float
    tracked_doppler_rate_hz_s: float
    phase_sigma_rad: float
    frequency_sigma_hz: float
    doppler_rate_sigma_hz_s: float
    phase_ambiguity_index: int = 0
    fractional_delay_samples: float = 0.0
    frame_phase_measurement_s: float = 0.0
    frame_phase_innovation_s: float = 0.0
    frame_timing_update_applied: bool = False
    tracked_frame_phase_s: float = 0.0
    tracked_frame_rate_error_s_s: float = 0.0
    frame_phase_sigma_s: float = 0.0
    frame_rate_error_sigma_s_s: float = 0.0


@dataclass(frozen=True, slots=True)
class PilotPhaseDopplerTrackingResult:
    status: NumericalStatus
    frames: tuple[PilotPhaseDopplerTrackFrame, ...]
    phase_segment_count: int
    phase_reset_count: int
    phase_update_count: int
    frequency_update_count: int
    reason: str
    known_symbols_only: bool = True
    candidate_only: bool = True
    phase_continuity_tested: bool = True
    phase_symmetry_order: int = 1
    phase_ambiguity_transition_count: int = 0
    frame_timing_update_count: int = 0


def analyze_pilot_phase_doppler_tracking(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    epoch_sample: int,
    absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    maximum_residual_cfo_hz: float = 2_000.0,
    config: PilotPhaseDopplerTrackingConfig | None = None,
) -> PilotPhaseDopplerTrackingResult:
    """Track carrier phase and Doppler using only complete Qin-pilot frames."""

    values = np.asarray(samples, dtype=np.complex128)
    selected_edge = StarlinkEdge(edge)
    settings = config or PilotPhaseDopplerTrackingConfig()
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample rate must be finite and positive")
    if epoch_sample < 0 or not math.isfinite(absolute_cfo_hz):
        raise ValueError("epoch must be nonnegative and CFO finite")
    if not math.isfinite(maximum_residual_cfo_hz) or maximum_residual_cfo_hz <= 0:
        raise ValueError("maximum residual CFO must be finite and positive")
    if maximum_residual_cfo_hz > 0.5 / OFDM_SYMBOL_DURATION_S:
        raise ValueError("maximum residual CFO exceeds the symbol-rate Nyquist limit")
    if sample_rate_hz < 8 * 234_375.0:
        raise ValueError("sample rate must be at least 1875000 Hz")
    starts = _complete_frame_starts(values.size, sample_rate_hz, epoch_sample)
    if not starts:
        return _empty(
            NumericalStatus.INSUFFICIENT,
            "window contains no complete pilot frame",
            phase_symmetry_order=settings.phase_symmetry_order,
        )
    if float(np.mean(np.abs(values) ** 2)) <= np.finfo(float).tiny:
        return _empty(
            NumericalStatus.NO_RESULT,
            "window has zero signal energy",
            phase_symmetry_order=settings.phase_symmetry_order,
        )

    demodulator = _KnownPilotDemodulator(
        values,
        sample_rate_hz,
        selected_edge,
        absolute_cfo_hz,
    )
    pilots = np.asarray([demodulator.frame(start) for start in starts], dtype=np.complex128)
    expected = qin_edge_pilot_symbols(selected_edge)
    control = qin_edge_pilot_symbols(selected_edge, symbol_roll=CONTROL_SYMBOL_ROLL)
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    reference_offset_s = float(np.mean(times_s))
    centered_times_s = times_s - reference_offset_s
    exact = pilots * np.conj(expected)[None, :, :]
    rolled = pilots * np.conj(control)[None, :, :]
    fits = tuple(
        _fit_phase_slope_frame(
            exact[index],
            rolled[index],
            centered_times_s,
            maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        )
        for index in range(len(starts))
    )
    references = tuple(float(start + reference_offset_s * sample_rate_hz) for start in starts)
    return _track_fits(
        fits,
        starts,
        references,
        sample_rate_hz=sample_rate_hz,
        absolute_cfo_hz=absolute_cfo_hz,
        edge=selected_edge,
        config=settings,
    )


def analyze_contiguous_pilot_phase_doppler_tracking(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    epoch_sample: int,
    initial_absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    maximum_residual_cfo_hz: float = 2_000.0,
    config: PilotPhaseDopplerTrackingConfig | None = None,
) -> PilotPhaseDopplerTrackingResult:
    """Run a closed-loop carrier NCO over a contiguous Qin-pilot frame sequence.

    The predicted phase, frequency, and frequency rate steer each frame's NCO.
    The exact Qin pilot then supplies phase and residual-frequency discriminator
    errors.  Only the initial CFO and frame epoch come from acquisition.
    """

    values = np.asarray(samples, dtype=np.complex128)
    selected_edge = StarlinkEdge(edge)
    settings = config or PilotPhaseDopplerTrackingConfig()
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample rate must be finite and positive")
    if epoch_sample < 0 or not math.isfinite(initial_absolute_cfo_hz):
        raise ValueError("epoch must be nonnegative and initial CFO finite")
    if not math.isfinite(maximum_residual_cfo_hz) or maximum_residual_cfo_hz <= 0:
        raise ValueError("maximum residual CFO must be finite and positive")
    if maximum_residual_cfo_hz > 0.5 / OFDM_SYMBOL_DURATION_S:
        raise ValueError("maximum residual CFO exceeds the symbol-rate Nyquist limit")
    starts = _complete_frame_starts(values.size, sample_rate_hz, epoch_sample)
    if not starts:
        return _empty(
            NumericalStatus.INSUFFICIENT,
            "window contains no complete pilot frame",
            phase_symmetry_order=settings.phase_symmetry_order,
        )
    if float(np.mean(np.abs(values) ** 2)) <= np.finfo(float).tiny:
        return _empty(
            NumericalStatus.NO_RESULT,
            "window has zero signal energy",
            phase_symmetry_order=settings.phase_symmetry_order,
        )

    expected = qin_edge_pilot_symbols(selected_edge)
    control = qin_edge_pilot_symbols(selected_edge, symbol_roll=CONTROL_SYMBOL_ROLL)
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    reference_offset_s = float(np.mean(times_s))
    centered_times_s = times_s - reference_offset_s
    references = tuple(float(start + reference_offset_s * sample_rate_hz) for start in starts)
    return _track_contiguous_frames(
        values,
        starts,
        references,
        sample_rate_hz=sample_rate_hz,
        initial_absolute_cfo_hz=initial_absolute_cfo_hz,
        edge=selected_edge,
        expected=expected,
        control=control,
        centered_times_s=centered_times_s,
        maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        config=settings,
    )


def analyze_locked_pilot_phase_doppler_tracking(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    frame_starts: tuple[int, ...],
    initial_absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    maximum_residual_cfo_hz: float = 2_000.0,
    config: PilotPhaseDopplerTrackingConfig | None = None,
) -> PilotPhaseDopplerTrackingResult:
    """Track across explicit frame epochs supplied by existing Qin-pilot locks."""

    values = np.asarray(samples, dtype=np.complex128)
    selected_edge = StarlinkEdge(edge)
    settings = config or PilotPhaseDopplerTrackingConfig()
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample rate must be finite and positive")
    if not math.isfinite(initial_absolute_cfo_hz):
        raise ValueError("initial CFO must be finite")
    if not math.isfinite(maximum_residual_cfo_hz) or maximum_residual_cfo_hz <= 0:
        raise ValueError("maximum residual CFO must be finite and positive")
    if maximum_residual_cfo_hz > 0.5 / OFDM_SYMBOL_DURATION_S:
        raise ValueError("maximum residual CFO exceeds the symbol-rate Nyquist limit")
    starts = tuple(sorted(set(int(start) for start in frame_starts)))
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    if not starts or starts[0] < 0 or starts[-1] + frame_content > values.size:
        return _empty(
            NumericalStatus.INSUFFICIENT,
            "locked frame epochs exceed the IQ window",
            phase_symmetry_order=settings.phase_symmetry_order,
        )
    if float(np.mean(np.abs(values) ** 2)) <= np.finfo(float).tiny:
        return _empty(
            NumericalStatus.NO_RESULT,
            "window has zero signal energy",
            phase_symmetry_order=settings.phase_symmetry_order,
        )

    expected = qin_edge_pilot_symbols(selected_edge)
    control = qin_edge_pilot_symbols(selected_edge, symbol_roll=CONTROL_SYMBOL_ROLL)
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    reference_offset_s = float(np.mean(times_s))
    references = tuple(float(start + reference_offset_s * sample_rate_hz) for start in starts)
    return _track_contiguous_frames(
        values,
        starts,
        references,
        sample_rate_hz=sample_rate_hz,
        initial_absolute_cfo_hz=initial_absolute_cfo_hz,
        edge=selected_edge,
        expected=expected,
        control=control,
        centered_times_s=times_s - reference_offset_s,
        maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        config=settings,
    )


def _state_transition(dt_s: float) -> np.ndarray:
    return np.asarray(
        (
            (1.0, dt_s, 0.5 * dt_s**2),
            (0.0, 1.0, dt_s),
            (0.0, 0.0, 1.0),
        ),
        dtype=float,
    )


def _process_covariance(dt_s: float, sigma_hz_s_sqrt_s: float) -> np.ndarray:
    q = (2 * math.pi * sigma_hz_s_sqrt_s) ** 2
    return q * np.asarray(
        (
            (dt_s**5 / 20, dt_s**4 / 8, dt_s**3 / 6),
            (dt_s**4 / 8, dt_s**3 / 3, dt_s**2 / 2),
            (dt_s**3 / 6, dt_s**2 / 2, dt_s),
        ),
        dtype=float,
    )


def _wrap_period_rad(value: float, period_rad: float) -> float:
    return float((value + 0.5 * period_rad) % period_rad - 0.5 * period_rad)


def _resolve_phase_symmetry(value_rad: float, order: int) -> tuple[float, int]:
    """Resolve a wrapped phase measurement under a declared rotational symmetry."""

    period_rad = 2 * math.pi / order
    resolved = _wrap_period_rad(value_rad, period_rad)
    ambiguity = int(round((value_rad - resolved) / period_rad)) % order
    return resolved, ambiguity


@lru_cache(maxsize=32)
def _fractional_delay_hypotheses(
    sample_rate_hz: float,
    edge: StarlinkEdge,
    maximum_delay_samples: float,
    grid_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    delays = np.linspace(-maximum_delay_samples, maximum_delay_samples, grid_size)
    frequencies_hz = edge_frequencies_hz(edge)
    ramps = np.exp(-2j * np.pi * delays[:, None] * frequencies_hz[None, :] / sample_rate_hz)
    delays.flags.writeable = False
    ramps.flags.writeable = False
    return delays, ramps


def _channel_phase_observation(
    reference: np.ndarray,
    channel: np.ndarray,
    *,
    sample_rate_hz: float,
    edge: StarlinkEdge,
    config: PilotPhaseDopplerTrackingConfig,
) -> tuple[np.ndarray, float, float, int, float]:
    """Separate fractional delay and declared phase symmetry from one channel vector."""

    if config.compensate_fractional_delay:
        delays, ramps = _fractional_delay_hypotheses(
            sample_rate_hz,
            edge,
            config.maximum_fractional_delay_samples,
            config.fractional_delay_grid_size,
        )
        candidates = ramps * channel[None, :]
        projections = candidates @ np.conj(reference)
        best = int(np.argmax(np.abs(projections)))
        delay_samples = float(delays[best])
        aligned = candidates[best]
        inner = complex(projections[best])
    else:
        delay_samples = 0.0
        aligned = channel
        inner = complex(np.vdot(reference, channel))
    raw_phase = float(np.angle(inner))
    resolved_phase, ambiguity = _resolve_phase_symmetry(
        raw_phase,
        config.phase_symmetry_order,
    )
    period_rad = 2 * math.pi / config.phase_symmetry_order
    canonical = aligned * np.exp(-1j * ambiguity * period_rad)
    return canonical, raw_phase, float(abs(inner)), ambiguity, delay_samples


def _interval_phase_measurement_sigma(
    phase_sigma_rad: float,
    frequency_sigma_hz: float,
    dt_s: float,
) -> float:
    """Include current frame-frequency uncertainty in a cross-frame phase update."""

    return float(math.hypot(phase_sigma_rad, 2 * math.pi * frequency_sigma_hz * dt_s))


def _timing_state_transition(dt_s: float) -> np.ndarray:
    return np.asarray(((1.0, dt_s), (0.0, 1.0)), dtype=float)


def _timing_process_covariance(dt_s: float, rate_sigma_s_s_sqrt_s: float) -> np.ndarray:
    q = rate_sigma_s_s_sqrt_s**2
    return q * np.asarray(
        ((dt_s**3 / 3, dt_s**2 / 2), (dt_s**2 / 2, dt_s)),
        dtype=float,
    )


def _timing_update(
    x: np.ndarray,
    covariance: np.ndarray,
    measurement_s: float,
    *,
    sample_period_s: float,
    measurement_sigma_s: float,
    gate_sigma: float,
) -> tuple[np.ndarray, np.ndarray, float, bool]:
    """Update modulo-one-sample frame phase and its drift."""

    innovation = _wrap_period_rad(measurement_s - float(x[0]), sample_period_s)
    innovation_variance = float(covariance[0, 0] + measurement_sigma_s**2)
    accepted = abs(innovation) <= gate_sigma * math.sqrt(max(innovation_variance, 0.0))
    if not accepted:
        return x, covariance, innovation, False
    observation = np.asarray((1.0, 0.0))
    gain = covariance @ observation / innovation_variance
    updated = x + gain * innovation
    residual = np.eye(2) - np.outer(gain, observation)
    noise = measurement_sigma_s**2
    updated_covariance = residual @ covariance @ residual.T + noise * np.outer(gain, gain)
    return (
        updated,
        0.5 * (updated_covariance + updated_covariance.T),
        innovation,
        True,
    )


def _unit_channel(vector: np.ndarray) -> tuple[np.ndarray, float]:
    norm = float(np.linalg.norm(vector))
    return vector / max(norm, np.finfo(float).tiny), norm


def _measurement_sigmas(
    fit: _FrameSlopeFit,
    config: PilotPhaseDopplerTrackingConfig,
) -> tuple[float, float]:
    # The per-symbol circular residual is averaged over 300 known symbols to
    # form the channel vector.  This is a local thermal-noise approximation;
    # reset gates, rather than this sigma, handle channel/user discontinuity.
    phase = fit.phase_residual_rms_rad / math.sqrt(300)
    phase = float(
        np.clip(
            phase,
            config.minimum_phase_measurement_sigma_rad,
            config.maximum_phase_measurement_sigma_rad,
        )
    )
    frequency = max(fit.frequency_uncertainty_hz, config.minimum_frequency_measurement_sigma_hz)
    return phase, float(frequency)


def _kalman_update(
    x: np.ndarray,
    covariance: np.ndarray,
    measurement: np.ndarray,
    observation: np.ndarray,
    noise: np.ndarray,
    *,
    phase_period_rad: float | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    innovation = measurement - observation @ x
    if phase_period_rad is not None:
        innovation[0] = _wrap_period_rad(float(innovation[0]), phase_period_rad)
    innovation_covariance = observation @ covariance @ observation.T + noise
    gain = np.linalg.solve(innovation_covariance, observation @ covariance).T
    updated = x + gain @ innovation
    identity = np.eye(3)
    residual = identity - gain @ observation
    updated_covariance = residual @ covariance @ residual.T + gain @ noise @ gain.T
    return updated, 0.5 * (updated_covariance + updated_covariance.T), innovation


def _kalman_error_update(
    x: np.ndarray,
    covariance: np.ndarray,
    innovation: np.ndarray,
    observation: np.ndarray,
    noise: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    innovation_covariance = observation @ covariance @ observation.T + noise
    gain = np.linalg.solve(innovation_covariance, observation @ covariance).T
    updated = x + gain @ innovation
    identity = np.eye(3)
    residual = identity - gain @ observation
    updated_covariance = residual @ covariance @ residual.T + gain @ noise @ gain.T
    return updated, 0.5 * (updated_covariance + updated_covariance.T)


def _track_contiguous_frames(
    values: np.ndarray,
    starts: tuple[int, ...],
    references: tuple[float, ...],
    *,
    sample_rate_hz: float,
    initial_absolute_cfo_hz: float,
    edge: StarlinkEdge,
    expected: np.ndarray,
    control: np.ndarray,
    centered_times_s: np.ndarray,
    maximum_residual_cfo_hz: float,
    config: PilotPhaseDopplerTrackingConfig,
) -> PilotPhaseDopplerTrackingResult:
    """Closed-loop error-state kernel used by the contiguous analyzer."""

    x = np.asarray(
        (
            0.0,
            2 * math.pi * initial_absolute_cfo_hz,
            2 * math.pi * config.initial_doppler_rate_hz_s,
        ),
        dtype=float,
    )
    covariance = np.diag(
        (
            config.maximum_phase_measurement_sigma_rad**2,
            (2 * math.pi * maximum_residual_cfo_hz) ** 2,
            (2 * math.pi * config.initial_doppler_rate_sigma_hz_s) ** 2,
        )
    )
    sample_period_s = 1.0 / sample_rate_hz
    frame_measurement_sigma_s = config.frame_phase_measurement_sigma_samples / sample_rate_hz
    timing_x = np.zeros(2, dtype=float)
    timing_covariance = np.diag(
        (
            (config.initial_frame_phase_sigma_samples / sample_rate_hz) ** 2,
            (config.initial_frame_rate_sigma_samples_s / sample_rate_hz) ** 2,
        )
    )
    channel_reference: np.ndarray | None = None
    previous_time_s: float | None = None
    last_phase_update_s: float | None = None
    last_frequency_update_s: float | None = None
    consecutive_phase_failures = 0
    segment_id = 0
    reset_count = 0
    tracked: list[PilotPhaseDopplerTrackFrame] = []

    for index, (start, reference) in enumerate(zip(starts, references, strict=True)):
        time_s = reference / sample_rate_hz
        if previous_time_s is not None:
            dt = time_s - previous_time_s
            transition = _state_transition(dt)
            x = transition @ x
            covariance = transition @ covariance @ transition.T + _process_covariance(
                dt,
                config.doppler_rate_process_sigma_hz_s_sqrt_s,
            )
            timing_transition = _timing_state_transition(dt)
            timing_x = timing_transition @ timing_x
            timing_covariance = (
                timing_transition @ timing_covariance @ timing_transition.T
                + _timing_process_covariance(
                    dt,
                    config.frame_rate_process_sigma_samples_s_sqrt_s / sample_rate_hz,
                )
            )
        previous_time_s = time_s
        predicted_x = x.copy()
        predicted_frequency_hz = float(predicted_x[1] / (2 * math.pi))
        demodulator = _KnownPilotDemodulator(
            values,
            sample_rate_hz,
            edge,
            predicted_frequency_hz,
        )
        pilots = demodulator.frame(start)
        exact = pilots * np.conj(expected)
        rolled = pilots * np.conj(control)
        fit = _fit_phase_slope_frame(
            exact,
            rolled,
            centered_times_s,
            maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        )
        margin = fit.exact_coherence - fit.control_coherence
        phase_sigma, frequency_sigma = _measurement_sigmas(fit, config)
        gauge = 2 * math.pi * predicted_frequency_hz * time_s - float(predicted_x[0])
        channel, channel_norm = _unit_channel(np.asarray(fit.channel_vector) * np.exp(1j * gauge))
        quality = (
            channel_norm > np.finfo(float).tiny
            and fit.exact_coherence >= config.minimum_exact_coherence
            and margin >= config.minimum_coherence_margin
        )

        if channel_reference is None:
            if not quality:
                continue
            channel_reference = channel
            phase_measurement = 0.0
            phase_innovation = 0.0
            phase_ambiguity_index = 0
            fractional_delay_samples = 0.0
            frame_phase_measurement_s = 0.0
            frame_phase_innovation_s = 0.0
            frame_timing_update = True
            timing_x[0] = 0.0
            timing_covariance[0, :] = 0.0
            timing_covariance[:, 0] = 0.0
            timing_covariance[0, 0] = frame_measurement_sigma_s**2
            channel_similarity = 1.0
            frequency_innovation = fit.residual_cfo_hz
            x[1] += 2 * math.pi * frequency_innovation
            covariance[0, 0] = phase_sigma**2
            covariance[1, 1] = (2 * math.pi * frequency_sigma) ** 2
            phase_update = True
            frequency_update = True
            phase_reset = False
            last_phase_update_s = time_s
            last_frequency_update_s = time_s
        else:
            (
                observed_channel,
                phase_measurement,
                channel_similarity,
                phase_ambiguity_index,
                fractional_delay_samples,
            ) = _channel_phase_observation(
                channel_reference,
                channel,
                sample_rate_hz=sample_rate_hz,
                edge=edge,
                config=config,
            )
            phase_innovation, _ = _resolve_phase_symmetry(
                phase_measurement,
                config.phase_symmetry_order,
            )
            frequency_innovation = fit.residual_cfo_hz
            frame_phase_measurement_s = fractional_delay_samples / sample_rate_hz
            frame_phase_innovation_s = _wrap_period_rad(
                frame_phase_measurement_s - float(timing_x[0]),
                sample_period_s,
            )
            frame_timing_update = False
            if quality and channel_similarity >= config.minimum_channel_similarity:
                (
                    timing_x,
                    timing_covariance,
                    frame_phase_innovation_s,
                    frame_timing_update,
                ) = _timing_update(
                    timing_x,
                    timing_covariance,
                    frame_phase_measurement_s,
                    sample_period_s=sample_period_s,
                    measurement_sigma_s=frame_measurement_sigma_s,
                    gate_sigma=config.frame_innovation_gate_sigma,
                )
            frequency_variance = covariance[1, 1] / (2 * math.pi) ** 2 + frequency_sigma**2
            frequency_coast_expired = (
                last_frequency_update_s is None
                or time_s - last_frequency_update_s > config.maximum_frequency_coast_s
            )
            frequency_reacquired = quality and frequency_coast_expired
            frequency_update = bool(
                quality
                and (
                    frequency_reacquired
                    or abs(frequency_innovation)
                    <= config.frequency_innovation_gate_sigma
                    * math.sqrt(max(float(frequency_variance), 0.0))
                )
            )
            coast_expired = (
                last_phase_update_s is None
                or time_s - last_phase_update_s > config.maximum_phase_coast_s
            )
            phase_update = (
                frequency_update
                and not frequency_reacquired
                and not coast_expired
                and channel_similarity >= config.minimum_channel_similarity
                and abs(phase_innovation) <= config.phase_innovation_gate_rad
            )
            phase_reset = False

            if frequency_reacquired:
                x[1] = predicted_x[1] + 2 * math.pi * frequency_innovation
                covariance[1, :] = 0.0
                covariance[:, 1] = 0.0
                covariance[1, 1] = (2 * math.pi * frequency_sigma) ** 2
                covariance[2, 2] = max(
                    covariance[2, 2],
                    (2 * math.pi * config.initial_doppler_rate_sigma_hz_s) ** 2,
                )
                channel_reference = observed_channel
                segment_id += 1
                reset_count += 1
                phase_reset = True
                last_phase_update_s = time_s
                last_frequency_update_s = time_s
                consecutive_phase_failures = 0
            elif phase_update:
                observation = np.asarray(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
                innovation = np.asarray((phase_innovation, 2 * math.pi * frequency_innovation))
                interval_phase_sigma = (
                    _interval_phase_measurement_sigma(
                        phase_sigma,
                        frequency_sigma,
                        time_s
                        - (last_phase_update_s if last_phase_update_s is not None else time_s),
                    )
                    if config.propagate_frequency_uncertainty_to_phase
                    else phase_sigma
                )
                noise = np.diag((interval_phase_sigma**2, (2 * math.pi * frequency_sigma) ** 2))
                x, covariance = _kalman_error_update(
                    x,
                    covariance,
                    innovation,
                    observation,
                    noise,
                )
                phase_correction = float(x[0] - predicted_x[0])
                aligned_channel = observed_channel * np.exp(-1j * phase_correction)
                alpha = config.channel_reference_smoothing
                channel_reference, _ = _unit_channel(
                    (1 - alpha) * channel_reference + alpha * aligned_channel
                )
                consecutive_phase_failures = 0
                last_phase_update_s = time_s
                last_frequency_update_s = time_s
            else:
                if frequency_update:
                    observation = np.asarray(((0.0, 1.0, 0.0),))
                    innovation = np.asarray((2 * math.pi * frequency_innovation,))
                    noise = np.asarray((((2 * math.pi * frequency_sigma) ** 2,),))
                    x, covariance = _kalman_error_update(
                        x,
                        covariance,
                        innovation,
                        observation,
                        noise,
                    )
                    last_frequency_update_s = time_s
                if quality:
                    consecutive_phase_failures += 1
                should_reset = quality and (
                    coast_expired or consecutive_phase_failures >= config.phase_reset_after_failures
                )
                if should_reset:
                    phase_correction = float(x[0] - predicted_x[0])
                    channel_reference = observed_channel * np.exp(-1j * phase_correction)
                    segment_id += 1
                    reset_count += 1
                    phase_reset = True
                    last_phase_update_s = time_s
                    consecutive_phase_failures = 0

        diagonal = np.maximum(np.diag(covariance), 0.0)
        timing_diagonal = np.maximum(np.diag(timing_covariance), 0.0)
        tracked.append(
            PilotPhaseDopplerTrackFrame(
                frame_index=index,
                frame_start_sample=int(start),
                reference_sample=float(reference),
                phase_segment_id=segment_id,
                phase_measurement_rad=phase_measurement,
                residual_cfo_measurement_hz=fit.residual_cfo_hz,
                absolute_cfo_measurement_hz=predicted_frequency_hz + fit.residual_cfo_hz,
                frequency_uncertainty_hz=frequency_sigma,
                exact_coherence=fit.exact_coherence,
                control_coherence=fit.control_coherence,
                coherence_margin=margin,
                channel_similarity=channel_similarity,
                phase_innovation_rad=phase_innovation,
                frequency_innovation_hz=frequency_innovation,
                phase_update_applied=phase_update,
                frequency_update_applied=frequency_update,
                phase_reset_detected=phase_reset,
                tracked_phase_rad=float(x[0]),
                tracked_residual_cfo_hz=float(x[1] / (2 * math.pi) - initial_absolute_cfo_hz),
                tracked_absolute_cfo_hz=float(x[1] / (2 * math.pi)),
                tracked_doppler_rate_hz_s=float(x[2] / (2 * math.pi)),
                phase_sigma_rad=float(math.sqrt(diagonal[0])),
                frequency_sigma_hz=float(math.sqrt(diagonal[1]) / (2 * math.pi)),
                doppler_rate_sigma_hz_s=float(math.sqrt(diagonal[2]) / (2 * math.pi)),
                phase_ambiguity_index=phase_ambiguity_index,
                fractional_delay_samples=fractional_delay_samples,
                frame_phase_measurement_s=frame_phase_measurement_s,
                frame_phase_innovation_s=frame_phase_innovation_s,
                frame_timing_update_applied=frame_timing_update,
                tracked_frame_phase_s=_wrap_period_rad(float(timing_x[0]), sample_period_s),
                tracked_frame_rate_error_s_s=float(timing_x[1]),
                frame_phase_sigma_s=float(math.sqrt(timing_diagonal[0])),
                frame_rate_error_sigma_s_s=float(math.sqrt(timing_diagonal[1])),
            )
        )

    if not tracked:
        return _empty(NumericalStatus.NO_RESULT, "no pilot frame passed the tracking gates")
    return _tracking_result(
        tracked,
        segment_count=segment_id + 1,
        reset_count=reset_count,
        config=config,
        reason="contiguous pilot-only five-state carrier/frame tracking with resets",
    )


def _track_fits(
    fits: tuple[_FrameSlopeFit, ...],
    starts: tuple[int, ...],
    references: tuple[float, ...],
    *,
    sample_rate_hz: float,
    absolute_cfo_hz: float,
    edge: StarlinkEdge,
    config: PilotPhaseDopplerTrackingConfig,
) -> PilotPhaseDopplerTrackingResult:
    """Causal tracker kernel separated from IQ demodulation for qualification."""

    if not (len(fits) == len(starts) == len(references)):
        raise ValueError("fit, start, and reference counts must match")
    x: np.ndarray | None = None
    covariance: np.ndarray | None = None
    channel_reference: np.ndarray | None = None
    previous_reference: float | None = None
    last_phase_update: float | None = None
    consecutive_phase_failures = 0
    segment_id = 0
    reset_count = 0
    tracked: list[PilotPhaseDopplerTrackFrame] = []
    sample_period_s = 1.0 / sample_rate_hz
    frame_measurement_sigma_s = config.frame_phase_measurement_sigma_samples / sample_rate_hz
    timing_x = np.zeros(2, dtype=float)
    timing_covariance = np.diag(
        (
            (config.initial_frame_phase_sigma_samples / sample_rate_hz) ** 2,
            (config.initial_frame_rate_sigma_samples_s / sample_rate_hz) ** 2,
        )
    )

    for index, (fit, start, reference) in enumerate(zip(fits, starts, references, strict=True)):
        time_s = reference / sample_rate_hz
        margin = fit.exact_coherence - fit.control_coherence
        channel, channel_norm = _unit_channel(np.asarray(fit.channel_vector))
        quality = (
            channel_norm > np.finfo(float).tiny
            and fit.exact_coherence >= config.minimum_exact_coherence
            and margin >= config.minimum_coherence_margin
        )
        phase_sigma, frequency_sigma = _measurement_sigmas(fit, config)

        if x is None:
            if not quality:
                continue
            x = np.asarray(
                (
                    0.0,
                    2 * math.pi * fit.residual_cfo_hz,
                    2 * math.pi * config.initial_doppler_rate_hz_s,
                )
            )
            covariance = np.diag(
                (
                    phase_sigma**2,
                    (2 * math.pi * frequency_sigma) ** 2,
                    (2 * math.pi * config.initial_doppler_rate_sigma_hz_s) ** 2,
                )
            )
            channel_reference = channel
            previous_reference = time_s
            last_phase_update = time_s
            phase_measurement = 0.0
            phase_innovation = 0.0
            phase_ambiguity_index = 0
            fractional_delay_samples = 0.0
            frame_phase_measurement_s = 0.0
            frame_phase_innovation_s = 0.0
            frame_timing_update = True
            timing_x[0] = 0.0
            timing_covariance[0, :] = 0.0
            timing_covariance[:, 0] = 0.0
            timing_covariance[0, 0] = frame_measurement_sigma_s**2
            frequency_innovation = 0.0
            phase_update = True
            frequency_update = True
            phase_reset = False
            channel_similarity = 1.0
        else:
            assert covariance is not None
            assert channel_reference is not None
            assert previous_reference is not None
            dt = time_s - previous_reference
            if dt <= 0:
                raise ValueError("frame reference times must increase strictly")
            transition = _state_transition(dt)
            x = transition @ x
            covariance = transition @ covariance @ transition.T + _process_covariance(
                dt,
                config.doppler_rate_process_sigma_hz_s_sqrt_s,
            )
            timing_transition = _timing_state_transition(dt)
            timing_x = timing_transition @ timing_x
            timing_covariance = (
                timing_transition @ timing_covariance @ timing_transition.T
                + _timing_process_covariance(
                    dt,
                    config.frame_rate_process_sigma_samples_s_sqrt_s / sample_rate_hz,
                )
            )
            previous_reference = time_s

            (
                observed_channel,
                phase_measurement,
                channel_similarity,
                phase_ambiguity_index,
                fractional_delay_samples,
            ) = _channel_phase_observation(
                channel_reference,
                channel,
                sample_rate_hz=sample_rate_hz,
                edge=edge,
                config=config,
            )
            resolved_measurement, _ = _resolve_phase_symmetry(
                phase_measurement,
                config.phase_symmetry_order,
            )
            phase_period_rad = 2 * math.pi / config.phase_symmetry_order
            phase_innovation = _wrap_period_rad(
                resolved_measurement - float(x[0]),
                phase_period_rad,
            )
            frame_phase_measurement_s = fractional_delay_samples / sample_rate_hz
            frame_phase_innovation_s = _wrap_period_rad(
                frame_phase_measurement_s - float(timing_x[0]),
                sample_period_s,
            )
            frame_timing_update = False
            if quality and channel_similarity >= config.minimum_channel_similarity:
                (
                    timing_x,
                    timing_covariance,
                    frame_phase_innovation_s,
                    frame_timing_update,
                ) = _timing_update(
                    timing_x,
                    timing_covariance,
                    frame_phase_measurement_s,
                    sample_period_s=sample_period_s,
                    measurement_sigma_s=frame_measurement_sigma_s,
                    gate_sigma=config.frame_innovation_gate_sigma,
                )
            frequency_innovation = fit.residual_cfo_hz - float(x[1] / (2 * math.pi))
            frequency_variance = covariance[1, 1] / (2 * math.pi) ** 2 + frequency_sigma**2
            frequency_update = bool(
                quality
                and abs(frequency_innovation)
                <= config.frequency_innovation_gate_sigma
                * math.sqrt(max(float(frequency_variance), 0.0))
            )
            coast_expired = (
                last_phase_update is None
                or time_s - last_phase_update > config.maximum_phase_coast_s
            )
            phase_update = (
                frequency_update
                and not coast_expired
                and channel_similarity >= config.minimum_channel_similarity
                and abs(phase_innovation) <= config.phase_innovation_gate_rad
            )
            phase_reset = False

            if phase_update:
                observation = np.asarray(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
                measurement = np.asarray((resolved_measurement, 2 * math.pi * fit.residual_cfo_hz))
                interval_phase_sigma = (
                    _interval_phase_measurement_sigma(
                        phase_sigma,
                        frequency_sigma,
                        time_s - (last_phase_update if last_phase_update is not None else time_s),
                    )
                    if config.propagate_frequency_uncertainty_to_phase
                    else phase_sigma
                )
                noise = np.diag((interval_phase_sigma**2, (2 * math.pi * frequency_sigma) ** 2))
                x, covariance, innovation = _kalman_update(
                    x,
                    covariance,
                    measurement,
                    observation,
                    noise,
                    phase_period_rad=phase_period_rad,
                )
                phase_innovation = float(innovation[0])
                frequency_innovation = float(innovation[1] / (2 * math.pi))
                consecutive_phase_failures = 0
                last_phase_update = time_s
                aligned_channel = observed_channel * np.exp(-1j * x[0])
                alpha = config.channel_reference_smoothing
                channel_reference, _ = _unit_channel(
                    (1 - alpha) * channel_reference + alpha * aligned_channel
                )
            else:
                if frequency_update:
                    observation = np.asarray(((0.0, 1.0, 0.0),))
                    measurement = np.asarray((2 * math.pi * fit.residual_cfo_hz,))
                    noise = np.asarray((((2 * math.pi * frequency_sigma) ** 2,),))
                    x, covariance, innovation = _kalman_update(
                        x,
                        covariance,
                        measurement,
                        observation,
                        noise,
                        phase_period_rad=None,
                    )
                    frequency_innovation = float(innovation[0] / (2 * math.pi))
                if quality:
                    consecutive_phase_failures += 1
                should_reset = quality and (
                    coast_expired or consecutive_phase_failures >= config.phase_reset_after_failures
                )
                if should_reset:
                    segment_id += 1
                    reset_count += 1
                    phase_reset = True
                    x[0] = 0.0
                    covariance[0, :] = 0.0
                    covariance[:, 0] = 0.0
                    covariance[0, 0] = phase_sigma**2
                    channel_reference = observed_channel
                    last_phase_update = time_s
                    consecutive_phase_failures = 0

        assert x is not None and covariance is not None
        diagonal = np.maximum(np.diag(covariance), 0.0)
        timing_diagonal = np.maximum(np.diag(timing_covariance), 0.0)
        tracked.append(
            PilotPhaseDopplerTrackFrame(
                frame_index=index,
                frame_start_sample=int(start),
                reference_sample=float(reference),
                phase_segment_id=segment_id,
                phase_measurement_rad=phase_measurement,
                residual_cfo_measurement_hz=fit.residual_cfo_hz,
                absolute_cfo_measurement_hz=absolute_cfo_hz + fit.residual_cfo_hz,
                frequency_uncertainty_hz=frequency_sigma,
                exact_coherence=fit.exact_coherence,
                control_coherence=fit.control_coherence,
                coherence_margin=margin,
                channel_similarity=channel_similarity,
                phase_innovation_rad=phase_innovation,
                frequency_innovation_hz=frequency_innovation,
                phase_update_applied=phase_update,
                frequency_update_applied=frequency_update,
                phase_reset_detected=phase_reset,
                tracked_phase_rad=float(x[0]),
                tracked_residual_cfo_hz=float(x[1] / (2 * math.pi)),
                tracked_absolute_cfo_hz=float(absolute_cfo_hz + x[1] / (2 * math.pi)),
                tracked_doppler_rate_hz_s=float(x[2] / (2 * math.pi)),
                phase_sigma_rad=float(math.sqrt(diagonal[0])),
                frequency_sigma_hz=float(math.sqrt(diagonal[1]) / (2 * math.pi)),
                doppler_rate_sigma_hz_s=float(math.sqrt(diagonal[2]) / (2 * math.pi)),
                phase_ambiguity_index=phase_ambiguity_index,
                fractional_delay_samples=fractional_delay_samples,
                frame_phase_measurement_s=frame_phase_measurement_s,
                frame_phase_innovation_s=frame_phase_innovation_s,
                frame_timing_update_applied=frame_timing_update,
                tracked_frame_phase_s=_wrap_period_rad(float(timing_x[0]), sample_period_s),
                tracked_frame_rate_error_s_s=float(timing_x[1]),
                frame_phase_sigma_s=float(math.sqrt(timing_diagonal[0])),
                frame_rate_error_sigma_s_s=float(math.sqrt(timing_diagonal[1])),
            )
        )

    if not tracked:
        return _empty(NumericalStatus.NO_RESULT, "no pilot frame passed the tracking gates")
    return _tracking_result(
        tracked,
        segment_count=segment_id + 1,
        reset_count=reset_count,
        config=config,
        reason="pilot-only five-state wrapped carrier/frame Kalman tracking with resets",
    )


def _tracking_result(
    tracked: list[PilotPhaseDopplerTrackFrame],
    *,
    segment_count: int,
    reset_count: int,
    config: PilotPhaseDopplerTrackingConfig,
    reason: str,
) -> PilotPhaseDopplerTrackingResult:
    phase_updates = tuple(frame for frame in tracked if frame.phase_update_applied)
    ambiguity_transitions = sum(
        current.phase_ambiguity_index != previous.phase_ambiguity_index
        for previous, current in zip(phase_updates, phase_updates[1:], strict=False)
    )
    return PilotPhaseDopplerTrackingResult(
        status=NumericalStatus.COMPLETE,
        frames=tuple(tracked),
        phase_segment_count=segment_count,
        phase_reset_count=reset_count,
        phase_update_count=len(phase_updates),
        frequency_update_count=sum(frame.frequency_update_applied for frame in tracked),
        reason=reason,
        phase_symmetry_order=config.phase_symmetry_order,
        phase_ambiguity_transition_count=ambiguity_transitions,
        frame_timing_update_count=sum(frame.frame_timing_update_applied for frame in tracked),
    )


def _empty(
    status: NumericalStatus,
    reason: str,
    *,
    phase_symmetry_order: int = 2,
) -> PilotPhaseDopplerTrackingResult:
    return PilotPhaseDopplerTrackingResult(
        status=status,
        frames=(),
        phase_segment_count=0,
        phase_reset_count=0,
        phase_update_count=0,
        frequency_update_count=0,
        reason=reason,
        phase_symmetry_order=phase_symmetry_order,
        frame_timing_update_count=0,
    )
