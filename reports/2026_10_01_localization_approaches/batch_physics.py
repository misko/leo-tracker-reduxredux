"""Compact batched linearizations for the frozen fixed-height physics."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026_10_01_fixed_height_greedy"))
from acquire import LIGHT_KM_S, WGS84_A_KM, WGS84_F, enu_state_ecef_km  # noqa: E402, I001


_STATE_STEP = 1e-4
_HEIGHT_GRADIENT_STEP_KM = 1e-3


def _height_gradient(height, east: float, north: float) -> tuple[float, float]:
    step = _HEIGHT_GRADIENT_STEP_KM
    east_gradient = (height(east + step, north) - height(east - step, north)) / (2 * step)
    north_gradient = (height(east, north + step) - height(east, north - step)) / (2 * step)
    if not np.isfinite(east_gradient) or not np.isfinite(north_gradient):
        raise ValueError("fixed height surface has a nonfinite numerical gradient")
    return float(east_gradient), float(north_gradient)


def _means_and_visibility(port, receiver, position, velocity, drift):
    line = position - receiver
    unit = line / np.linalg.norm(line, axis=2, keepdims=True)
    doppler = (
        port.config.doppler_sign
        * port.config.reference_frequency_hz
        / LIGHT_KM_S
        * np.sum(velocity * unit, axis=2)
    )
    means = (doppler + drift[None, :]) @ port.likelihood.contrasts.T
    semiminor = WGS84_A_KM * (1 - WGS84_F)
    up = receiver / np.array([WGS84_A_KM**2, WGS84_A_KM**2, semiminor**2])
    up /= np.linalg.norm(up)
    elevations = np.degrees(np.arcsin(np.clip(unit @ up, -1, 1)))
    eligible = np.all(elevations >= -port.config.horizon_margin_deg, axis=1)
    return means, eligible


def linearize_candidates(port, state, indices):
    """Linearize requested candidates into six compact original-state columns.

    The compact coordinates for satellite ``s`` are
    ``[east, north, clock, drift_0, drift_1, epoch_s]``.  Numerical steps and
    fixed-height chain rules match the frozen per-candidate physics exactly.
    """
    state = np.asarray(state, dtype=np.float64)
    selected = np.asarray(indices, dtype=np.int64)
    count = int(port.candidate_count)
    if state.shape != (5 + count,) or not np.all(np.isfinite(state)):
        raise ValueError("invalid state")
    if (selected.ndim != 1 or selected.size == 0
            or np.any(selected < 0) or np.any(selected >= count)
            or np.unique(selected).size != selected.size):
        raise ValueError("indices must be a non-empty unique in-range vector")
    # This includes every catalogue epoch at base and clock +/- the frozen step.
    port._global_support(state)

    east, north = float(state[0]), float(state[1])
    height = float(port.height(east, north))
    if not np.isfinite(height):
        raise ValueError("fixed height surface returned a nonfinite height")
    def receiver(e, n, h):
        return enu_state_ecef_km(
            e, n, h, port.config.prior_center_lat_deg, port.config.prior_center_lon_deg
        )
    receivers = (
        receiver(east, north, height),
        receiver(east + _STATE_STEP, north, height),
        receiver(east - _STATE_STEP, north, height),
        receiver(east, north + _STATE_STEP, height),
        receiver(east, north - _STATE_STEP, height),
        receiver(east, north, height + _STATE_STEP),
        receiver(east, north, height - _STATE_STEP),
    )

    offsets = state[2] + state[5:]
    base_position, base_velocity = port.likelihood._orbit_states_per_satellite(offsets)
    plus_position, plus_velocity = port.likelihood._orbit_states_per_satellite(
        offsets + _STATE_STEP
    )
    minus_position, minus_velocity = port.likelihood._orbit_states_per_satellite(
        offsets - _STATE_STEP
    )
    base_position, base_velocity = base_position[selected], base_velocity[selected]
    plus_position, plus_velocity = plus_position[selected], plus_velocity[selected]
    minus_position, minus_velocity = minus_position[selected], minus_velocity[selected]

    centered = port.likelihood.centered_times
    drift = state[3 + port.likelihood.receiver_indices] * port.likelihood.drift_scale * centered
    base, eligible = _means_and_visibility(
        port, receivers[0], base_position, base_velocity, drift
    )
    spatial_height_means = [
        _means_and_visibility(port, item, base_position, base_velocity, drift)[0]
        for item in receivers[1:]
    ]
    clock_plus = _means_and_visibility(
        port, receivers[0], plus_position, plus_velocity, drift
    )[0]
    clock_minus = _means_and_visibility(
        port, receivers[0], minus_position, minus_velocity, drift
    )[0]

    east_gradient, north_gradient = _height_gradient(port.height, east, north)
    height_derivative = (
        spatial_height_means[4] - spatial_height_means[5]
    ) / (2 * _STATE_STEP)
    jacobians = np.empty((selected.size, base.shape[1], 6), dtype=np.float64)
    jacobians[:, :, 0] = (
        (spatial_height_means[0] - spatial_height_means[1]) / (2 * _STATE_STEP)
        + height_derivative * east_gradient
    )
    jacobians[:, :, 1] = (
        (spatial_height_means[2] - spatial_height_means[3]) / (2 * _STATE_STEP)
        + height_derivative * north_gradient
    )
    jacobians[:, :, 2] = (clock_plus - clock_minus) / (2 * _STATE_STEP)
    drift_jacobian = np.stack([
        port.likelihood.contrasts
        @ (centered * (port.likelihood.receiver_indices == receiver_index))
        * port.likelihood.drift_scale
        for receiver_index in (0, 1)
    ], axis=1)
    jacobians[:, :, 3:5] = drift_jacobian[None, :, :]
    jacobians[:, :, 5] = jacobians[:, :, 2]
    columns = np.column_stack((
        np.broadcast_to(np.arange(5, dtype=np.int64), (selected.size, 5)),
        5 + selected,
    ))
    return {
        "indices": selected.copy(),
        "means": np.asarray(base, dtype=np.float64),
        "jacobians": jacobians,
        "columns": columns,
        "covariance": np.asarray(port.likelihood.covariance, dtype=np.float64),
        "eligible": np.asarray(eligible, dtype=np.bool_),
    }
