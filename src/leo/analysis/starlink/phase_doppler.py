"""Research primitives for constant-rate carrier phase and Doppler tracking.

The Starlink PNT receiver described by Kozhaya, Saroufim, and Kassas tracks
carrier phase, Doppler, and Doppler rate from matched-filter outputs.  This
module implements the corresponding narrowband Qin-edge-pilot experiment.  It
does not reproduce their blindly estimated full-OFDM beacon or their code loop.

Frequency is always degree one in time.  Integrating that frequency necessarily
gives a quadratic *phase* law; no quadratic or cubic frequency trajectory is
fitted.  Carrier phase is never allowed to bend the Doppler line silently:
inconsistent phase observations are reported as explicit reference resets.
"""

from __future__ import annotations

import math
from collections.abc import Hashable
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

from leo.analysis.robust_linear import HuberLinearFit, fit_huber_linear_irls
from leo.analysis.starlink.frame_phase import wrapped_cycle_difference


@dataclass(frozen=True, slots=True)
class CarrierFrameObservation:
    """One actual-frame prompt phase and frequency-discriminator observation."""

    time_s: float
    phase_cycles: float
    doppler_hz: float
    coherence: float
    mean_normalized_power: float
    control_phase_cycles: float
    control_doppler_hz: float
    control_coherence: float
    container_id: Hashable


@dataclass(frozen=True, slots=True)
class CarrierPhaseTransition:
    """One-step phase prediction made by integrating a degree-one Doppler line."""

    leading_index: int
    trailing_index: int
    start_time_s: float
    stop_time_s: float
    gap_s: float
    same_container: bool
    innovation_cycles: float
    accepted_continuity: bool
    starts_new_episode: bool
    nearest_eighth_cycle: float
    eighth_cycle_error: float


@dataclass(frozen=True, slots=True)
class ConstantRatePhaseDopplerTrack:
    """One robust linear Doppler fit plus auditable phase-continuity episodes."""

    doppler_fit: HuberLinearFit
    observations: tuple[CarrierFrameObservation, ...]
    transitions: tuple[CarrierPhaseTransition, ...]
    episode_ids: tuple[int, ...]
    phase_gate_cycles: float
    maximum_continuous_gap_s: float

    def doppler_hz(self, time_s: npt.ArrayLike) -> np.ndarray:
        times = np.asarray(time_s, dtype=float)
        return self.doppler_fit.intercept_at_reference_hz + self.doppler_fit.slope_hz_per_s * (
            times - self.doppler_fit.reference_time_s
        )


