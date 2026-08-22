from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.starlink.frame_phase import (
    circular_concentration,
    estimate_frame_phase_states,
    fit_heldout_constant_phase_increment,
    wrapped_cycle_difference,
)


def _synthetic(reset_cycles: np.ndarray, *, noise: float = 0.03):
    rng = np.random.default_rng(17)
    symbols = 64
    phases = np.exp(2j * np.pi * reset_cycles[:, None])
    exact = phases + noise * (
        rng.normal(size=(len(reset_cycles), symbols))
        + 1j * rng.normal(size=(len(reset_cycles), symbols))
    )
    control = rng.normal(size=exact.shape) + 1j * rng.normal(size=exact.shape)
    exact_power = np.full(exact.shape, 0.7)
    control_power = np.full(exact.shape, 0.05)
    times = np.tile(np.arange(symbols) * 4.4e-6, (len(reset_cycles), 1))
    return exact, control, exact_power, control_power, times


def test_frame_local_phase_survives_arbitrary_interframe_resets() -> None:
    expected = np.asarray((0.10, -0.37, 0.46, -0.02))
    states = estimate_frame_phase_states(*_synthetic(expected))

    observed = np.asarray([state.phase_cycles for state in states])
    assert np.max(np.abs(wrapped_cycle_difference(observed, expected))) < 0.01
    assert min(state.coherence for state in states) > 0.99
    assert max(state.median_absolute_residual_cycles for state in states) < 0.02
    assert max(state.control_coherence for state in states) < 0.3


def test_frame_phase_caps_one_high_energy_outlier() -> None:
    values = _synthetic(np.asarray((0.2,)))
    exact = values[0].copy()
    exact[0, 7] = 1_000.0 * np.exp(-0.4j * np.pi)
    power = values[2].copy()
    power[0, 7] = 1_000_000.0
    states = estimate_frame_phase_states(exact, values[1], power, values[3], values[4])

    assert abs(wrapped_cycle_difference(states[0].phase_cycles, 0.2)) < 0.03


def test_constant_phase_increment_predicts_heldout_frames() -> None:
    indexes = np.arange(15)
    phases = (0.23 + 0.17 * indexes + 0.5) % 1.0 - 0.5

    result = fit_heldout_constant_phase_increment(phases, indexes)

    assert result.increment_cycles_per_frame == pytest.approx(0.17, abs=1 / 4096)
    assert np.max(result.heldout_errors_cycles) < 0.002
    assert result.training_concentration > 0.999


def test_circular_helpers_cover_uniform_and_concentrated_samples() -> None:
    assert circular_concentration(np.zeros(8)) == pytest.approx(1.0)
    assert circular_concentration(np.arange(8) / 8) == pytest.approx(0.0, abs=1e-15)
    assert wrapped_cycle_difference(0.49, -0.49) == pytest.approx(-0.02)


def test_frame_local_phase_rejects_shape_mismatch() -> None:
    values = _synthetic(np.asarray((0.0, 0.1)))
    with pytest.raises(ValueError, match="identical shapes"):
        estimate_frame_phase_states(values[0], values[1][:-1], *values[2:])
