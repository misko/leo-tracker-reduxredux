"""Five-state Starlink carrier/code Kalman replay for Research analysis.

The state is ``[carrier phase, Doppler, Doppler rate, code phase, code rate]``
in cycles, Hz, Hz/s, seconds, and seconds/second.  This is the unit-scaled
equivalent of the carrier/code state described by Kozhaya, Saroufim, and
Kassas.  Doppler rate and code rate are constant states: the transition adds no
process noise that could silently create a curved frequency trajectory.

Carrier phase and code phase are circular observations.  Failed innovations
are reported as explicit reference resets; they never update Doppler or its
rate.  The implementation consumes already extracted matched-filter
observations and is therefore an offline measurement replay, not yet a raw-IQ
closed loop that drives the next carrier/code wipe-off.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from leo.analysis.starlink.phase_doppler import CarrierFrameObservation


@dataclass(frozen=True, slots=True)
class CodePhaseObservation:
    """One modulo-frame code-phase observation from a GLRT frame epoch."""

    time_s: float
    code_phase_s: float
    container_id: int


@dataclass(frozen=True, slots=True)
class PntKalmanConfig:
    """Transparent noise, gate, and initialization settings for replay."""

    frame_period_s: float = 1.0 / 750.0
    base_phase_sigma_cycles: float = 0.03
    base_doppler_sigma_hz: float = 100.0
    minimum_coherence: float = 0.10
    code_phase_sigma_s: float = 0.8e-6
    phase_gate_cycles: float = 0.10
    doppler_gate_sigma: float = 5.0
    maximum_doppler_innovation_hz: float = 975.0
    code_gate_sigma: float = 6.0
    maximum_code_innovation_s: float = 50e-6
    initial_phase_sigma_cycles: float = 0.25
    initial_doppler_sigma_hz: float = 500.0
    initial_doppler_rate_sigma_hz_s: float = 500.0
    initial_code_phase_sigma_s: float = 0.5 / 750.0
    initial_code_rate_sigma_s_s: float = 50e-6
    apply_phase_updates: bool = True
    apply_code_updates: bool = True
    reset_rejected_phase: bool = True
    reset_rejected_code: bool = True

    def __post_init__(self) -> None:
        positive = (
            self.frame_period_s,
            self.base_phase_sigma_cycles,
            self.base_doppler_sigma_hz,
            self.code_phase_sigma_s,
            self.phase_gate_cycles,
            self.doppler_gate_sigma,
            self.maximum_doppler_innovation_hz,
            self.code_gate_sigma,
            self.maximum_code_innovation_s,
            self.initial_phase_sigma_cycles,
            self.initial_doppler_sigma_hz,
            self.initial_doppler_rate_sigma_hz_s,
            self.initial_code_phase_sigma_s,
            self.initial_code_rate_sigma_s_s,
        )
        if any(not math.isfinite(item) or item <= 0.0 for item in positive):
            raise ValueError("Kalman configuration scales and gates must be finite and positive")
        if not 0.0 < self.minimum_coherence <= 1.0:
            raise ValueError("minimum coherence must lie in (0, 1]")
        if self.phase_gate_cycles >= 0.5:
            raise ValueError("phase gate must be less than half a cycle")
        if self.maximum_code_innovation_s >= 0.5 * self.frame_period_s:
            raise ValueError("code gate must be less than half a frame")


@dataclass(frozen=True, slots=True)
class CarrierKalmanStep:
    """Causal state and innovations at one actual-frame carrier update."""

    time_s: float
    container_id: object
    measured_phase_cycles: float
    predicted_phase_cycles: float
    filtered_phase_cycles: float
    phase_innovation_cycles: float
    phase_accepted: bool
    phase_reset: bool
    measured_doppler_hz: float
    predicted_doppler_hz: float
    filtered_doppler_hz: float
    doppler_innovation_hz: float
    doppler_accepted: bool
    filtered_doppler_rate_hz_s: float
    coherence: float


@dataclass(frozen=True, slots=True)
class CodeKalmanStep:
    """Causal state and wrapped innovation at one container epoch update."""

    time_s: float
    container_id: int
    measured_code_phase_s: float
    predicted_code_phase_s: float
    filtered_code_phase_s: float
    code_innovation_s: float
    code_accepted: bool
    code_reset: bool
    filtered_code_rate_s_s: float


@dataclass(frozen=True, slots=True)
class PntKalmanResult:
    """Complete replay history and final five-state posterior."""

    reference_time_s: float
    initial_doppler_rate_hz_s: float
    carrier_steps: tuple[CarrierKalmanStep, ...]
    code_steps: tuple[CodeKalmanStep, ...]
    final_time_s: float
    final_state: tuple[float, float, float, float, float]
    final_covariance: tuple[tuple[float, ...], ...]
    config: PntKalmanConfig

    def final_doppler_at(self, time_s: float) -> float:
        dt = float(time_s) - self.final_time_s
        return self.final_state[1] + self.final_state[2] * dt


def replay_pnt_kalman(
    carrier_observations: tuple[CarrierFrameObservation, ...],
    code_observations: tuple[CodePhaseObservation, ...],
    *,
    initial_doppler_rate_hz_s: float,
    phase_channel: Literal["exact", "control"] = "exact",
    config: PntKalmanConfig | None = None,
) -> PntKalmanResult:
    """Replay the paper's five-state transition over extracted observations.

    Carrier frequency always uses the exact-pilot discriminator.  Selecting the
    control channel changes only the phase observations, producing a matched
    phase-continuity null under identical Doppler and code dynamics.
    """

    selected_config = PntKalmanConfig() if config is None else config
    config = selected_config
    carriers = tuple(sorted(carrier_observations, key=lambda item: item.time_s))
    codes = tuple(sorted(code_observations, key=lambda item: item.time_s))
    if len(carriers) < 3:
        raise ValueError("Kalman replay requires at least three carrier observations")
    if not codes:
        raise ValueError("Kalman replay requires at least one code observation")
    if any(
        right.time_s <= left.time_s
        for left, right in zip(carriers, carriers[1:], strict=False)
    ):
        raise ValueError("carrier observation times must be unique and increasing")
    if any(
        right.time_s <= left.time_s
        for left, right in zip(codes, codes[1:], strict=False)
    ):
        raise ValueError("code observation times must be unique and increasing")
    if not math.isfinite(initial_doppler_rate_hz_s):
        raise ValueError("initial Doppler rate must be finite")
    if phase_channel not in {"exact", "control"}:
        raise ValueError("phase channel must be exact or control")

    first = carriers[0]
    initial_code = min(codes, key=lambda item: abs(item.time_s - first.time_s))
    first_phase = (
        first.phase_cycles if phase_channel == "exact" else first.control_phase_cycles
    )
    state = np.asarray(
        [
            first_phase,
            first.doppler_hz,
            float(initial_doppler_rate_hz_s),
            initial_code.code_phase_s,
            0.0,
        ],
        dtype=float,
    )
    covariance = np.diag(
        np.square(
            [
                config.initial_phase_sigma_cycles,
                config.initial_doppler_sigma_hz,
                config.initial_doppler_rate_sigma_hz_s,
                config.initial_code_phase_sigma_s,
                config.initial_code_rate_sigma_s_s,
            ]
        )
    )
    current_time = first.time_s
    carrier_steps = [
        CarrierKalmanStep(
            time_s=first.time_s,
            container_id=first.container_id,
            measured_phase_cycles=_wrap_cycles(first_phase),
            predicted_phase_cycles=_wrap_cycles(first_phase),
            filtered_phase_cycles=_wrap_cycles(first_phase),
            phase_innovation_cycles=0.0,
            phase_accepted=True,
            phase_reset=False,
            measured_doppler_hz=first.doppler_hz,
            predicted_doppler_hz=first.doppler_hz,
            filtered_doppler_hz=first.doppler_hz,
            doppler_innovation_hz=0.0,
            doppler_accepted=True,
            filtered_doppler_rate_hz_s=float(initial_doppler_rate_hz_s),
            coherence=(first.coherence if phase_channel == "exact" else first.control_coherence),
        )
    ]
    code_steps = [
        CodeKalmanStep(
            time_s=initial_code.time_s,
            container_id=initial_code.container_id,
            measured_code_phase_s=initial_code.code_phase_s,
            predicted_code_phase_s=initial_code.code_phase_s,
            filtered_code_phase_s=initial_code.code_phase_s,
            code_innovation_s=0.0,
            code_accepted=True,
            code_reset=False,
            filtered_code_rate_s_s=0.0,
        )
    ]

    events = [
        (item.time_s, 1, "carrier", item)
        for item in carriers[1:]
    ] + [
        (item.time_s, 0, "code", item)
        for item in codes
        if item is not initial_code and item.time_s > current_time
    ]
    events.sort(key=lambda item: (item[0], item[1]))
    for event_time, _, kind, observation in events:
        state, covariance = _predict(state, covariance, event_time - current_time)
        current_time = event_time
        if kind == "carrier":
            carrier = observation
            assert isinstance(carrier, CarrierFrameObservation)
            phase = (
                carrier.phase_cycles
                if phase_channel == "exact"
                else carrier.control_phase_cycles
            )
            coherence = (
                carrier.coherence
                if phase_channel == "exact"
                else carrier.control_coherence
            )
            predicted_phase = _wrap_cycles(state[0])
            predicted_doppler = float(state[1])
            doppler_innovation = carrier.doppler_hz - predicted_doppler
            doppler_sigma = config.base_doppler_sigma_hz / max(
                carrier.coherence, config.minimum_coherence
            )
            doppler_limit = min(
                config.maximum_doppler_innovation_hz,
                config.doppler_gate_sigma
                * math.sqrt(covariance[1, 1] + doppler_sigma**2),
            )
            doppler_accepted = (
                carrier.coherence >= config.minimum_coherence
                and abs(doppler_innovation) <= doppler_limit
            )
            if doppler_accepted:
                state, covariance = _scalar_update(
                    state, covariance, 1, doppler_innovation, doppler_sigma**2
                )

            phase_innovation = _wrap_cycles(phase - state[0])
            phase_accepted = (
                coherence >= config.minimum_coherence
                and abs(phase_innovation) <= config.phase_gate_cycles
            )
            phase_reset = False
            if phase_accepted and config.apply_phase_updates:
                phase_sigma = config.base_phase_sigma_cycles / max(
                    coherence, config.minimum_coherence
                )
                state, covariance = _scalar_update(
                    state, covariance, 0, phase_innovation, phase_sigma**2
                )
            elif (
                not phase_accepted
                and config.reset_rejected_phase
                and coherence >= config.minimum_coherence
            ):
                state[0] += phase_innovation
                covariance[0, :] = 0.0
                covariance[:, 0] = 0.0
                covariance[0, 0] = (
                    config.base_phase_sigma_cycles / max(coherence, config.minimum_coherence)
                ) ** 2
                phase_reset = True
            carrier_steps.append(
                CarrierKalmanStep(
                    time_s=carrier.time_s,
                    container_id=carrier.container_id,
                    measured_phase_cycles=_wrap_cycles(phase),
                    predicted_phase_cycles=predicted_phase,
                    filtered_phase_cycles=_wrap_cycles(state[0]),
                    phase_innovation_cycles=phase_innovation,
                    phase_accepted=phase_accepted,
                    phase_reset=phase_reset,
                    measured_doppler_hz=carrier.doppler_hz,
                    predicted_doppler_hz=predicted_doppler,
                    filtered_doppler_hz=float(state[1]),
                    doppler_innovation_hz=doppler_innovation,
                    doppler_accepted=doppler_accepted,
                    filtered_doppler_rate_hz_s=float(state[2]),
                    coherence=coherence,
                )
            )
        else:
            code = observation
            assert isinstance(code, CodePhaseObservation)
            predicted_code = _wrap_period(state[3], config.frame_period_s)
            innovation = _wrap_period_difference(
                code.code_phase_s - state[3], config.frame_period_s
            )
            innovation_sigma = math.sqrt(
                covariance[3, 3] + config.code_phase_sigma_s**2
            )
            code_limit = min(
                config.maximum_code_innovation_s,
                config.code_gate_sigma * innovation_sigma,
            )
            accepted = abs(innovation) <= code_limit
            reset = False
            if accepted and config.apply_code_updates:
                state, covariance = _scalar_update(
                    state,
                    covariance,
                    3,
                    innovation,
                    config.code_phase_sigma_s**2,
                )
            elif not accepted and config.reset_rejected_code:
                state[3] += innovation
                covariance[3, :] = 0.0
                covariance[:, 3] = 0.0
                covariance[3, 3] = config.code_phase_sigma_s**2
                reset = True
            code_steps.append(
                CodeKalmanStep(
                    time_s=code.time_s,
                    container_id=code.container_id,
                    measured_code_phase_s=code.code_phase_s,
                    predicted_code_phase_s=predicted_code,
                    filtered_code_phase_s=_wrap_period(
                        state[3], config.frame_period_s
                    ),
                    code_innovation_s=innovation,
                    code_accepted=accepted,
                    code_reset=reset,
                    filtered_code_rate_s_s=float(state[4]),
                )
            )

    return PntKalmanResult(
        reference_time_s=first.time_s,
        initial_doppler_rate_hz_s=float(initial_doppler_rate_hz_s),
        carrier_steps=tuple(carrier_steps),
        code_steps=tuple(code_steps),
        final_time_s=current_time,
        final_state=tuple(float(item) for item in state),
        final_covariance=tuple(tuple(float(item) for item in row) for row in covariance),
        config=config,
    )


def _predict(
    state: np.ndarray,
    covariance: np.ndarray,
    dt_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    if not math.isfinite(dt_s) or dt_s < 0.0:
        raise ValueError("Kalman event times must be finite and monotonic")
    transition = np.asarray(
        [
            [1.0, dt_s, 0.5 * dt_s**2, 0.0, 0.0],
            [0.0, 1.0, dt_s, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0, dt_s],
            [0.0, 0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    return transition @ state, transition @ covariance @ transition.T


def _scalar_update(
    state: np.ndarray,
    covariance: np.ndarray,
    state_index: int,
    innovation: float,
    measurement_variance: float,
) -> tuple[np.ndarray, np.ndarray]:
    innovation_variance = covariance[state_index, state_index] + measurement_variance
    gain = covariance[:, state_index] / innovation_variance
    updated_state = state + gain * innovation
    identity_minus_gain = np.eye(len(state), dtype=float)
    identity_minus_gain[:, state_index] -= gain
    updated_covariance = (
        identity_minus_gain @ covariance @ identity_minus_gain.T
        + measurement_variance * np.outer(gain, gain)
    )
    updated_covariance = 0.5 * (updated_covariance + updated_covariance.T)
    return updated_state, updated_covariance


def _wrap_cycles(value: float) -> float:
    return float((value + 0.5) % 1.0 - 0.5)


def _wrap_period(value: float, period: float) -> float:
    return float(value % period)


def _wrap_period_difference(value: float, period: float) -> float:
    return float((value + 0.5 * period) % period - 0.5 * period)