def estimate_frame_carrier_observations(
    exact_values: npt.ArrayLike,
    control_values: npt.ArrayLike,
    exact_power: npt.ArrayLike,
    control_power: npt.ArrayLike,
    times_s: npt.ArrayLike,
    *,
    nco_frequency_hz: float,
    absolute_time_offset_s: float,
    container_id: Hashable,
    residual_frequency_span_hz: float = 1_000.0,
    residual_frequency_step_hz: float = 25.0,
) -> tuple[CarrierFrameObservation, ...]:
    """Estimate prompt phase and residual frequency in every actual frame.

    Inputs are per-symbol matched-filter correlations after wipe-off by one
    constant NCO inside the independently acquired container.  A local
    frequency bank estimates the residual frequency separately in every actual
    frame.  The NCO phase is then restored at the frame midpoint, putting every
    returned phase on the same raw-capture sample-clock reference.

    The symbol-rolled control receives its own frequency maximization.  This is
    intentionally conservative: the null gets the same look-elsewhere freedom
    as the exact Qin pilot.
    """

    exact = _complex_matrix("exact_values", exact_values)
    control = _complex_matrix("control_values", control_values)
    exact_scores = _real_matrix("exact_power", exact_power)
    control_scores = _real_matrix("control_power", control_power)
    moments = _real_matrix("times_s", times_s)
    compared = (control, exact_scores, control_scores, moments)
    if any(value.shape != exact.shape for value in compared):
        raise ValueError("carrier observation inputs must have identical shapes")
    finite = (
        nco_frequency_hz,
        absolute_time_offset_s,
        residual_frequency_span_hz,
        residual_frequency_step_hz,
    )
    if any(not math.isfinite(float(item)) for item in finite):
        raise ValueError("carrier observation configuration must be finite")
    if residual_frequency_span_hz <= 0.0 or residual_frequency_step_hz <= 0.0:
        raise ValueError("residual frequency span and step must be positive")
    grid_count = int(math.floor(2.0 * residual_frequency_span_hz / residual_frequency_step_hz))
    grid = (
        np.arange(grid_count + 1, dtype=float) * residual_frequency_step_hz
        - residual_frequency_span_hz
    )
    if grid[-1] < residual_frequency_span_hz - 1e-9:
        grid = np.append(grid, residual_frequency_span_hz)

    output = []
    for frame_index in range(exact.shape[0]):
        local_midpoint_s = float(np.mean(moments[frame_index]))
        exact_result = _frequency_discriminator(
            exact[frame_index], exact_scores[frame_index], moments[frame_index], grid
        )
        control_result = _frequency_discriminator(
            control[frame_index], control_scores[frame_index], moments[frame_index], grid
        )
        exact_residual_hz, exact_phase, exact_coherence = exact_result
        control_residual_hz, control_phase, control_coherence = control_result
        output.append(
            CarrierFrameObservation(
                time_s=absolute_time_offset_s + local_midpoint_s,
                phase_cycles=_wrap_cycle(exact_phase + nco_frequency_hz * local_midpoint_s),
                doppler_hz=nco_frequency_hz + exact_residual_hz,
                coherence=exact_coherence,
                mean_normalized_power=float(np.mean(exact_scores[frame_index])),
                control_phase_cycles=_wrap_cycle(
                    control_phase + nco_frequency_hz * local_midpoint_s
                ),
                control_doppler_hz=nco_frequency_hz + control_residual_hz,
                control_coherence=control_coherence,
                container_id=container_id,
            )
        )
    return tuple(output)


def fit_constant_rate_phase_doppler(
    observations: tuple[CarrierFrameObservation, ...],
    *,
    phase_channel: Literal["exact", "control"] = "exact",
    initial_doppler_rate_hz_s: float | None = None,
    phase_gate_cycles: float = 0.10,
    maximum_continuous_gap_s: float = 2.25 / 750.0,
    doppler_scale_floor_hz: float = 100.0,
) -> ConstantRatePhaseDopplerTrack:
    """Fit one constant Doppler rate and audit every one-step phase innovation.

    Doppler observations alone determine the robust degree-one frequency model.
    Phase is reserved for a held-separate consistency test: the frequency model
    is integrated between adjacent observations and compared with the measured
    wrapped phase increment.  A failed gate or a time gap starts a new explicit
    phase episode and never changes the Doppler model.
    """

    if len(observations) < 3:
        raise ValueError("phase-Doppler tracking requires at least three observations")
    ordered = tuple(sorted(observations, key=lambda item: item.time_s))
    times = np.asarray([item.time_s for item in ordered], dtype=float)
    if np.any(np.diff(times) <= 0.0):
        raise ValueError("carrier observations must have unique increasing times")
    if not 0.0 < phase_gate_cycles < 0.5:
        raise ValueError("phase gate must lie strictly between zero and half a cycle")
    if maximum_continuous_gap_s <= 0.0 or doppler_scale_floor_hz <= 0.0:
        raise ValueError("gap and Doppler scale floor must be positive")

    if phase_channel == "exact":
        frequencies = np.asarray([item.doppler_hz for item in ordered], dtype=float)
        phases = np.asarray([item.phase_cycles for item in ordered], dtype=float)
    elif phase_channel == "control":
        frequencies = np.asarray([item.control_doppler_hz for item in ordered], dtype=float)
        phases = np.asarray([item.control_phase_cycles for item in ordered], dtype=float)
    else:
        raise ValueError("phase channel must be exact or control")
    reference_time_s = float(np.median(times))
    relative = times - reference_time_s
    ordinary = np.polyfit(relative, frequencies, 1)
    initial_rate = (
        float(ordinary[0])
        if initial_doppler_rate_hz_s is None
        else float(initial_doppler_rate_hz_s)
    )
    doppler = fit_huber_linear_irls(
        times,
        frequencies,
        initial_coefficients_hz=(initial_rate, float(ordinary[1])),
        reference_time_s=reference_time_s,
        scale_floor_hz=doppler_scale_floor_hz,
    )

    transitions = []
    episode_ids = [0]
    episode = 0
    for index in range(1, len(ordered)):
        start = ordered[index - 1]
        stop = ordered[index]
        gap_s = stop.time_s - start.time_s
        start_relative = start.time_s - reference_time_s
        stop_relative = stop.time_s - reference_time_s
        integrated_cycles = (
            doppler.intercept_at_reference_hz * gap_s
            + 0.5 * doppler.slope_hz_per_s * (stop_relative**2 - start_relative**2)
        )
        observed_increment = phases[index] - phases[index - 1]
        innovation = _wrap_cycle(observed_increment - integrated_cycles)
        same_container = start.container_id == stop.container_id
        accepted = abs(innovation) <= phase_gate_cycles
        starts_new = gap_s > maximum_continuous_gap_s or not accepted
        if starts_new:
            episode += 1
        episode_ids.append(episode)
        nearest_eighth = _wrap_cycle(round(innovation * 8.0) / 8.0)
        transitions.append(
            CarrierPhaseTransition(
                leading_index=index - 1,
                trailing_index=index,
                start_time_s=start.time_s,
                stop_time_s=stop.time_s,
                gap_s=gap_s,
                same_container=same_container,
                innovation_cycles=innovation,
                accepted_continuity=accepted,
                starts_new_episode=starts_new,
                nearest_eighth_cycle=nearest_eighth,
                eighth_cycle_error=abs(_wrap_cycle(innovation - nearest_eighth)),
            )
        )
    return ConstantRatePhaseDopplerTrack(
        doppler_fit=doppler,
        observations=ordered,
        transitions=tuple(transitions),
        episode_ids=tuple(episode_ids),
        phase_gate_cycles=phase_gate_cycles,
        maximum_continuous_gap_s=maximum_continuous_gap_s,
    )


