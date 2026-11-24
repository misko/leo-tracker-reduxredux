"""Guarded, per-probe compact time cache for the released projection arithmetic."""

from ctypes import CDLL, c_double, c_int, c_size_t, c_void_p

import numpy as np


def projection_order(times, endpoints, batches):
    """Assign each actual time to the first stage which needs it."""
    starts = np.asarray(endpoints, dtype=np.int64).ravel()
    requested = [starts, *(np.asarray(group, dtype=np.int64).ravel() for group in batches)]
    if any((group < 0).any() or (group >= times).any() for group in requested):
        raise ValueError("Lazy column lies outside the original prepared grid")
    # Return first occurrence of each time in a fixed chronological order
    # within each score batch, then keep that compact ordering for all probes.
    path = np.concatenate([np.unique(group) for group in requested])
    first = np.unique(path, return_index=True)[1]
    order = np.ascontiguousarray(path[np.sort(first)])
    mapped = np.full(times, -1, dtype=np.int64)
    mapped[order] = np.arange(len(order))
    return order, mapped


class LazyProjector:
    def __init__(self, library, grid, endpoints, batches):
        base = grid.geometry
        vectors = base.position_km, base.velocity_km_s, grid.position_derivative, grid.velocity_derivative
        additive = (base.position_norm_squared, base.position_dot_velocity,
                    grid.numerator_derivative, grid.position_dot_derivative)
        shape = additive[0].shape
        if (len(shape) != 2 or any(a.shape != (*shape, 3) for a in vectors)
                or any(a.shape != shape for a in additive)
                or any(type(a) is not np.ndarray or a.dtype != np.float64 or not a.flags.c_contiguous or not a.flags.aligned
                       for a in (*vectors, *additive))):
            raise ValueError("Expected the released projection arrays")
        self.orbits, self.times = shape
        self.columns, self.map = projection_order(self.times, endpoints, batches)
        if not self.columns.size:
            raise ValueError("The receiver has no supported projection column")
        self.library = CDLL(str(library))
        self.call = self.library.regional_lazy_projection
        self.call.argtypes = [c_size_t] * 5 + [c_void_p] * 10 + [c_double, c_void_p, c_double, c_double] + [c_void_p] * 3
        self.call.restype = c_int
        self.inputs = tuple(a.ctypes.data for a in (*vectors, *additive))
        self.data = (*vectors, *additive)
        output = self.orbits, len(self.columns)
        self.output = np.empty(output), np.empty(output, dtype=np.int8), np.empty(output)
        self.pointers = tuple(a.ctypes.data for a in self.output)
        self.ready = 0

    def begin(self, latitude, longitude):
        from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("The projection point lies outside the geographic domain")
        origin = geodetic_to_ecef_km(latitude, longitude, 0.)
        up = ecef_to_enu_matrix(latitude, longitude)[2]
        self.point = origin, float(origin @ origin), up, float(origin @ up)
        self.ready = 0
        return self.output

    def ensure(self, end):
        if not 0 <= end <= len(self.columns):
            raise ValueError("Impossible compact time extent")
        if end <= self.ready:
            return 0
        origin, squared, up, vertical = self.point
        status = self.call(self.orbits, self.times, len(self.columns), self.ready, end,
                           self.columns.ctypes.data, *self.inputs, origin.ctypes.data, squared,
                           up.ctypes.data, vertical, 11.5e9, *self.pointers)
        if status:
            raise ValueError("A partial projection left the released finite domain")
        computed = (end-self.ready) * self.orbits
        self.ready = end
        return computed
