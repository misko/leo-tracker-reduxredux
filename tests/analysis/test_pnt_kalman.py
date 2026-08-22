from __future__ import annotations

import numpy as np

from leo.analysis.starlink.phase_doppler import CarrierFrameObservation
from leo.analysis.starlink.pnt_kalman import (
    CodePhaseObservation,
    PntKalmanConfig,
    replay_pnt_kalman,
)


def _carrier(time_s: float, phase: float, doppler: float, container: int):
    return CarrierFrameObservation(
        time_s=time_s,
        phase_cycles=(phase + 0.5) % 1.0 - 0.5,
        doppler_hz=doppler,
        coherence=0.95,
        mean_normalized_power=0.5,
        control_phase_cycles=((0.37 * container + phase) + 0.5) % 1.0 - 0.5,
        control_doppler_hz=doppler,
        control_coherence=0.2,
        container_id=container,
    )


def _synthetic(*, phase_jump: float = 0.0, code_jump_s: float = 0.0):
    frame_period = 1.0 / 750.0
    times = np.arange(0.0, 0.40, frame_period)
    doppler0 = 22_000.0
    rate = -5_900.0
    phase = 0.13 + doppler0 * times + 0.5 * rate * times**2
    phase[times >= 0.20] += phase_jump
    carrier = tuple(
        _carrier(time, value, doppler0 + rate * time, int(time / 0.020))
        for time, value in zip(times, phase, strict=True)
    )
    code_times = np.arange(0.0, 0.40, 0.020)
    code_rate = 8e-6
    code_phase = 0.0002 + code_rate * code_times
    code_phase[code_times >= 0.20] += code_jump_s
    code = tuple(
        CodePhaseObservation(time, value % frame_period, index)
        for index, (time, value) in enumerate(zip(code_times, code_phase, strict=True))
    )
    return carrier, code, rate, code_rate


def test_five_state_filter_recovers_constant_doppler_and_code_rates() -> None:
    carrier, code, rate, code_rate = _synthetic()

    result = replay_pnt_kalman(
        carrier,
        code,
        initial_doppler_rate_hz_s=rate + 100.0,
    )

    assert abs(result.final_state[2] - rate) < 1.0
    assert abs(result.final_state[4] - code_rate) < 1e-7
    assert sum(item.phase_reset for item in result.carrier_steps) == 0
    assert sum(item.code_reset for item in result.code_steps) == 0
    assert all(item.doppler_accepted for item in result.carrier_steps)


def test_phase_jump_resets_phase_without_changing_constant_rate_model() -> None:
    carrier, code, rate, _ = _synthetic(phase_jump=0.25)

    result = replay_pnt_kalman(
        carrier,
        code,
        initial_doppler_rate_hz_s=rate,
    )

    resets = [item for item in result.carrier_steps if item.phase_reset]
    assert len(resets) == 1
    assert abs(abs(resets[0].phase_innovation_cycles) - 0.25) < 1e-6
    assert abs(result.final_state[2] - rate) < 1e-6


def test_code_jump_is_explicit_and_does_not_touch_carrier_state() -> None:
    carrier, code, rate, _ = _synthetic(code_jump_s=0.0003)

    result = replay_pnt_kalman(
        carrier,
        code,
        initial_doppler_rate_hz_s=rate,
        config=PntKalmanConfig(maximum_code_innovation_s=40e-6),
    )

    resets = [item for item in result.code_steps if item.code_reset]
    assert len(resets) == 1
    assert abs(abs(resets[0].code_innovation_s) - 0.0003) < 2e-6
    assert abs(result.final_state[2] - rate) < 1e-6


def test_frequency_only_ablation_is_invariant_to_phase_channel() -> None:
    carrier, code, rate, _ = _synthetic()
    config = PntKalmanConfig(
        apply_phase_updates=False,
        apply_code_updates=False,
        reset_rejected_phase=False,
        reset_rejected_code=False,
    )

    exact = replay_pnt_kalman(
        carrier,
        code,
        initial_doppler_rate_hz_s=rate,
        config=config,
    )
    control = replay_pnt_kalman(
        carrier,
        code,
        initial_doppler_rate_hz_s=rate,
        phase_channel="control",
        config=config,
    )

    assert np.allclose(exact.final_state[:3], control.final_state[:3], atol=1e-12)
