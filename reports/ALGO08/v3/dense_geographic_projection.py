"""Bind the fused contiguous kernel only at the released geographic score port."""

from collections import Counter
from ctypes import CDLL, c_double, c_int, c_size_t, c_void_p
from hashlib import sha256
from pathlib import Path
from time import process_time_ns

import numpy as np

from visible_orbit_proof import PIN, PROJECTOR_PIN


class Projector:
    def __init__(self, path, digest, reference):
        if sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError("Unpinned native geographic projection")
        self.library = CDLL(str(path))
        self.call = self.library.dense_geographic_projection
        self.call.argtypes = [c_size_t] + [c_void_p] * 9 + [c_double, c_void_p, c_double, c_double] + [c_void_p] * 3
        self.call.restype = c_int
        self.reference = reference
        self.counts = Counter()

    def __call__(self, grid, latitude, longitude, *, altitude_m=0., rf_hz=11.5e9):
        if (not (-90 <= latitude <= 90 and -180 <= longitude <= 180)
                or not np.isfinite(altitude_m) or not np.isfinite(rf_hz) or rf_hz <= 0):
            return self.reference(grid, latitude, longitude, altitude_m=altitude_m, rf_hz=rf_hz)
        base = grid.geometry
        vectors = base.position_km, base.velocity_km_s, grid.position_derivative, grid.velocity_derivative
        additive = (base.position_norm_squared, base.position_dot_velocity,
                    grid.numerator_derivative, grid.position_dot_derivative)
        shape = additive[0].shape
        if (len(shape) != 2 or any(a.shape != (*shape, 3) for a in vectors)
                or any(a.shape != shape for a in additive)
                or any(type(a) is not np.ndarray or a.dtype != np.float64 or not a.flags.c_contiguous or not a.flags.aligned
                       for a in (*vectors, *additive))):
            self.counts["original_fallback"] += 1
            return self.reference(grid, latitude, longitude, altitude_m=altitude_m, rf_hz=rf_hz)
        from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

        start = process_time_ns()
        observer = geodetic_to_ecef_km(latitude, longitude, altitude_m)
        up = ecef_to_enu_matrix(latitude, longitude)[2]
        frequency, derivative = np.empty(shape), np.empty(shape)
        horizon = np.empty(shape, dtype=np.int8)
        status = self.call(frequency.size, *(a.ctypes.data for a in (*vectors, *additive)),
                           observer.ctypes.data, observer @ observer, up.ctypes.data, observer @ up, rf_hz,
                           frequency.ctypes.data, horizon.ctypes.data, derivative.ctypes.data)
        self.counts["projection_cpu_ns"] += process_time_ns()-start
        if status:
            self.counts["original_fallback"] += 1
            return self.reference(grid, latitude, longitude, altitude_m=altitude_m, rf_hz=rf_hz)
        self.counts["calls"] += 1
        self.counts["cells"] += frequency.size
        return frequency, horizon, derivative


def checked_runtime():
    from tools.pipeline_eval.variants.experimental import regional_reassignment as kernel

    reference = kernel.phase_linear_frequency
    if (sha256(Path(kernel.__file__).read_bytes()).hexdigest() != PIN
            or sha256(Path(reference.__code__.co_filename).read_bytes()).hexdigest() != PROJECTOR_PIN):
        raise ValueError("Expected the reviewed original regional scorer and projector")
    return kernel, reference
