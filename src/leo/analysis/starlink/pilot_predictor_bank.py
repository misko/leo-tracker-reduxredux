"""Differential pilot bank with exact valid-support normalization."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DifferentialBank:
    """Precomputed exact/control replicas and valid-support normalization."""

    transforms: np.ndarray
    energies: np.ndarray
    lags: tuple[int, ...]
    period: int


def prepare_bank(exact: np.ndarray, control: np.ndarray, lags: tuple[int, ...]) -> DifferentialBank:
    if exact.shape != (10000,) or control.shape != exact.shape:
        raise ValueError("templates must span three frames / 10000 samples")
    if not lags or any(d not in (0, 1, 2, 4) for d in lags):
        raise ValueError("unsupported differential lag")
    replicas = []
    energies = []
    for d in lags:
        count = 50000 - d
        weights = np.full(10000, 5.0)
        weights[:d] -= 1
        wf = np.fft.fft(weights)
        pair = []
        pair_energy = []
        for template in (exact, control):
            ref = template * np.roll(template, d).conj()
            ref = ref - ref.mean()
            rf = np.fft.fft(ref)
            # Weighted mean/energy depend on alignment when the first d input
            # products are absent. Use identical valid support in every score.
            weighted_sum = np.fft.ifft(wf * rf.conj())
            weighted_energy = np.fft.ifft(wf * np.fft.fft(abs(ref) ** 2).conj()).real
            centered_energy = weighted_energy - abs(weighted_sum) ** 2 / count
            pair.append(rf)
            pair_energy.append(np.maximum(centered_energy, 0))
        replicas.append(pair)
        energies.append(pair_energy)
    return DifferentialBank(np.asarray(replicas), np.asarray(energies), lags, 10000)
