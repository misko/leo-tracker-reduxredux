"""Apply Doppler innovations with a compiled recurrence and no matrix factorization."""

import ctypes

import numpy as np

from .innovation_noise import InnovationFilter


def kernel(path):
    function = ctypes.CDLL(str(path)).leo_filter_innovations
    pointer, stride = ctypes.c_void_p, ctypes.c_ssize_t
    function.argtypes = [
        ctypes.c_size_t,
        ctypes.c_size_t,
        pointer,
        stride,
        stride,
        pointer,
        stride,
        stride,
        pointer,
        pointer,
        pointer,
    ]
    function.restype = None
    return function


class CompiledFilter(InnovationFilter):
    def __init__(self, times, white_sd, correlated_sd, correlation_time, *, run):
        self.run = run
        super().__init__(times, white_sd, correlated_sd, correlation_time)

    def apply(self, values):
        values = np.asarray(values, dtype=np.float64)
        if values.ndim not in (1, 2) or values.shape[0] != len(self.innovation_sd):
            raise ValueError("invalid time axis for innovations")
        if not hasattr(self, "inverse_sd"):
            self.inverse_sd = 1 / self.innovation_sd
        matrix = values[:, None] if values.ndim == 1 else values
        out = np.empty_like(matrix, order="F" if matrix.flags.f_contiguous else "C")
        step = matrix.itemsize
        if any(s % step for s in matrix.strides) or not matrix.flags.aligned:
            matrix = np.require(matrix, requirements=["C", "A"])
        self.run(
            *matrix.shape,
            matrix.ctypes.data,
            matrix.strides[0] // step,
            matrix.strides[1] // step,
            out.ctypes.data,
            out.strides[0] // step,
            out.strides[1] // step,
            self.decay.ctypes.data,
            self.inverse_sd.ctypes.data,
            self.bands[1].ctypes.data,
        )
        return out[:, 0] if values.ndim == 1 else out

    @property
    def nbytes(self):
        return super().nbytes + self.inverse_sd.nbytes
