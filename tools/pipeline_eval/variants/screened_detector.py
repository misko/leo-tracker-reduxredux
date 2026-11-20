"""Optional bounded reuse of exact 16-tap fractional GLRT interpolation weights."""

from contextlib import contextmanager
from functools import lru_cache
from unittest.mock import patch

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

HALF_WIDTH = 8
MAX_LOCATIONS = 4096
MAX_PHASES = 8


class FractionalRows:
    def __init__(self, original):
        self.original = original
        self.calls = 0
        self.samples = 0
        self.uniform_calls = 0
        self.weight_rows = 0
        self.fallback_calls = 0
        self.weights = lru_cache(maxsize=512)(self._weights)
        self.offsets = np.arange(1 - HALF_WIDTH, HALF_WIDTH + 1)

    def _weights(self, phase):
        self.weight_rows += 1
        distance = phase - self.offsets
        weights = np.sinc(distance) * np.sinc(distance / HALF_WIDTH)
        return weights / np.sum(weights)

    def __call__(self, samples, positions, *, half_width=HALF_WIDTH):
        self.calls += 1
        values = np.asarray(samples)
        locations = np.asarray(positions, dtype=float)
        if (
            type(half_width) is not int
            or half_width != HALF_WIDTH
            or values.ndim != 1
            or values.dtype != np.dtype(np.complex128)
            or not 32 <= locations.size <= MAX_LOCATIONS
            or not np.isfinite(locations).all()
            or locations.min() < HALF_WIDTH - 1
            or locations.max() >= len(values) - HALF_WIDTH
        ):
            self.fallback_calls += 1
            return self.original(samples, positions, half_width=half_width)

        # All retained locations are positive. Their base subtraction is exact
        # (Sterbenz), so fraction - offset rounds exactly as location - index.
        bases = locations.astype(np.intp)
        fractions = locations - bases
        phase = fractions.flat[0]
        if np.all(fractions == phase):
            if phase <= 1e-12 or phase >= 1 - 1e-12:
                self.fallback_calls += 1
                return self.original(samples, positions, half_width=half_width)
            self.uniform_calls += 1
            weights = self.weights(float(phase))
        else:
            if np.all((fractions <= 1e-12) | (fractions >= 1 - 1e-12)):
                self.fallback_calls += 1
                return self.original(samples, positions, half_width=half_width)
            unique, inverse = np.unique(fractions, return_inverse=True)
            if unique.size > MAX_PHASES:
                self.fallback_calls += 1
                return self.original(samples, positions, half_width=half_width)
            table = np.asarray([self.weights(float(item)) for item in unique])
            weights = table[inverse.reshape(locations.shape)]
        self.samples += locations.size
        windows = sliding_window_view(values, 2 * HALF_WIDTH)
        return np.sum(windows[bases - (HALF_WIDTH - 1)] * weights, axis=-1)

    def receipts(self):
        return dict(
            calls=self.calls,
            samples=self.samples,
            uniform_calls=self.uniform_calls,
            weight_rows=self.weight_rows,
            fallback_calls=self.fallback_calls,
            cache=self.weights.cache_info()._asdict(),
        )


@contextmanager
def route(scores=None):
    """Use in a dedicated, single-detector process with the installed scorer."""
    if scores is None:
        from leo.analysis.starlink import fast_scan_scores as scores

    sampler = FractionalRows(scores.fractional_take)
    with patch.object(scores, "fractional_take", sampler):
        yield sampler
