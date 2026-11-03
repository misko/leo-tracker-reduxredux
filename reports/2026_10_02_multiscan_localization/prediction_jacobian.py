"""Pure paired orbit prediction and sparse parameter Jacobian."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from joint_inputs import LIGHT_SPEED_KM_S, _coordinates, _ecef


@dataclass(frozen=True)
class PairedPredictionJacobian:
    """Jacobian with dense shared columns and one sparse tau entry per pair."""

    shared: np.ndarray
    tau: np.ndarray
    satellites: np.ndarray
    candidate_count: int

    def to_dense(self) -> np.ndarray:
        output = np.zeros(self.tau.shape + (6 + self.candidate_count,), dtype=float)
        output[..., :6] = self.shared
        flat = output.reshape(-1, output.shape[-1])
        flat[np.arange(len(flat)), 6 + self.satellites.ravel()] = self.tau.ravel()
        return output

    def transpose_multiply(self, weights) -> np.ndarray:
        weights = np.asarray(weights, dtype=float)
        if weights.shape != self.tau.shape:
            raise ValueError("weights must match the paired prediction shape")
        flat_weights = weights.ravel()
        shared_gradient = np.sum(flat_weights[:, None] * self.shared.reshape(-1, 6), axis=0)
        tau_gradient = np.zeros(self.candidate_count, dtype=float)
        np.add.at(
            tau_gradient,
            self.satellites.ravel(),
            flat_weights * self.tau.ravel(),
        )
        return np.concatenate((shared_gradient, tau_gradient))

    def normal_matrix(self, weights) -> np.ndarray:
        weights = np.asarray(weights, dtype=float)
        if weights.shape != self.tau.shape:
            raise ValueError("weights must match the paired prediction shape")
        if np.any(~np.isfinite(weights)) or np.any(weights < 0):
            raise ValueError("precision weights must be finite and nonnegative")
        flat_weights = weights.ravel()
        shared = self.shared.reshape(-1, 6)
        tau = self.tau.ravel()
        satellites = self.satellites.ravel()
        normal = np.zeros((6 + self.candidate_count, 6 + self.candidate_count))
        normal[:6, :6] = shared.T @ (flat_weights[:, None] * shared)
        cross = np.stack(
            [
                np.bincount(
                    satellites,
                    weights=flat_weights * tau * shared[:, column],
                    minlength=self.candidate_count,
                )
                for column in range(6)
            ]
        )
        normal[:6, 6:] = cross
        normal[6:, :6] = cross.T
        indices = 6 + np.arange(self.candidate_count)
        normal[indices, indices] = np.bincount(
            satellites, weights=flat_weights * tau**2, minlength=self.candidate_count
        )
        return normal


def _observer_and_geographic_jacobian(point, step_km):
    point = np.asarray(point, dtype=float)
    latitude, longitude = _coordinates(point)
    observer = _ecef(latitude, longitude)
    derivative = np.empty((3, 2), dtype=float)
    for axis in range(2):
        delta = np.zeros(2)
        delta[axis] = step_km
        plus = _ecef(*_coordinates(point + delta))
        minus = _ecef(*_coordinates(point - delta))
        derivative[:, axis] = (plus - minus) / (2 * step_km)
    return observer, derivative, latitude, longitude


def paired_prediction_jacobian(
    data,
    parameters,
    rows,
    satellites,
    *,
    location_step_km=1e-3,
):
    """Return paired predictions, visibility, and a sparse analytic Jacobian.

    Parameter order is ``[east, north, a0, b0, a1, b1, tau per satellite]``.
    RX slopes use actual receive time relative to ``data.reference_time_s``;
    old single-capture adapters default to 150 seconds.
    """

    candidate_count = len(data.numbers)
    parameters = np.asarray(parameters, dtype=float)
    rows = np.asarray(rows, dtype=int)
    satellites = np.asarray(satellites, dtype=int)
    if parameters.shape != (6 + candidate_count,) or np.any(~np.isfinite(parameters)):
        raise ValueError("parameters do not match the data candidate bank")
    if rows.shape != satellites.shape:
        raise ValueError("paired rows and satellites must have identical shapes")
    if np.any(rows < 0) or np.any(rows >= len(data.times)):
        raise ValueError("row index falls outside observations")
    if np.any(satellites < 0) or np.any(satellites >= candidate_count):
        raise ValueError("satellite index falls outside candidate bank")
    if not np.isfinite(location_step_km) or location_step_km <= 0:
        raise ValueError("location_step_km must be positive and finite")

    nodes = np.asarray(data.nodes, dtype=float)
    spacing = float(nodes[1] - nodes[0])
    if (
        nodes.ndim != 1
        or len(nodes) < 2
        or not np.allclose(np.diff(nodes), spacing, rtol=0.0, atol=1e-12)
    ):
        raise ValueError("ephemeris nodes must be uniformly spaced")
    position_bank = np.asarray(data.position)
    velocity_bank = np.asarray(data.velocity)
    expected_shape = (candidate_count, len(nodes), 3)
    if position_bank.shape != expected_shape or velocity_bank.shape != expected_shape:
        raise ValueError("ephemeris arrays do not match nodes and candidate bank")

    receive_time = np.asarray(data.times)[rows]
    query = receive_time + parameters[6:][satellites]
    if np.any(query < nodes[0]) or np.any(query >= nodes[-1]):
        raise ValueError("shifted orbit time lies outside ephemeris")
    fraction = (query - nodes[0]) / spacing
    lower = np.floor(fraction).astype(int)
    interpolation_weight = (fraction - lower)[..., None]
    lower_position = position_bank[satellites, lower]
    upper_position = position_bank[satellites, lower + 1]
    lower_velocity = velocity_bank[satellites, lower]
    upper_velocity = velocity_bank[satellites, lower + 1]
    position = lower_position * (1 - interpolation_weight) + upper_position * interpolation_weight
    velocity = lower_velocity * (1 - interpolation_weight) + upper_velocity * interpolation_weight
    position_rate = (upper_position - lower_position) / spacing
    velocity_rate = (upper_velocity - lower_velocity) / spacing

    observer, observer_derivative, latitude, longitude = _observer_and_geographic_jacobian(
        parameters[:2], float(location_step_km)
    )
    delta = position - observer
    distance = np.linalg.norm(delta, axis=-1)
    direction = delta / distance[..., None]
    radial_velocity = np.sum(direction * velocity, axis=-1)
    rf = np.asarray(data.rf)[rows]
    orbital = -rf * radial_velocity / LIGHT_SPEED_KM_S

    reference_time = float(getattr(data, "reference_time_s", 150.0))
    receiver = np.asarray(data.receiver)[rows]
    offset = parameters[2 + 2 * receiver] + parameters[3 + 2 * receiver] * (
        receive_time - reference_time
    )
    prediction = orbital + offset

    latitude_rad, longitude_rad = np.deg2rad([latitude, longitude])
    up = np.array(
        [
            np.cos(latitude_rad) * np.cos(longitude_rad),
            np.cos(latitude_rad) * np.sin(longitude_rad),
            np.sin(latitude_rad),
        ]
    )
    visible = np.sum(direction * up, axis=-1) >= 0

    observer_gradient = (
        rf[..., None]
        / LIGHT_SPEED_KM_S
        * (velocity - direction * radial_velocity[..., None])
        / distance[..., None]
    )
    shared = np.zeros(rows.shape + (6,), dtype=float)
    shared[..., :2] = np.einsum("...i,ij->...j", observer_gradient, observer_derivative)
    flat_shared = shared.reshape(-1, 6)
    flat_receiver = receiver.ravel()
    flat_time = receive_time.ravel()
    pair_index = np.arange(len(flat_shared))
    flat_shared[pair_index, 2 + 2 * flat_receiver] = 1.0
    flat_shared[pair_index, 3 + 2 * flat_receiver] = flat_time - reference_time

    projected_position_rate = np.sum(direction * position_rate, axis=-1)
    direction_rate = (position_rate - direction * projected_position_rate[..., None]) / distance[
        ..., None
    ]
    radial_rate = np.sum(direction_rate * velocity, axis=-1) + np.sum(
        direction * velocity_rate, axis=-1
    )
    tau_derivative = -rf * radial_rate / LIGHT_SPEED_KM_S
    jacobian = PairedPredictionJacobian(
        shared=shared,
        tau=tau_derivative,
        satellites=satellites.copy(),
        candidate_count=candidate_count,
    )
    return prediction, visible, jacobian


__all__ = ["PairedPredictionJacobian", "paired_prediction_jacobian"]
