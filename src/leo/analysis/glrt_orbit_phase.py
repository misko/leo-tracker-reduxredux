"""Pure fixed-position orbital port with a shared ephemeris-time nuisance."""

import numpy as np

from leo.analysis.wrapped_glrt_likelihood import smooth_visibility
from leo.sky.frames import EARTH_ROTATION_RATE_RAD_S, ecef_to_enu_matrix, geodetic_to_ecef_km


class OrbitPhasePort:
    def __init__(
        self,
        positions,
        velocities,
        nodes_s,
        times_s,
        rf_hz,
        latitude_deg,
        longitude_deg,
        altitude_m,
        *,
        inertial_phase=False,
    ):
        self.position = np.asarray(positions, float)
        self.velocity = np.asarray(velocities, float)
        self.nodes = np.asarray(nodes_s, float)
        self.times = np.asarray(times_s, float)
        self.rf = np.asarray(rf_hz, float)
        if (
            self.position.ndim != 3
            or self.position.shape[-1] != 3
            or self.velocity.shape != self.position.shape
            or self.nodes.shape != (self.position.shape[1],)
            or len(self.nodes) < 3
            or self.times.ndim != 1
            or self.rf.shape != self.times.shape
            or not np.allclose(np.diff(self.nodes), self.nodes[1] - self.nodes[0])
            or self.nodes[1] <= self.nodes[0]
            or any(
                not np.isfinite(x).all()
                for x in (self.position, self.velocity, self.nodes, self.times, self.rf)
            )
        ):
            raise ValueError("finite regular orbital bank required")
        self.receiver = geodetic_to_ecef_km(latitude_deg, longitude_deg, altitude_m)
        self.up = ecef_to_enu_matrix(latitude_deg, longitude_deg)[2]
        self.inertial_phase = bool(inertial_phase)

    def predict(self, phase_s, indices=None):
        selected = np.arange(len(self.position)) if indices is None else np.asarray(indices, int)
        phase = np.asarray(phase_s, float)
        if phase.ndim > 1 or (phase.ndim == 1 and phase.shape != selected.shape):
            raise ValueError("one finite phase per selected satellite required")
        if not np.isfinite(phase).all():
            raise ValueError("one finite phase per selected satellite required")
        query = self.times[None, :] + np.broadcast_to(phase, selected.shape)[:, None]
        if query.min() < self.nodes[0] or query.max() > self.nodes[-1]:
            raise ValueError("ephemeris query outside recorded phase support")
        step = self.nodes[1] - self.nodes[0]
        fractional = (query - self.nodes[0]) / step
        lower = np.minimum(np.floor(fractional).astype(int), len(self.nodes) - 2)
        weight = (fractional - lower)[:, :, None]
        p0 = self.position[selected[:, None], lower]
        p1 = self.position[selected[:, None], lower + 1]
        v0 = self.velocity[selected[:, None], lower]
        v1 = self.velocity[selected[:, None], lower + 1]
        p = p0 + weight * (p1 - p0)
        v = v0 + weight * (v1 - v0)
        pos_rate = (p1 - p0) / step
        acceleration = (v1 - v0) / step
        if self.inertial_phase:
            # Shift orbital phase while holding reception-time Earth rotation
            # fixed. The queried ECEF states already include the extra rotation.
            angle = EARTH_ROTATION_RATE_RAD_S * np.broadcast_to(phase, selected.shape)
            cosine, sine = np.cos(angle)[:, None], np.sin(angle)[:, None]

            def rotate(value):
                return np.stack(
                    (
                        cosine * value[..., 0] - sine * value[..., 1],
                        sine * value[..., 0] + cosine * value[..., 1],
                        value[..., 2],
                    ),
                    axis=-1,
                )

            p, v = rotate(p), rotate(v)
            pos_rate = rotate(pos_rate) + EARTH_ROTATION_RATE_RAD_S * np.cross([0.0, 0.0, 1.0], p)
            acceleration = rotate(acceleration) + EARTH_ROTATION_RATE_RAD_S * np.cross(
                [0.0, 0.0, 1.0], v
            )
        delta = p - self.receiver
        distance = np.linalg.norm(delta, axis=-1)
        direction = delta / distance[:, :, None]
        rate = np.sum(direction * v, axis=-1)
        direction_rate = (
            pos_rate - direction * np.sum(direction * pos_rate, axis=-1)[:, :, None]
        ) / distance[:, :, None]
        range_acc = np.sum(direction_rate * v + direction * acceleration, axis=-1)
        factor = self.rf[None, :] / 299792.458
        prediction = (-factor * rate).T
        derivative = (-factor * range_acc).T
        sine = np.clip(direction @ self.up, -1, 1)
        elevation = np.rad2deg(np.arcsin(sine))
        opportunity = smooth_visibility(elevation).T
        x = np.clip(elevation / 5, 0, 1)
        elevation_rate = np.rad2deg(direction_rate @ self.up) / np.sqrt(
            np.maximum(1e-12, 1 - sine * sine)
        )
        opportunity_rate = (6 * x * (1 - x) * elevation_rate / 5).T
        return prediction, opportunity, derivative, opportunity_rate
