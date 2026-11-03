"""Orbital freedom can erase a position direction that priors then restore."""

import numpy as np
import pytest

from leo.analysis.research.phase_position_identifiability import conditional_position_information


def fragment():
    t = np.linspace(0, 300, 61)
    x = (t - 150) / 150
    return dict(
        component="curve",
        satellite=123,
        times=t,
        group=0,
        rf_ratio=1.0,
        active_curvature=True,
        phase_sensitivity_hz_s=1000 * x * x,
        position_sensitivity_hz_km=np.column_stack([1000 * x * x, 1000 * x**3]),
    )


def test_shared_orbit_phase_removes_one_data_only_position_direction():
    data = fragment()
    fixed = conditional_position_information([data], fitted_c=False)
    phase = conditional_position_information([data], fitted_c=False, phase_sigma_s={123: 0.5})
    assert fixed["data_only"]["position_rank"] == 2
    assert phase["data_only"]["position_rank"] == 1
    assert phase["data_only"]["optimistic_axis_sigma_km"] is None
    assert phase["with_declared_priors"]["position_rank"] == 2
    assert not phase["empirical_confidence"]


def test_linear_tracks_cannot_create_calibration_confidence():
    data = fragment()
    data["active_curvature"] = False
    with pytest.raises(ValueError, match="linear fragments"):
        conditional_position_information([data], fitted_c=False)
