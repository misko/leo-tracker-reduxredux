from __future__ import annotations

import numpy as np

from tools.ds7_clock_gate import identifiability, recover_injected_bias


def test_diverse_geometry_identifies_and_recovers_shared_bias() -> None:
    phase = np.linspace(-1.0, 1.0, 41)
    geometry = np.column_stack((phase, phase**2 - np.mean(phase**2)))
    clock = np.ones(phase.size)

    result = identifiability(geometry, clock)

    assert result.identifiable
    assert result.rank == result.columns
    assert result.projected_clock_norm > 0.99
    for injected_hz in (0.0, -250.0, 250.0):
        assert abs(recover_injected_bias(geometry, clock, injected_hz) - injected_hz) < 1e-9


def test_clock_column_confounded_with_position_derivative_is_rejected() -> None:
    phase = np.linspace(-1.0, 1.0, 41)
    clock = 2.0 * phase
    geometry = np.column_stack((phase, phase**2))

    result = identifiability(geometry, clock)

    assert not result.identifiable
    assert result.rank < result.columns
    assert result.projected_clock_norm < 1e-12
