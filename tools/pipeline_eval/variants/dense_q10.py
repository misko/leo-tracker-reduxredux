"""Use bounded Q10 sliding-tone sums and the original exact contender repair."""

import ctypes
import subprocess
from pathlib import Path
from time import process_time

import numpy as np

from .anchor_receiver import FLAGS
from .spectral_grid import SpectralGrid, _gamma

SOURCE = Path(__file__).with_suffix(".c")
SCALE = 1024


def compile_grid(library):
    subprocess.run(["cc", *FLAGS, "-mavx2", str(SOURCE), "-lm", "-o", str(library)], check=True)


def rounding_bound(aperture, max_inverse_iq, max_inverse_template):
    """Bound the extra score error from modulation, integer rounding and rephasing."""
    arithmetic = _gamma(20, np.float32)
    norm = 1 + _gamma(3, np.float32)
    quantization = np.sqrt(2) * aperture * max_inverse_iq / SCALE
    return float(
        8
        * norm
        * max_inverse_template
        * (arithmetic * np.sqrt(aperture) + (1 + arithmetic) * quantization)
    )


class DenseQ10Grid(SpectralGrid):
    def __init__(self, library, control):
        super().__init__(library, control)
        dll = ctypes.CDLL(str(Path(library).resolve()))
        f, i, d, b = (
            np.ctypeslib.ndpointer(dtype=t, flags="C_CONTIGUOUS")
            for t in (np.float32, np.int32, np.float64, np.uint8)
        )
        n = ctypes.c_int
        self._dense = dll.score_dense_q10
        self._dense.argtypes = [f, f, n, n, f, f, i, n, b, f, f, i, n, f, n, f, d]
        self._dense.restype = None
        self._score = self._quantized_row
        self._max_inverse_template = None

    def _quantized_row(self, real, imag, valid, aperture, weights, phase, *args):
        if self._max_inverse_template is None:
            self._max_inverse_template = float(np.max(args[4]))
        quantized_weights = weights.astype(np.float32)
        quantized_weights *= SCALE
        quantized_phase = phase.astype(np.float32)
        quantized_phase /= SCALE
        self._dense(real, imag, valid, aperture, quantized_weights, quantized_phase, *args)

    def score_grid(self, *args):
        self._max_inverse_template = None
        rows = super().score_grid(*args)
        start = process_time()
        _, grid = self._pending
        if grid is not None:
            extra = rounding_bound(
                grid.aperture, grid.inverse_iq_norm.max(), self._max_inverse_template
            )
            grid.error_bound += extra
            scratch = 8 * 2 * (128 + grid.aperture - 1 + 128) * np.dtype(np.float32).itemsize
            grid.timing.update(
                error_bound=grid.error_bound,
                quantized_extra_bound=extra,
                quantized_coefficients_bytes=scratch,
                quantized_integer_prefix_bytes=2 * (128 + 44) * np.dtype(np.uint32).itemsize,
                coarse_cpu_s=grid.timing["coarse_cpu_s"] + process_time() - start,
            )
        return rows
