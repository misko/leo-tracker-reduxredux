"""Memoize exact returned residuals within one frozen optimizer closure."""

from collections import OrderedDict
from time import process_time_ns

import numpy as np


class ResidualMemo:
    def __init__(self, residual, capacity=8):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("Residual memo requires a positive fixed capacity")
        self.residual = residual
        self.capacity = capacity
        self.cache = OrderedDict()
        self.hits = self.misses = self.evictions = self.peak_bytes = self.exact_cpu_ns = 0
        self.bytes = 0

    def __call__(self, point):
        coordinates = np.asarray(point)
        if coordinates.shape != (2,) or coordinates.dtype != np.dtype(np.float64):
            return self.residual(point)
        key = coordinates.tobytes()
        cached = self.cache.get(key)
        if cached is not None:
            self.hits += 1
            self.cache.move_to_end(key)
            return cached.copy()
        start = process_time_ns()
        value = self.residual(point)
        self.exact_cpu_ns += process_time_ns()-start
        self.misses += 1
        if len(self.cache) == self.capacity:
            self.bytes -= self.cache.popitem(last=False)[1].nbytes
            self.evictions += 1
        frozen = value.copy()
        frozen.flags.writeable = False
        self.cache[key] = frozen
        self.bytes += frozen.nbytes
        self.peak_bytes = max(self.peak_bytes, self.bytes)
        return value

    def receipt(self):
        return dict(capacity=self.capacity, hits=self.hits, misses=self.misses, evictions=self.evictions,
                    peak_residual_bytes=self.peak_bytes, exact_cpu_ns=self.exact_cpu_ns)