def _frequency_discriminator(
    values: np.ndarray,
    normalized_power: np.ndarray,
    times_s: np.ndarray,
    grid_hz: np.ndarray,
) -> tuple[float, float, float]:
    magnitudes = np.abs(values)
    positive = magnitudes > 0.0
    if np.count_nonzero(positive) < 2:
        return 0.0, 0.0, 0.0
    weights = np.sqrt(np.maximum(normalized_power, 0.0))
    median = float(np.median(weights[positive]))
    weights = np.minimum(weights, max(4.0 * median, np.finfo(float).eps))
    weights = np.where(positive, np.maximum(weights, np.finfo(float).eps), 0.0)
    unit = np.divide(values, magnitudes, out=np.zeros_like(values), where=positive)
    midpoint_s = float(np.mean(times_s))
    phase_bank = np.exp(-2j * np.pi * grid_hz[:, None] * (times_s[None, :] - midpoint_s))
    vectors = np.sum(weights[None, :] * unit[None, :] * phase_bank, axis=1)
    best = int(np.argmax(np.abs(vectors)))
    vector = complex(vectors[best])
    coherence = float(abs(vector) / max(float(np.sum(weights)), np.finfo(float).eps))
    return (
        float(grid_hz[best]),
        float(np.angle(vector) / (2.0 * np.pi)),
        coherence,
    )


def _wrap_cycle(value: float) -> float:
    return float(wrapped_cycle_difference(value, 0.0))


def _complex_matrix(name: str, values: npt.ArrayLike) -> np.ndarray:
    result = np.asarray(values, dtype=np.complex128)
    if result.ndim != 2 or not result.shape[0] or result.shape[1] < 2:
        raise ValueError(f"{name} must be a nonempty frame-by-symbol matrix")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be finite")
    return result


def _real_matrix(name: str, values: npt.ArrayLike) -> np.ndarray:
    result = np.asarray(values, dtype=float)
    if result.ndim != 2 or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be one finite frame-by-symbol matrix")
    if "power" in name and np.any(result < 0.0):
        raise ValueError(f"{name} must be nonnegative")
    return result
