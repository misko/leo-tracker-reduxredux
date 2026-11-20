"""Phase-consistent raw-pilot autocorrelation followed by exact regional GLRT."""

from time import process_time

import numpy as np
from scipy.signal import correlate

from . import anchor_grid, spectral_grid
from .sparse_epoch import _local_maxima

LAGS = (1, 8, 15)
PROPOSALS = 12
RADIUS = 4


def _fold(product, frames, size):
    accum = np.zeros(size, dtype=np.complex64)
    support = np.zeros(size, dtype=np.int16)
    for start in frames:
        available = min(size, len(product) - start)
        if available > 0:
            accum[:available] += product[start : start + available]
            support[:available] += 1
    np.divide(accum, support, out=accum, where=support > 0)
    accum -= accum.mean()
    return accum


def lag_products(values, template, starts, frames, aperture, epochs):
    """Correlate each complex lag against its exact anchor-template product."""
    iq = np.asarray(values, dtype=np.complex64)
    ref = np.asarray(template, dtype=np.complex64)
    outputs = []
    for lag in LAGS:
        length = aperture - lag
        kernel = np.zeros(starts[-1] + length, dtype=np.complex64)
        for start in starts:
            kernel[start : start + length] = (
                ref[start + lag : start + aperture] * ref[start : start + length].conj()
            )
        product = iq[lag:] * iq[:-lag].conj()
        folded = _fold(product, frames, len(kernel) + epochs - 1)
        energy = np.vdot(kernel, kernel).real
        outputs.append(correlate(folded, kernel, mode="valid", method="fft") / energy)
    return tuple(outputs)


def phase_score(products):
    left, center, right = products
    return np.abs(left.conj() * center + center.conj() * right)


def proposals(scores):
    peaks = np.flatnonzero(
        (scores > 0) & (scores >= np.roll(scores, 1)) & (scores > np.roll(scores, -1))
    )
    selected = []
    for epoch in peaks[np.argsort(-scores[peaks], kind="stable")]:
        distances = [abs(epoch - other) for other in selected]
        if all(min(d, len(scores) - d) >= 2 * RADIUS + 1 for d in distances):
            selected.append(epoch)
            if len(selected) == PROPOSALS:
                break
    return np.asarray(selected, dtype=np.int32)


class DifferentialGate(spectral_grid.SpectralGrid):
    def __init__(self, library, control):
        super().__init__(library, control)
        self._region = None

    def score_grid(self, values, template, sample_rate, frequencies, symbols, epochs):
        start = process_time()
        args = values, template, sample_rate, frequencies, symbols, epochs
        self._region = None
        supported = (
            sample_rate == 10_000_000
            and epochs == 13333
            and tuple(symbols) == tuple(sorted(set(symbols)))
        )
        prepared = None
        if supported:
            prepared = spectral_grid._prepare(
                values, template, sample_rate, np.asarray(frequencies), tuple(symbols), epochs
            )
        if prepared is None:
            return super().score_grid(*args)
        grid = prepared[0]
        del prepared
        lagged = lag_products(values, template, grid.starts, grid.frames, grid.aperture, epochs)
        selected = proposals(phase_score(lagged))
        region = np.unique((selected[:, None] + np.arange(-RADIUS, RADIUS + 1)) % epochs).astype(
            np.int32
        )
        grid.timing.update(
            coarse_cpu_s=process_time() - start,
            fallback=None,
            lag_product_count=len(values) * len(LAGS) - sum(LAGS),
            lag_fft_count=3 * len(LAGS),
            proposal_epochs=selected.tolist(),
            verified_epochs=region.tolist(),
            lag_result_bytes=sum(lag.nbytes for lag in lagged),
        )
        self._region = grid, region
        self.receipts.append(grid.timing)
        return tuple(grid.scores)

    def retain_peaks(self, residuals, scores, count, epoch_separation, cfo_separation, epochs):
        if self._region is None:
            return super().retain_peaks(
                residuals, scores, count, epoch_separation, cfo_separation, epochs
            )
        start = process_time()
        grid, region = self._region
        self._region = None
        guard = np.clip(region[:, None] + (-1, 0, 1), 0, epochs - 1)
        starts = np.unique(guard // spectral_grid.TILE * spectral_grid.TILE).astype(np.int32)
        if len(starts):
            for index, row in enumerate(grid.scores):
                self._repair(
                    *grid.iq,
                    grid.valid,
                    grid.aperture,
                    grid.direct[0][index],
                    grid.direct[1][index],
                    grid.starts,
                    len(grid.starts),
                    grid.frames,
                    len(grid.frames),
                    grid.inverse_iq_norm,
                    epochs,
                    starts,
                    len(starts),
                    row,
                )
        np.divide(grid.scores, grid.support, out=grid.scores, where=grid.support > 0)
        wanted = np.zeros(epochs, dtype=bool)
        wanted[region] = True
        eligible = wanted & _local_maxima(grid.scores)
        candidates = np.where(eligible, grid.scores, -np.inf)
        result = anchor_grid.retained_peaks(
            residuals, candidates, count, epoch_separation, cfo_separation, epochs
        )
        grid.timing.update(
            repair_cpu_s=process_time() - start,
            repair_tiles=len(starts) * len(grid.scores),
            repaired_cells=len(starts) * len(grid.scores) * spectral_grid.TILE,
        )
        return result
