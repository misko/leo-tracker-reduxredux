"""Qualification-only frontend for the independently implemented FFTW scorer."""

import ctypes
from contextlib import AbstractContextManager
from pathlib import Path

import numpy as np

from . import differential_pilot as reference

SOURCE = Path(__file__).with_suffix(".c")


class FftScout(AbstractContextManager):
    def __init__(self, library, edge):
        port = ctypes.CDLL(str(library))
        port.leo_differential_scout_create.argtypes = []
        port.leo_differential_scout_create.restype = ctypes.c_void_p
        self.destroy = port.leo_differential_scout_destroy
        self.destroy.argtypes = [ctypes.c_void_p]
        self.destroy.restype = None
        self.evaluate = port.leo_differential_scout
        self.evaluate.argtypes = [ctypes.c_void_p] * 5
        self.evaluate.restype = None
        references = reference.filters(edge)
        self.filters = np.stack([k for k, _ in references], dtype="<c8")
        self.energy = np.stack([e for _, e in references], dtype="<f8")
        self.edge = edge
        self.native = port.leo_differential_scout_create()
        if not self.native:
            raise MemoryError("could not allocate the differential FFTW scout")

    def surface(self, samples):
        if samples.shape != (reference.SAMPLES, 2, 2) or samples.dtype != np.dtype("<i2"):
            raise ValueError("Expected a dual-receiver 20 ms CI16 window at 10 MS/s")
        if not self.native:
            raise RuntimeError("the differential FFTW scout is closed")
        samples = np.ascontiguousarray(samples)
        out = np.empty((2, reference.FRAME), dtype="<f8")
        self.evaluate(
            self.native,
            samples.ctypes.data,
            self.filters.ctypes.data,
            self.energy.ctypes.data,
            out.ctypes.data,
        )
        return out

    def __call__(self, samples, edge):
        if edge != self.edge:
            raise ValueError("a differential FFTW context is bound to one edge")
        return [
            (centers, [float(row[index]) for index in centers])
            for row in self.surface(samples)
            for centers in [reference.ranked_centers(row)]
        ]

    def __exit__(self, *exc):
        if self.native:
            self.destroy(self.native)
            self.native = None
