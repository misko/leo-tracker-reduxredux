"""Choose a full-GLRT extra epoch from either representative half of a visit."""

import numpy as np

from . import differential_pilot as differential


def representative_peaks(first, second):
    """Compare each half's tallest timing peak relative to its absolute background."""
    candidates = []
    for index, scores in enumerate((first, second)):
        peak = differential.ranked_centers(scores, capacity=1)
        if not peak:
            continue
        epoch = peak[0]
        background = max(float(np.percentile(abs(scores), 95)), np.finfo(float).tiny)
        candidates.append((float(scores[epoch]) / background, -index, epoch))
    return (None, None) if not candidates else (max(candidates)[2], -max(candidates)[1])


class RepresentativeTime:
    def __init__(self, fftw):
        self.fftw = fftw
        self.scratch = np.zeros((differential.SAMPLES, 2, 2), dtype="<i2")

    def __call__(self, samples):
        if samples.shape != self.scratch.shape or samples.dtype != self.scratch.dtype:
            raise ValueError("expected a dual-RX 20 ms CI16 short window")
        half = len(samples) // 2
        self.scratch[:half] = samples[:half]
        self.scratch[half:] = 0
        first = self.fftw.surface(self.scratch)
        self.scratch[:half] = 0
        self.scratch[half:] = samples[half:]
        second = self.fftw.surface(self.scratch)
        selection = [representative_peaks(a, b) for a, b in zip(first, second, strict=True)]
        return tuple(v[0] for v in selection), tuple(v[1] for v in selection)
