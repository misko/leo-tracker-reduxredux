"""Interpolated orbit Doppler and its absolute-timing derivative, without IO."""

import numpy as np

from leo.analysis.t1_at import top_candidates
from leo.contracts.t1_at_prediction import T1AtDiscoveryData


class T1AtPredictor:
    def __init__(self, data: T1AtDiscoveryData):
        self.data = data
        winners = {c.candidate_id: c for c in top_candidates(data.manifest.evidence.candidates)}
        ids = np.asarray(data.candidate_ids)
        if (
            ids.dtype.kind not in "iu"
            or ids.ndim != 1
            or len(set(map(int, ids))) != len(ids)
            or set(map(int, ids)) != set(winners)
        ):
            raise ValueError("prediction rows must exactly cover top refined candidates")
        self.candidates = tuple(winners[int(i)] for i in ids)
        self.times = np.array([c.receive_time_s for c in self.candidates])
        n = len(ids)
        s = len(data.numbers)
        k = len(data.nodes_s)
        shapes = {
            "numbers": (s,),
            "nodes_s": (k,),
            "position_km": (s, k, 3),
            "velocity_km_s": (s, k, 3),
            "rf_hz": (n,),
            "observer_km": (2, n, 3),
            "up": (2, n, 3),
            "calibration_hz": (2, n),
        }
        for name, shape in shapes.items():
            array = np.asarray(getattr(data, name))
            if array.shape != shape or not np.all(np.isfinite(array)):
                raise ValueError(f"invalid orbit bank {name}")
        if (
            data.numbers.dtype.kind not in "iu"
            or not n
            or not s
            or k < 2
            or len(set(map(int, data.numbers))) != s
            or np.any(data.numbers <= 0)
        ):
            raise ValueError("orbit bank needs observations, unique catalogue IDs and nodes")
        self.spacing = float(data.nodes_s[1] - data.nodes_s[0])
        if self.spacing <= 0 or not np.allclose(
            np.diff(data.nodes_s), self.spacing, atol=1e-12, rtol=0
        ):
            raise ValueError("orbit nodes must be uniformly increasing")
        if self.times.min() - 20 < data.nodes_s[0] or self.times.max() + 20 >= data.nodes_s[-1]:
            raise ValueError("orbit bank must cover the full +/-20 second search")
        if np.any(data.rf_hz <= 0) or not np.allclose(
            np.linalg.norm(data.up, axis=-1), 1, atol=1e-10
        ):
            raise ValueError("RF/up calibration geometry is invalid")

    def __call__(self, arm, indices, offset):
        if arm not in ("fitted-c", "zero-c") or not np.isfinite(offset) or abs(offset) > 20:
            raise ValueError("unknown RF arm or invalid absolute timing")
        indices = np.asarray(indices, int)
        if indices.ndim != 1 or np.any(indices < 0) or np.any(indices >= len(self.data.numbers)):
            raise ValueError("orbit index outside bank")
        a = 0 if arm == "fitted-c" else 1
        data = self.data
        query = self.times + offset
        fractional = (query - data.nodes_s[0]) / self.spacing
        lower = np.floor(fractional).astype(int)
        weight = (fractional - lower)[:, None, None]
        satellite = indices[None, :]
        node = lower[:, None]
        p0, p1 = data.position_km[satellite, node], data.position_km[satellite, node + 1]
        v0, v1 = data.velocity_km_s[satellite, node], data.velocity_km_s[satellite, node + 1]
        position = p0 * (1 - weight) + p1 * weight
        velocity = v0 * (1 - weight) + v1 * weight
        p_rate = (p1 - p0) / self.spacing
        v_rate = (v1 - v0) / self.spacing
        delta = position - data.observer_km[a, :, None, :]
        distance = np.linalg.norm(delta, axis=-1)
        if np.any(distance <= 0):
            raise ValueError("observer intersects orbit state")
        direction = delta / distance[:, :, None]
        radial = np.sum(direction * velocity, axis=-1)
        prediction = -data.rf_hz[:, None] * radial / 299792.458 + data.calibration_hz[a, :, None]
        visible = np.sum(direction * data.up[a, :, None, :], axis=-1) >= 0
        d_rate = (p_rate - direction * np.sum(direction * p_rate, axis=-1)[:, :, None]) / distance[
            :, :, None
        ]
        radial_rate = np.sum(d_rate * velocity, axis=-1) + np.sum(direction * v_rate, axis=-1)
        return prediction, visible, -data.rf_hz[:, None] * radial_rate / 299792.458
