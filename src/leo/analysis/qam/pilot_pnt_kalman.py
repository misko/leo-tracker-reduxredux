"""Research PNT-like Kalman tracking from the known Qin edge pilots.

The continuous state mirrors the carrier/timing state used by Kozhaya,
Saroufim, and Kassas: carrier phase, carrier frequency, carrier-frequency
rate, frame-timing phase, and frame-timing rate.  The measurement model is
adapted to the signal actually available in this repository:

* carrier frequency comes from the within-frame Qin pilot phase slope;
* carrier phase is observed modulo pi because measured edge-pilot channel
  vectors have a repeatable binary sign ambiguity;
* frame timing is a receiver-relative fractional-delay measurement across the
  eight edge subcarriers, not code phase, pseudorange, or transmit time.

Frequency remains linear in time between process-noise updates.  The quadratic
term in the phase transition is only the analytic integral of that constant
frequency rate; this module never fits a quadratic or cubic radio-frequency
trajectory.
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
class PilotPntKalmanConfig:
    """Research defaults for the pilot-only five-state tracker."""

    minimum_exact_coherence: float = 0.02
    minimum_coherence_margin: float = 0.0
    minimum_channel_similarity: float = 0.65
    phase_innovation_gate_rad: float = 1.2
    frequency_innovation_gate_sigma: float = 8.0
    timing_innovation_gate_sigma: float = 8.0
    maximum_frequency_coast_s: float = 0.050
    maximum_phase_coast_s: float = 0.012
    channel_reference_smoothing: float = 0.08
    minimum_phase_measurement_sigma_rad: float = 0.02
    maximum_phase_measurement_sigma_rad: float = 0.50
    minimum_frequency_measurement_sigma_hz: float = 1.0
    minimum_timing_measurement_sigma_samples: float = 0.02
    maximum_fractional_timing_samples: float = 0.75
    fractional_timing_grid_points: int = 301
    initial_doppler_rate_hz_s: float = 0.0
    initial_doppler_rate_sigma_hz_s: float = 20_000.0
    rate_bootstrap_supported_frames: int = 12
    bootstrap_doppler_rate_sigma_hz_s: float = 2_000.0
    maximum_abs_doppler_rate_hz_s: float = 15_000.0
    minimum_phase_lock_supported_frames: int = 20
    minimum_phase_lock_update_fraction: float = 0.80
    maximum_phase_lock_innovation_rms_rad: float = 0.50
    initial_timing_rate_sigma_s_s: float = 1e-4
    doppler_rate_process_sigma_hz_s_sqrt_s: float = 500.0
    timing_rate_process_sigma_s_s_sqrt_s: float = 2e-8
    independent_phase_reacquisition: bool = False

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
            self.timing_innovation_gate_sigma,
            self.maximum_frequency_coast_s,
            self.maximum_phase_coast_s,
            self.minimum_phase_measurement_sigma_rad,
            self.maximum_phase_measurement_sigma_rad,
            self.minimum_frequency_measurement_sigma_hz,
            self.minimum_timing_measurement_sigma_samples,
            self.maximum_fractional_timing_samples,
            self.initial_doppler_rate_sigma_hz_s,
            self.bootstrap_doppler_rate_sigma_hz_s,
            self.maximum_abs_doppler_rate_hz_s,
            self.maximum_phase_lock_innovation_rms_rad,
            self.initial_timing_rate_sigma_s_s,
            self.doppler_rate_process_sigma_hz_s_sqrt_s,
            self.timing_rate_process_sigma_s_s_sqrt_s,
        )
        if any(not math.isfinite(value) or value <= 0 for value in positive):
            raise ValueError("tracking noise, gate, and timing parameters must be positive")
        if self.minimum_phase_measurement_sigma_rad > self.maximum_phase_measurement_sigma_rad:
            raise ValueError("minimum phase sigma exceeds maximum phase sigma")
        if not 3 <= self.fractional_timing_grid_points <= 4_001:
            raise ValueError("fractional timing grid must contain 3..4001 points")
        if self.fractional_timing_grid_points % 2 == 0:
            raise ValueError("fractional timing grid point count must be odd")
        if not 3 <= self.rate_bootstrap_supported_frames <= 100:
            raise ValueError("rate bootstrap must use 3..100 supported frames")
        if not 3 <= self.minimum_phase_lock_supported_frames <= 10_000:
            raise ValueError("phase-lock qualification must use at least three frames")
        if not 0 < self.minimum_phase_lock_update_fraction <= 1:
            raise ValueError("phase-lock update fraction must lie in (0, 1]")
        if not math.isfinite(self.initial_doppler_rate_hz_s):
            raise ValueError("initial Doppler rate must be finite")
        if self.phase_innovation_gate_rad > math.pi / 2:
            raise ValueError("a modulo-pi phase gate cannot exceed pi/2")


@dataclass(frozen=True, slots=True)
class PilotPntKalmanConfigV2(PilotPntKalmanConfig):
    """Corrected phase-loop policy for new, additive scientific products.

    V1 only reacquired when the *frequency* coast expired.  A healthy CFO
    discriminator could therefore keep refreshing the frequency timestamp
    after phase updates stopped, leaving the phase loop permanently unable to
    reacquire.  V2 permits phase-only reacquisition while preserving the
    independently gated frequency and timing states.
    """

    independent_phase_reacquisition: bool = True


@dataclass(frozen=True, slots=True)
class PilotPntKalmanFrame:
    """One causal known-pilot measurement and five-state estimate."""

    frame_index: int
    frame_start_sample: int
    reference_sample: float
    time_s: float
    exact_coherence: float
    control_coherence: float
    coherence_margin: float
    channel_similarity: float
    measurement_supported: bool
    phase_measurement_rad: float
    phase_innovation_modulo_pi_rad: float
    phase_ambiguity_bit: int
    residual_cfo_measurement_hz: float
    absolute_cfo_measurement_hz: float
    frequency_innovation_hz: float
    fractional_timing_measurement_samples: float
    lattice_rounding_correction_samples: float
    timing_innovation_samples: float
    phase_update_applied: bool
    frequency_update_applied: bool
    timing_update_applied: bool
    reacquired: bool
    doppler_rate_bootstrapped: bool
    tracked_phase_modulo_pi_rad: float
    tracked_absolute_cfo_hz: float
    tracked_doppler_rate_hz_s: float
    tracked_fractional_timing_samples: float
    tracked_timing_rate_s_s: float
    phase_sigma_rad: float
    frequency_sigma_hz: float
    doppler_rate_sigma_hz_s: float
    timing_sigma_samples: float


@dataclass(frozen=True, slots=True)
class PilotPntKalmanResult:
    """Research-only PNT-like pilot tracking result."""

    status: NumericalStatus
    frames: tuple[PilotPntKalmanFrame, ...]
    supported_frame_count: int
    phase_update_count: int
    frequency_update_count: int
    timing_update_count: int
    reacquisition_count: int
    rate_bootstrap_frame_index: int | None
    phase_lock_qualified: bool
    phase_lock_reason: str
    phase_ambiguity_transition_count: int
    reason: str
    expected_symbol_roll: int = 0
    carrier_phase_period_rad: float = math.pi
    absolute_carrier_phase_resolved: bool = False
    frame_timing_is_receiver_relative: bool = True
    known_symbols_only: bool = True
    candidate_only: bool = True


def state_transition(dt_s: float) -> np.ndarray:
    """Exact constant-frequency-rate and constant-timing-rate transition."""

    if not math.isfinite(dt_s) or dt_s < 0:
        raise ValueError("Kalman transition interval must be finite and nonnegative")
    return np.asarray(
        (
            (1.0, dt_s, 0.5 * dt_s**2, 0.0, 0.0),
            (0.0, 1.0, dt_s, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 1.0, dt_s),
            (0.0, 0.0, 0.0, 0.0, 1.0),
        ),
        dtype=float,
    )


def process_covariance(
    dt_s: float,
    *,
    doppler_rate_process_sigma_hz_s_sqrt_s: float,
    timing_rate_process_sigma_s_s_sqrt_s: float,
) -> np.ndarray:
    """Continuous-white-noise covariance for the two state chains."""

    if not math.isfinite(dt_s) or dt_s < 0:
        raise ValueError("Kalman covariance interval must be finite and nonnegative")
    values = (
        doppler_rate_process_sigma_hz_s_sqrt_s,
        timing_rate_process_sigma_s_s_sqrt_s,
    )
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("Kalman process noise values must be finite and positive")
    result = np.zeros((5, 5), dtype=float)
    carrier_q = (2 * math.pi * doppler_rate_process_sigma_hz_s_sqrt_s) ** 2
    result[:3, :3] = carrier_q * np.asarray(
        (
            (dt_s**5 / 20, dt_s**4 / 8, dt_s**3 / 6),
            (dt_s**4 / 8, dt_s**3 / 3, dt_s**2 / 2),
            (dt_s**3 / 6, dt_s**2 / 2, dt_s),
        )
    )
    timing_q = timing_rate_process_sigma_s_s_sqrt_s**2
    result[3:, 3:] = timing_q * np.asarray(((dt_s**3 / 3, dt_s**2 / 2), (dt_s**2 / 2, dt_s)))
    return result


def analyze_contiguous_pilot_pnt_kalman(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    epoch_sample: int,
    initial_absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    maximum_residual_cfo_hz: float = 2_000.0,
    expected_symbol_roll: int = 0,
    config: PilotPntKalmanConfig | None = None,
) -> PilotPntKalmanResult:
    """Track pilot phase modulo pi, frequency/rate, and fractional timing."""

    values = np.asarray(samples, dtype=np.complex128)
    selected_edge = StarlinkEdge(edge)
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
    if not isinstance(expected_symbol_roll, int):
        raise ValueError("expected symbol roll must be an integer")
    starts = _complete_frame_starts(values.size, sample_rate_hz, epoch_sample)
    if not starts:
        return _empty(
            NumericalStatus.INSUFFICIENT,
            "window contains no complete known-pilot frame",
            expected_symbol_roll,
        )
    if float(np.mean(np.abs(values) ** 2)) <= np.finfo(float).tiny:
        return _empty(
            NumericalStatus.NO_RESULT,
            "window has zero signal energy",
            expected_symbol_roll,
        )

    settings = config or PilotPntKalmanConfig()
    expected = qin_edge_pilot_symbols(selected_edge, symbol_roll=expected_symbol_roll)
    control_roll = CONTROL_SYMBOL_ROLL if expected_symbol_roll == 0 else 0
    control = qin_edge_pilot_symbols(selected_edge, symbol_roll=control_roll)
    symbol_times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    reference_offset_s = float(np.mean(symbol_times_s))
    centered_times_s = symbol_times_s - reference_offset_s
    timing_grid_samples = np.linspace(
        -settings.maximum_fractional_timing_samples,
        settings.maximum_fractional_timing_samples,
        settings.fractional_timing_grid_points,
    )
    timing_grid_s = timing_grid_samples / sample_rate_hz
    frequencies_hz = edge_frequencies_hz(selected_edge)
    timing_ramps = np.exp(-2j * np.pi * timing_grid_s[:, None] * frequencies_hz[None, :])

    x = np.asarray(
        (
            0.0,
            2 * math.pi * initial_absolute_cfo_hz,
            2 * math.pi * settings.initial_doppler_rate_hz_s,
            0.0,
            0.0,
        ),
        dtype=float,
    )
    covariance = np.diag(
        (
            settings.maximum_phase_measurement_sigma_rad**2,
            (2 * math.pi * maximum_residual_cfo_hz) ** 2,
            (2 * math.pi * settings.initial_doppler_rate_sigma_hz_s) ** 2,
            (settings.maximum_fractional_timing_samples / sample_rate_hz) ** 2,
            settings.initial_timing_rate_sigma_s_s**2,
        )
    )
    channel_reference: np.ndarray | None = None
    previous_time_s: float | None = None
    last_phase_update_s: float | None = None
    last_frequency_update_s: float | None = None
    frames: list[PilotPntKalmanFrame] = []
    frequency_history: list[tuple[float, float]] = []
    rate_bootstrapped = False
    rate_bootstrap_frame_index: int | None = None

    for frame_index, (start, reference_sample) in enumerate(
        zip(starts, (start + reference_offset_s * sample_rate_hz for start in starts), strict=True)
    ):
        time_s = float(reference_sample / sample_rate_hz)
        if previous_time_s is not None:
            dt_s = time_s - previous_time_s
            transition = state_transition(dt_s)
            x = transition @ x
            covariance = transition @ covariance @ transition.T + process_covariance(
                dt_s,
                doppler_rate_process_sigma_hz_s_sqrt_s=(
                    settings.doppler_rate_process_sigma_hz_s_sqrt_s
                ),
                timing_rate_process_sigma_s_s_sqrt_s=(
                    settings.timing_rate_process_sigma_s_s_sqrt_s
                ),
            )
        previous_time_s = time_s
        predicted = x.copy()
        predicted_frequency_hz = float(predicted[1] / (2 * math.pi))
        # Keep each bounded-window frame-CFO measurement independent of the
        # Kalman state. Steering the discriminator with its own estimate made
        # weak-frame rate errors self-confirming in measured IQ. A long-lived
        # loop must reacquire a new bounded anchor before this residual span is
        # exceeded.
        demodulator = _KnownPilotDemodulator(
            values,
            sample_rate_hz,
            selected_edge,
            initial_absolute_cfo_hz,
        )
        pilots = demodulator.frame(start)
        fit = _fit_phase_slope_frame(
            pilots * np.conj(expected),
            pilots * np.conj(control),
            centered_times_s,
            maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        )
        margin = fit.exact_coherence - fit.control_coherence
        phase_sigma = float(
            np.clip(
                fit.phase_residual_rms_rad / math.sqrt(300),
                settings.minimum_phase_measurement_sigma_rad,
                settings.maximum_phase_measurement_sigma_rad,
            )
        )
        frequency_sigma_hz = float(
            max(fit.frequency_uncertainty_hz, settings.minimum_frequency_measurement_sigma_hz)
        )
        timing_sigma_s = max(
            settings.minimum_timing_measurement_sigma_samples / sample_rate_hz,
            float(abs(timing_grid_s[1] - timing_grid_s[0])),
        )
        gauge = 2 * math.pi * initial_absolute_cfo_hz * time_s - float(predicted[0])
        raw_channel = np.asarray(fit.channel_vector) * np.exp(1j * gauge)
        channel_norm = float(np.linalg.norm(raw_channel))
        channel = raw_channel / max(channel_norm, np.finfo(float).tiny)
        supported = bool(
            channel_norm > np.finfo(float).tiny
            and fit.exact_coherence >= settings.minimum_exact_coherence
            and margin >= settings.minimum_coherence_margin
        )
        phase_measurement = 0.0
        phase_innovation = 0.0
        ambiguity_bit = 0
        timing_measurement_s = 0.0
        timing_innovation_s = 0.0
        channel_similarity = 0.0
        absolute_cfo_measurement_hz = float(initial_absolute_cfo_hz + fit.residual_cfo_hz)
        if supported:
            frequency_history.append((time_s, absolute_cfo_measurement_hz))
        frequency_innovation_hz = absolute_cfo_measurement_hz - predicted_frequency_hz
        phase_update = False
        frequency_update = False
        timing_update = False
        reacquired = False

        if channel_reference is None:
            if not supported:
                continue
            channel_reference = channel
            channel_similarity = 1.0
            x[1] += 2 * math.pi * frequency_innovation_hz
            covariance[0, 0] = phase_sigma**2
            covariance[1, 1] = (2 * math.pi * frequency_sigma_hz) ** 2
            covariance[3, 3] = timing_sigma_s**2
            phase_update = frequency_update = timing_update = True
            last_phase_update_s = time_s
            last_frequency_update_s = time_s
        else:
            candidates = timing_ramps * channel[None, :]
            projections = candidates @ np.conj(channel_reference)
            best_timing = int(np.argmax(np.abs(projections)))
            timing_corrected_channel = candidates[best_timing]
            inner = complex(projections[best_timing])
            phase_measurement = float(np.angle(inner))
            channel_similarity = float(abs(inner))
            lattice_rounding_samples = float(
                start - (epoch_sample + frame_index * sample_rate_hz / FRAME_RATE_HZ)
            )
            timing_measurement_s = float(
                (timing_grid_samples[best_timing] - lattice_rounding_samples) / sample_rate_hz
            )
            phase_innovation = _wrap_period(phase_measurement, math.pi)
            ambiguity_bit = int(round((phase_measurement - phase_innovation) / math.pi)) % 2
            frequency_variance_hz2 = covariance[1, 1] / (2 * math.pi) ** 2 + frequency_sigma_hz**2
            timing_variance_s2 = covariance[3, 3] + timing_sigma_s**2
            timing_innovation_s = timing_measurement_s - float(predicted[3])
            frequency_coast_expired = bool(
                last_frequency_update_s is None
                or time_s - last_frequency_update_s > settings.maximum_frequency_coast_s
            )
            phase_coast_expired = bool(
                last_phase_update_s is None
                or time_s - last_phase_update_s > settings.maximum_phase_coast_s
            )
            frequency_reacquired = supported and frequency_coast_expired
            frequency_update = bool(
                supported
                and (
                    frequency_reacquired
                    or abs(frequency_innovation_hz)
                    <= settings.frequency_innovation_gate_sigma
                    * math.sqrt(max(float(frequency_variance_hz2), 0.0))
                )
            )
            timing_update = bool(
                supported
                and channel_similarity >= settings.minimum_channel_similarity
                and abs(timing_innovation_s)
                <= settings.timing_innovation_gate_sigma
                * math.sqrt(max(float(timing_variance_s2), 0.0))
            )
            phase_reacquired = bool(
                settings.independent_phase_reacquisition
                and supported
                and phase_coast_expired
                and frequency_update
                and timing_update
                and not frequency_reacquired
            )
            reacquired = frequency_reacquired or phase_reacquired
            phase_update = bool(
                frequency_update
                and timing_update
                and not frequency_reacquired
                and not phase_coast_expired
                and abs(phase_innovation) <= settings.phase_innovation_gate_rad
            )

            if frequency_reacquired:
                x[1] = predicted[1] + 2 * math.pi * frequency_innovation_hz
                covariance[1, :] = 0.0
                covariance[:, 1] = 0.0
                covariance[1, 1] = (2 * math.pi * frequency_sigma_hz) ** 2
                covariance[2, 2] = max(
                    covariance[2, 2],
                    (2 * math.pi * settings.initial_doppler_rate_sigma_hz_s) ** 2,
                )
                x[3] = timing_measurement_s
                covariance[3, :] = 0.0
                covariance[:, 3] = 0.0
                covariance[3, 3] = timing_sigma_s**2
                if settings.independent_phase_reacquisition:
                    x[0] = predicted[0] + phase_innovation
                    covariance[0, :] = 0.0
                    covariance[:, 0] = 0.0
                    covariance[0, 0] = phase_sigma**2
                channel_reference = timing_corrected_channel * np.exp(-1j * phase_measurement)
                channel_reference /= max(
                    float(np.linalg.norm(channel_reference)), np.finfo(float).tiny
                )
                last_phase_update_s = time_s
                last_frequency_update_s = time_s
                phase_update = timing_update = True
            else:
                if phase_reacquired:
                    # Frequency and timing remain independently observable, so
                    # reset only the lost modulo-pi carrier-phase state.  Move
                    # the state to the nearest observed pi-equivalence class
                    # and establish a fresh channel reference for subsequent
                    # predictive innovations.
                    x[0] = predicted[0] + phase_innovation
                    covariance[0, :] = 0.0
                    covariance[:, 0] = 0.0
                    covariance[0, 0] = phase_sigma**2
                    channel_reference = timing_corrected_channel * np.exp(-1j * phase_measurement)
                    channel_reference /= max(
                        float(np.linalg.norm(channel_reference)), np.finfo(float).tiny
                    )
                    phase_update = True
                    last_phase_update_s = time_s
                rows: list[tuple[np.ndarray, float]] = []
                innovations: list[float] = []
                if phase_update and not phase_reacquired:
                    rows.append((np.asarray((1.0, 0.0, 0.0, 0.0, 0.0)), phase_sigma))
                    innovations.append(phase_innovation)
                if frequency_update:
                    rows.append(
                        (
                            np.asarray((0.0, 1.0, 0.0, 0.0, 0.0)),
                            2 * math.pi * frequency_sigma_hz,
                        )
                    )
                    innovations.append(2 * math.pi * frequency_innovation_hz)
                if timing_update:
                    rows.append((np.asarray((0.0, 0.0, 0.0, 1.0, 0.0)), timing_sigma_s))
                    innovations.append(timing_innovation_s)
                if rows:
                    observation = np.asarray([row[0] for row in rows])
                    noise = np.diag([row[1] ** 2 for row in rows])
                    x, covariance = _error_state_update(
                        x,
                        covariance,
                        np.asarray(innovations),
                        observation,
                        noise,
                    )
                if phase_update and not phase_reacquired:
                    aligned_channel = timing_corrected_channel * np.exp(-1j * phase_measurement)
                    alpha = settings.channel_reference_smoothing
                    channel_reference = (1 - alpha) * channel_reference + alpha * aligned_channel
                    channel_reference /= max(
                        float(np.linalg.norm(channel_reference)), np.finfo(float).tiny
                    )
                    last_phase_update_s = time_s
                if frequency_update:
                    last_frequency_update_s = time_s

        if (
            not rate_bootstrapped
            and len(frequency_history) >= settings.rate_bootstrap_supported_frames
        ):
            bootstrap_time = np.asarray(
                [item[0] for item in frequency_history[: settings.rate_bootstrap_supported_frames]]
            )
            bootstrap_frequency = np.asarray(
                [item[1] for item in frequency_history[: settings.rate_bootstrap_supported_frames]]
            )
            bootstrap_rate, bootstrap_frequency_now = _theil_sen_frequency_state(
                bootstrap_time,
                bootstrap_frequency,
                time_s,
            )
            bootstrap_rate = float(
                np.clip(
                    bootstrap_rate,
                    -settings.maximum_abs_doppler_rate_hz_s,
                    settings.maximum_abs_doppler_rate_hz_s,
                )
            )
            x[1] = 2 * math.pi * bootstrap_frequency_now
            x[2] = 2 * math.pi * bootstrap_rate
            covariance[1, :] = 0.0
            covariance[:, 1] = 0.0
            covariance[1, 1] = (2 * math.pi * frequency_sigma_hz) ** 2
            covariance[2, :] = 0.0
            covariance[:, 2] = 0.0
            covariance[2, 2] = (2 * math.pi * settings.bootstrap_doppler_rate_sigma_hz_s) ** 2
            rate_bootstrapped = True
            rate_bootstrap_frame_index = frame_index
            frequency_update = True
            last_frequency_update_s = time_s
        elif rate_bootstrapped:
            x[2] = float(
                np.clip(
                    x[2],
                    -2 * math.pi * settings.maximum_abs_doppler_rate_hz_s,
                    2 * math.pi * settings.maximum_abs_doppler_rate_hz_s,
                )
            )

        diagonal = np.maximum(np.diag(covariance), 0.0)
        frames.append(
            PilotPntKalmanFrame(
                frame_index=frame_index,
                frame_start_sample=int(start),
                reference_sample=float(reference_sample),
                time_s=time_s,
                exact_coherence=float(fit.exact_coherence),
                control_coherence=float(fit.control_coherence),
                coherence_margin=float(margin),
                channel_similarity=channel_similarity,
                measurement_supported=supported,
                phase_measurement_rad=phase_measurement,
                phase_innovation_modulo_pi_rad=phase_innovation,
                phase_ambiguity_bit=ambiguity_bit,
                residual_cfo_measurement_hz=float(fit.residual_cfo_hz),
                absolute_cfo_measurement_hz=absolute_cfo_measurement_hz,
                frequency_innovation_hz=frequency_innovation_hz,
                fractional_timing_measurement_samples=timing_measurement_s * sample_rate_hz,
                lattice_rounding_correction_samples=(
                    0.0
                    if channel_reference is None
                    else float(
                        start - (epoch_sample + frame_index * sample_rate_hz / FRAME_RATE_HZ)
                    )
                ),
                timing_innovation_samples=timing_innovation_s * sample_rate_hz,
                phase_update_applied=phase_update,
                frequency_update_applied=frequency_update,
                timing_update_applied=timing_update,
                reacquired=reacquired,
                doppler_rate_bootstrapped=rate_bootstrapped,
                tracked_phase_modulo_pi_rad=_wrap_period(float(x[0]), math.pi),
                tracked_absolute_cfo_hz=float(x[1] / (2 * math.pi)),
                tracked_doppler_rate_hz_s=float(x[2] / (2 * math.pi)),
                tracked_fractional_timing_samples=float(x[3] * sample_rate_hz),
                tracked_timing_rate_s_s=float(x[4]),
                phase_sigma_rad=float(math.sqrt(diagonal[0])),
                frequency_sigma_hz=float(math.sqrt(diagonal[1]) / (2 * math.pi)),
                doppler_rate_sigma_hz_s=float(math.sqrt(diagonal[2]) / (2 * math.pi)),
                timing_sigma_samples=float(math.sqrt(diagonal[3]) * sample_rate_hz),
            )
        )

    if not frames:
        return _empty(
            NumericalStatus.NO_RESULT,
            "no frame passed the exact-versus-control pilot gate",
            expected_symbol_roll,
        )
    supported_frames = [frame for frame in frames if frame.measurement_supported]
    ambiguity_bits = [frame.phase_ambiguity_bit for frame in supported_frames]
    supported_count = len(supported_frames)
    phase_update_count = sum(frame.phase_update_applied for frame in frames)
    phase_update_fraction = phase_update_count / supported_count
    innovation_rms = math.sqrt(
        sum(frame.phase_innovation_modulo_pi_rad**2 for frame in supported_frames) / supported_count
    )
    lock_failures = []
    if supported_count < settings.minimum_phase_lock_supported_frames:
        lock_failures.append("too few supported frames")
    if phase_update_fraction < settings.minimum_phase_lock_update_fraction:
        lock_failures.append("phase-update fraction below threshold")
    if innovation_rms > settings.maximum_phase_lock_innovation_rms_rad:
        lock_failures.append("modulo-pi innovation RMS above threshold")
    return PilotPntKalmanResult(
        status=NumericalStatus.COMPLETE,
        frames=tuple(frames),
        supported_frame_count=supported_count,
        phase_update_count=phase_update_count,
        frequency_update_count=sum(frame.frequency_update_applied for frame in frames),
        timing_update_count=sum(frame.timing_update_applied for frame in frames),
        reacquisition_count=sum(frame.reacquired for frame in frames),
        rate_bootstrap_frame_index=rate_bootstrap_frame_index,
        phase_lock_qualified=not lock_failures,
        phase_lock_reason=(
            "qualified modulo-pi phase lock" if not lock_failures else "; ".join(lock_failures)
        ),
        phase_ambiguity_transition_count=sum(
            left != right for left, right in zip(ambiguity_bits, ambiguity_bits[1:], strict=False)
        ),
        reason=(
            "five-state known-pilot tracking with modulo-pi carrier phase and "
            "receiver-relative fractional timing"
        ),
        expected_symbol_roll=expected_symbol_roll,
    )


def analyze_contiguous_pilot_pnt_kalman_v2(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    epoch_sample: int,
    initial_absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    maximum_residual_cfo_hz: float = 2_000.0,
    expected_symbol_roll: int = 0,
    config: PilotPntKalmanConfigV2 | None = None,
) -> PilotPntKalmanResult:
    """Run the corrected independently reacquiring modulo-pi tracker.

    This entry point is deliberately additive.  The V1 function remains
    available for exact replay of persisted V1 products, while all new
    scientific consumers can select the corrected phase-loop semantics
    explicitly.
    """

    settings = config or PilotPntKalmanConfigV2()
    if not settings.independent_phase_reacquisition:
        raise ValueError("PNT Kalman V2 requires independent phase reacquisition")
    return analyze_contiguous_pilot_pnt_kalman(
        samples,
        sample_rate_hz,
        epoch_sample=epoch_sample,
        initial_absolute_cfo_hz=initial_absolute_cfo_hz,
        edge=edge,
        maximum_residual_cfo_hz=maximum_residual_cfo_hz,
        expected_symbol_roll=expected_symbol_roll,
        config=settings,
    )


def _wrap_period(value: float, period: float) -> float:
    return float((value + period / 2) % period - period / 2)


def _error_state_update(
    state: np.ndarray,
    covariance: np.ndarray,
    innovation: np.ndarray,
    observation: np.ndarray,
    noise: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    innovation_covariance = observation @ covariance @ observation.T + noise
    gain = np.linalg.solve(innovation_covariance, observation @ covariance).T
    updated = state + gain @ innovation
    identity = np.eye(5)
    residual = identity - gain @ observation
    updated_covariance = residual @ covariance @ residual.T + gain @ noise @ gain.T
    return updated, 0.5 * (updated_covariance + updated_covariance.T)


def _theil_sen_frequency_state(
    time_s: np.ndarray,
    frequency_hz: np.ndarray,
    evaluation_time_s: float,
) -> tuple[float, float]:
    """Robust causal degree-one bootstrap from a short supported prefix."""

    slopes = [
        (frequency_hz[right] - frequency_hz[left]) / (time_s[right] - time_s[left])
        for left in range(len(time_s) - 1)
        for right in range(left + 1, len(time_s))
        if time_s[right] > time_s[left]
    ]
    if not slopes:
        raise ValueError("rate bootstrap requires observations at two times")
    slope = float(np.median(slopes))
    value = float(np.median(frequency_hz - slope * (time_s - evaluation_time_s)))
    return slope, value


def _empty(status: NumericalStatus, reason: str, expected_symbol_roll: int) -> PilotPntKalmanResult:
    return PilotPntKalmanResult(
        status=status,
        frames=(),
        supported_frame_count=0,
        phase_update_count=0,
        frequency_update_count=0,
        timing_update_count=0,
        reacquisition_count=0,
        rate_bootstrap_frame_index=None,
        phase_lock_qualified=False,
        phase_lock_reason="no supported pilot frames",
        phase_ambiguity_transition_count=0,
        reason=reason,
        expected_symbol_roll=expected_symbol_roll,
    )
