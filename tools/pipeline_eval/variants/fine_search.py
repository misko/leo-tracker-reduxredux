"""Prune unused fine-CFO bins while preserving capture-era binary64 arithmetic."""

import ctypes
import os
import subprocess
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch

import numpy as np

from .prepared_hotpath import FFT_SIZE, FIRST, PILOTS, STOP, SYMBOLS
from .refine_bank import EPOCHS, FRAME_BASE, RATE, SAMPLES, TAPS

SOURCE = Path(__file__).with_suffix(".c")
MAX_BINS = 321
FLAGS = (
    "-std=c11",
    "-O3",
    "-march=native",
    "-fopenmp-simd",
    "-ffp-contract=off",
    "-shared",
    "-fPIC",
)


def build(work):
    library = work / "fine_search.so"
    command = ["cc", *FLAGS, str(SOURCE), "-lm", "-o", str(library)]
    subprocess.run(command, env=os.environ | {"TMPDIR": str(work)}, check=True)
    return library, command


@lru_cache(maxsize=64)
def _rotation(first):
    return np.exp(-2j * np.pi * first * PILOTS / RATE)


class FineSearch:
    """One capture worker's checked prefix transform and private scratch arrays."""

    def __init__(self, library, acquisition):
        self.acquisition = acquisition
        self.original = acquisition._normalized_frame_scores_fft
        dll = ctypes.CDLL(str(library))
        vector = np.ctypeslib.ndpointer(dtype=np.complex128, flags="C_CONTIGUOUS")
        initialize = dll.fine_search_twiddles
        initialize.argtypes = (vector,)
        initialize.restype = None
        self.transform = dll.fine_search_transform
        self.transform.argtypes = (vector, vector, vector, vector, ctypes.c_int, ctypes.c_int)
        self.transform.restype = None
        self.roots = np.empty(FFT_SIZE, dtype=np.complex128)
        initialize(self.roots)
        self.work = np.zeros(2 * FFT_SIZE, dtype=np.complex128)
        self.output = np.empty((len(FRAME_BASE), MAX_BINS), dtype=np.complex128)
        self.frames = self.bins = self.calls = self.fallbacks = 0
        self.compatible = self._matches_runtime()

    @property
    def workspace_bytes(self):
        return self.roots.nbytes + self.work.nbytes + self.output.nbytes

    def _matches_runtime(self):
        rng = np.random.default_rng(499157)
        shape = (len(FRAME_BASE), len(PILOTS))
        weighted = rng.standard_normal(shape) + 1j * rng.standard_normal(shape)
        scratch = np.zeros((len(weighted), FFT_SIZE), dtype=np.complex128)
        scratch[:, PILOTS] = weighted
        full = np.fft.fft(scratch, axis=1)
        return all(
            np.array_equal(full[:frames, :bins], self._selected(weighted[:frames], bins))
            for frames, bins in ((15, MAX_BINS), (14, 161), (14, 2))
        )

    def _selected(self, weighted, bins):
        frames = len(weighted)
        selected = self.output.ravel()[: frames * bins].reshape(frames, bins)
        self.transform(weighted, self.roots, self.work, selected, frames, bins)
        return selected

    def score(self, values, template, rate, epoch, frequencies, symbols, *, transform_size):
        if not (
            self.compatible
            and rate == RATE
            and transform_size == FFT_SIZE
            and symbols == SYMBOLS
            and values.shape == (SAMPLES,)
            and template.shape == (EPOCHS,)
            and values.dtype == template.dtype == np.complex128
            and 0 <= epoch < EPOCHS
            and 2 <= len(frequencies) <= MAX_BINS
            and self.acquisition._constant_grid_step(frequencies) == RATE / FFT_SIZE
            and np.isfinite(frequencies[0])
        ):
            self.fallbacks += 1
            return self.original(
                values, template, rate, epoch, frequencies, symbols, transform_size=transform_size
            )

        starts = epoch + FRAME_BASE
        frames = int(np.searchsorted(starts, SAMPLES - STOP, side="right"))
        received = np.stack(
            [
                values[start + FIRST : start + STOP].reshape(-1, TAPS)[::2].ravel()
                for start in starts[:frames]
            ]
        )
        references = template[PILOTS]
        energy = float(np.vdot(references, references).real)
        denominator = np.sqrt(energy * np.sum(np.abs(received) ** 2, axis=1))
        weighted = (received * np.conj(references)[None, :]) * _rotation(frequencies[0])
        selected = self._selected(weighted, len(frequencies)).T
        normalized = np.divide(
            np.abs(selected),
            denominator[None, :],
            out=np.zeros_like(selected.real),
            where=denominator[None, :] > 0,
        )
        self.calls += 1
        self.frames += frames
        self.bins += frames * len(frequencies)
        return tuple(float(value) for value in np.mean(normalized, axis=1))

    @contextmanager
    def route(self):
        with patch.object(self.acquisition, "_normalized_frame_scores_fft", self.score):
            yield self
