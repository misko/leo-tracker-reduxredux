"""Immutable phase-grid interpolation, independent of the trial receiver position."""

from dataclasses import dataclass

import numpy as np

from leo.analysis.research.continuous_curve_fit import (
    paired_phase_states,
    phase_frequency_from_states,
)
from leo.analysis.research.orbit_uncertainty import frequency_modes_from_states


@dataclass(frozen=True)
class PreparedPhaseGeometry:
    position_km: np.ndarray
    velocity_km_s: np.ndarray
    mode_position_km: np.ndarray
    mode_velocity_km_s: np.ndarray

    def evaluate(self, latitude, longitude, *, altitude_m=0.0):
        frequency, elevation = phase_frequency_from_states(
            self.position_km, self.velocity_km_s, latitude, longitude, altitude_m=altitude_m
        )
        modes = frequency_modes_from_states(
            self.position_km, self.velocity_km_s, self.mode_position_km,
            self.mode_velocity_km_s, latitude, longitude, altitude_m=altitude_m
        )
        return frequency, elevation, modes


def prepare_phase_geometry(bank, mode_bank, times, labels, phases):
    """Snapshot the exact existing interpolation; no cross-family/global cache.

    Callers create another snapshot when their phase grid or orbit bank changes.
    Output states own their storage and cannot be modified through input arrays.
    """
    position, velocity = paired_phase_states(bank, times, labels, phases)
    satellites = len(np.asarray(phases))
    if satellites < 1:
        raise ValueError("nonempty satellite phase grid required")
    count = np.asarray(mode_bank["position_km"]).shape[0] // satellites
    if count < 1 or count * satellites != np.asarray(mode_bank["position_km"]).shape[0]:
        raise ValueError("equal positive mode count per satellite required")
    expanded = (np.asarray(labels)[:, None] * count + np.arange(count)).ravel()
    dp, dv = paired_phase_states(
        mode_bank, np.repeat(times, count), expanded, np.repeat(phases, count)
    )
    dp, dv = dp.reshape(-1, count, 3), dv.reshape(-1, count, 3)
    for values in (position, velocity, dp, dv):
        values.setflags(write=False)
    return PreparedPhaseGeometry(position, velocity, dp, dv)
