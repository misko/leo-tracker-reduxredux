"""Offer the portable C scorer to the guarded original host detector experiment."""

import ctypes as c
from contextlib import contextmanager
from unittest.mock import patch

import numpy as np

from .fine_search import MAX_BINS
from .prepared_hotpath import FFT_SIZE, PILOTS, SYMBOLS
from .refine_bank import EPOCHS, RATE, SAMPLES

WORKSPACE_DOUBLES = 2 * (3 * FFT_SIZE + 2 * len(PILOTS) + MAX_BINS) + 1


class Peak(c.Structure):
    _fields_ = [
        ("winner", c.c_uint),
        ("runner", c.c_uint),
        ("guard", c.c_uint),
        ("frames", c.c_uint),
        ("interpolated_hz", c.c_double),
        ("gap", c.c_double),
        ("curvature", c.c_double),
    ]


class PortableFine:
    def __init__(self, path, acquisition, fallback):
        native = c.CDLL(str(path))
        self.acquisition, self.fallback = acquisition, fallback
        self.calls = self.guarded = self.unsupported = 0
        raw_pointer = c.POINTER(c.c_double)
        complex_samples = np.ctypeslib.ndpointer(dtype=np.complex128, flags="C_CONTIGUOUS")
        self.workspace = (c.c_double * WORKSPACE_DOUBLES)()
        self.scores = (c.c_double * MAX_BINS)()
        native.portable_fine_prepare.argtypes = (raw_pointer,)
        native.portable_fine_prepare.restype = None
        native.portable_fine_prepare(self.workspace)
        self.native_score = native.portable_fine_score
        self.native_score.argtypes = (
            raw_pointer,
            complex_samples,
            complex_samples,
            c.c_uint,
            c.c_double,
            c.c_uint,
            raw_pointer,
            c.POINTER(c.c_uint),
        )
        self.native_score.restype = c.c_int
        self.native_peak = native.portable_fine_peak
        self.native_peak.argtypes = (raw_pointer, c.c_double, c.c_uint, c.POINTER(Peak))
        self.native_peak.restype = c.c_int

    def score(self, values, template, rate, epoch, frequencies, symbols, *, transform_size):
        bins = len(frequencies)
        supported = (
            rate == RATE
            and transform_size == FFT_SIZE
            and symbols == SYMBOLS
            and values.shape == (SAMPLES,)
            and template.shape == (EPOCHS,)
            and values.dtype == template.dtype == np.complex128
            and values.flags.c_contiguous
            and template.flags.c_contiguous
            and 0 <= epoch < EPOCHS
            and 2 <= bins <= MAX_BINS
            and self.acquisition._constant_grid_step(frequencies) == RATE / FFT_SIZE
        )
        if supported:
            frames = c.c_uint()
            peak = Peak()
            first = frequencies[0]
            supported = (
                self.native_score(
                    self.workspace,
                    values,
                    template,
                    epoch,
                    first,
                    bins,
                    self.scores,
                    c.byref(frames),
                )
                == 0
                and self.native_peak(self.scores, first, bins, c.byref(peak)) == 0
            )
            if supported and not peak.guard:
                # The producer still fits the returned scores on its own residual grid.
                self.calls += 1
                return tuple(self.scores[:bins])
        if supported:
            self.guarded += 1
        else:
            self.unsupported += 1
        return self.fallback(
            values, template, rate, epoch, frequencies, symbols, transform_size=transform_size
        )

    @contextmanager
    def route(self):
        with patch.object(self.acquisition, "_normalized_frame_scores_fft", self.score):
            yield self
