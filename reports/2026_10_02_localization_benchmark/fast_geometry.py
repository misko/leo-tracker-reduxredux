"""Preinterpolated zero-shift Doppler geometry for repeated position queries."""

from __future__ import annotations

import numpy as np
from bundle import _COMMON

LIGHT_SPEED_KM_S = 299_792.458
CANDIDATE_COUNT = 64


def usable(data) -> bool:
    """Return whether ``data`` supports the fixed 64-candidate zero-shift path."""
    try:
        times = np.asarray(data.times)
        rf = np.asarray(data.rf)
        nodes = np.asarray(data.nodes)
        position = np.asarray(data.position)
        velocity = np.asarray(data.velocity)
        numbers = np.asarray(data.numbers)
    except (AttributeError, TypeError, ValueError):
        return False
    return bool(
        times.ndim == 1
        and len(times) > 0
        and rf.shape == times.shape
        and nodes.ndim == 1
        and len(nodes) >= 2
        and numbers.shape == (CANDIDATE_COUNT,)
        and position.shape == (CANDIDATE_COUNT, len(nodes), 3)
        and velocity.shape == position.shape
        and np.all(np.isfinite(times))
        and np.all(np.isfinite(rf))
        and np.all(np.isfinite(nodes))
        and np.all(np.diff(nodes) > 0)
        and np.allclose(np.diff(nodes), nodes[1] - nodes[0], rtol=0.0, atol=1e-12)
        and np.all(times >= nodes[0])
        and np.all(times < nodes[-1])
    )


class ZeroShiftGeometry:
    """Cache orbit states at observation times for zero-RX, zero-tau predictions."""

    usable = staticmethod(usable)

    def __init__(self, data):
        if not usable(data):
            raise ValueError("data is incompatible with zero-shift geometry")
        self.times = np.asarray(data.times, dtype=np.float64)
        self.rf = np.asarray(data.rf, dtype=np.float64)
        nodes = np.asarray(data.nodes, dtype=np.float64)
        fraction = (self.times - nodes[0]) / (nodes[1] - nodes[0])
        lower = np.floor(fraction).astype(int)
        weight = fraction - lower
        shape = (len(self.times), CANDIDATE_COUNT, 3)
        self.position = np.empty(shape, dtype=np.float64)
        self.velocity = np.empty(shape, dtype=np.float64)
        for satellite in range(CANDIDATE_COUNT):
            interpolation_weight = weight[:, None]
            self.position[:, satellite] = (
                data.position[satellite, lower] * (1.0 - interpolation_weight)
                + data.position[satellite, lower + 1] * interpolation_weight
            )
            self.velocity[:, satellite] = (
                data.velocity[satellite, lower] * (1.0 - interpolation_weight)
                + data.velocity[satellite, lower + 1] * interpolation_weight
            )
        self.preinterpolation_count = 1

    def predict(self, point2) -> tuple[np.ndarray, np.ndarray]:
        """Return zero-offset, zero-shift Doppler Hz and visibility for one EN point."""
        point = np.asarray(point2, dtype=np.float64)
        if point.shape != (2,) or not np.all(np.isfinite(point)):
            raise ValueError("point2 must contain two finite east/north coordinates")
        latitude, longitude = _COMMON.coordinates(point)
        receiver = _COMMON.ecef(latitude, longitude)
        delta = self.position - receiver
        direction = delta / np.linalg.norm(delta, axis=-1)[..., None]
        prediction = (
            -self.rf[:, None]
            * np.sum(direction * self.velocity, axis=-1)
            / LIGHT_SPEED_KM_S
        )
        latitude_rad, longitude_rad = np.deg2rad([latitude, longitude])
        up = np.array(
            [
                np.cos(latitude_rad) * np.cos(longitude_rad),
                np.cos(latitude_rad) * np.sin(longitude_rad),
                np.sin(latitude_rad),
            ]
        )
        visible = np.sum(direction * up, axis=-1) >= 0
        return prediction, visible


__all__ = ["ZeroShiftGeometry", "usable"]
