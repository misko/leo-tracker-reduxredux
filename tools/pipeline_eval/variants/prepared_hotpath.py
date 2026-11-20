"""Reuse the original capture producer's sparse fine-CFO FFT workspace."""

from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import numpy as np

from .refine_bank import EPOCHS, FRAME_BASE, RATE, SAMPLES, TAPS

SYMBOLS = tuple(range(2, 302, 2))
FIRST, STOP = 2 * TAPS, 301 * TAPS
FFT_SIZE = 20_000
PILOTS = np.arange(FIRST, STOP).reshape(-1, TAPS)[::2].ravel()


class FineWorkspace:
    """One producer worker owns its received aperture and FFT input/output buffers."""

    def __init__(self, acquisition):
        self.acquisition = acquisition
        self.original = acquisition._normalized_frame_scores_fft
        self.applied = 0
        self.fallbacks = 0
        self.received = np.empty((len(FRAME_BASE), len(PILOTS)), dtype=np.complex128)
        self.scratch = np.zeros((len(FRAME_BASE), FFT_SIZE), dtype=np.complex128)
        self.spectrum = np.empty_like(self.scratch)

    @property
    def workspace_bytes(self):
        return self.received.nbytes + self.scratch.nbytes + self.spectrum.nbytes

    def score(self, values, template, rate, epoch, frequencies, symbols, *, transform_size):
        if not (
            rate == RATE
            and transform_size == FFT_SIZE
            and symbols == SYMBOLS
            and values.shape == (SAMPLES,)
            and template.shape == (EPOCHS,)
            and values.dtype == template.dtype == np.complex128
            and 0 <= epoch < EPOCHS
            and 2 <= len(frequencies) <= FFT_SIZE
            and self.acquisition._constant_grid_step(frequencies) == RATE / FFT_SIZE
            and np.isfinite(frequencies[0])
        ):
            self.fallbacks += 1
            return self.original(
                values,
                template,
                rate,
                epoch,
                frequencies,
                symbols,
                transform_size=transform_size,
            )

        starts = epoch + FRAME_BASE
        frames = int(np.searchsorted(starts, SAMPLES - STOP, side="right"))
        received = self.received[:frames]
        sample_blocks = received.reshape(frames, len(SYMBOLS), TAPS)
        for row, start in zip(sample_blocks, starts[:frames], strict=True):
            row[:] = values[start + FIRST : start + STOP].reshape(-1, TAPS)[::2]

        references = template[PILOTS]
        energy = float(np.vdot(references, references).real)
        denominator = np.sqrt(energy * np.sum(np.abs(received) ** 2, axis=1))
        base_rotation = np.exp(-2j * np.pi * frequencies[0] * PILOTS / rate)
        scratch = self.scratch[:frames]
        # All samples outside these symbol views remain zero across calls.
        occupied = scratch[:, FIRST:STOP].reshape(frames, -1, TAPS)[:, ::2, :]
        np.multiply(received, np.conj(references)[None, :], out=received)
        np.multiply(sample_blocks, base_rotation.reshape(-1, TAPS), out=occupied)
        spectrum = np.fft.fft(scratch, axis=1, out=self.spectrum[:frames])
        selected = spectrum[:, : len(frequencies)].T
        normalized = np.divide(
            np.abs(selected),
            denominator[None, :],
            out=np.zeros_like(selected.real),
            where=denominator[None, :] > 0,
        )
        self.applied += 1
        return tuple(float(value) for value in np.mean(normalized, axis=1))

    @contextmanager
    def route(self, *, selector=None):
        with ExitStack() as scope:
            scope.enter_context(
                patch.object(self.acquisition, "_normalized_frame_scores_fft", self.score)
            )
            if selector is not None:
                scope.enter_context(
                    patch.object(self.acquisition, "_retain_score_map_peaks", selector)
                )
            yield self
