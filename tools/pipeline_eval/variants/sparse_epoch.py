"""Scout a raw epoch lattice and score the shortlisted neighborhoods at full rate."""

import ctypes
import subprocess
from pathlib import Path
from time import process_time

import numpy as np

from . import anchor_grid, spectral_grid
from .anchor_receiver import FLAGS

SOURCE = Path(__file__).with_suffix(".c")
STRIDE = 6
PROPOSALS = 8
RADIUS = 4


def compile_grid(library):
    subprocess.run(["cc", *FLAGS, "-mavx2", str(SOURCE), "-lm", "-o", str(library)], check=True)


def _planes(values, plane):
    padded = np.zeros(STRIDE * plane, dtype=np.float32)
    padded[:len(values)] = values
    return np.ascontiguousarray(padded.reshape(-1, STRIDE).T)


def _local_maxima(rows):
    padded = np.pad(rows, [(0, 0), (1, 1)], constant_values=-np.inf)
    left, right = padded[:, :-2], padded[:, 2:]
    return (rows >= left) & (rows >= right) & ((rows > left) | (rows > right))


class SparseEpochGrid(spectral_grid.SpectralGrid):
    def __init__(self, library, control):
        super().__init__(library, control)
        dll = ctypes.CDLL(str(Path(library).resolve()))
        f, i, d = (np.ctypeslib.ndpointer(dtype=t, flags="C_CONTIGUOUS")
                   for t in (np.float32, np.int32, np.float64))
        n = ctypes.c_int
        self._scout = dll.score_sparse_epochs
        self._scout.argtypes = [f, f, n, n, f, f, n, n, i, n, i, n, f, n, d]
        self._scout.restype = None
        self._sparse = None

    def score_grid(self, values, template, sample_rate, frequencies, symbols, epochs):
        start = process_time()
        args = values, template, sample_rate, frequencies, symbols, epochs
        self._sparse = None
        if sample_rate != 10_000_000 or epochs != 13333:
            return super().score_grid(*args)
        prepared = spectral_grid._prepare(values, template, sample_rate, np.asarray(frequencies),
                                          tuple(symbols), epochs)
        if prepared is None:
            return super().score_grid(*args)
        grid = prepared[0]
        plane = (len(values) + STRIDE - 1) // STRIDE
        real, imag = (_planes(iq, plane) for iq in grid.iq)
        norm = _planes(grid.inverse_iq_norm, plane)
        rows = np.zeros((len(frequencies), (epochs + STRIDE - 1) // STRIDE))
        self._scout(real, imag, plane, grid.valid, *grid.direct, len(frequencies), grid.aperture,
                    grid.starts, len(grid.starts), grid.frames, len(grid.frames), norm, epochs, rows)
        support = grid.support[::STRIDE]
        np.divide(rows, support, out=rows, where=support > 0)
        grid.timing.update(coarse_cpu_s=process_time() - start, fallback=None,
                           scout_cells=int(rows.size), full_cells=int(grid.scores.size),
                           scout_anchor_outputs=int(support.sum()) * len(frequencies),
                           scout_plane_bytes=real.nbytes + imag.nbytes + norm.nbytes + rows.nbytes)
        self._sparse = (grid, rows)
        self.receipts.append(grid.timing)
        return tuple(grid.scores)

    def retain_peaks(self, residuals, scores, count, epoch_separation, cfo_separation, epochs):
        if self._sparse is None:
            return super().retain_peaks(residuals, scores, count, epoch_separation,
                                        cfo_separation, epochs)
        start = process_time()
        grid, scout = self._sparse
        self._sparse = None
        if not grid.inverse_iq_norm.any():
            grid.timing.update(repair_cpu_s=process_time() - start, repair_tiles=0,
                               verified_cells=0)
            return anchor_grid.retained_peaks(residuals, scores, count, epoch_separation,
                                             cfo_separation, epochs)

        sampled_maxima = _local_maxima(scout)
        wanted = np.zeros_like(grid.scores, dtype=bool)
        tile_count = 0
        for index, (row, peaks) in enumerate(zip(scout, sampled_maxima, strict=True)):
            candidates = np.flatnonzero(peaks)
            selected = candidates[np.argsort(-row[candidates], kind="stable")[:PROPOSALS]]
            region = ((selected[:, None] * STRIDE + np.arange(-RADIUS, RADIUS + 1)) % epochs).ravel()
            wanted[index, region] = True
            guard = np.clip(region[:, None] + (-1, 0, 1), 0, epochs - 1)
            starts = np.unique(guard // spectral_grid.TILE * spectral_grid.TILE).astype(np.int32)
            tile_count += len(starts)
            self._repair(*grid.iq, grid.valid, grid.aperture, grid.direct[0][index],
                         grid.direct[1][index], grid.starts, len(grid.starts), grid.frames,
                         len(grid.frames), grid.inverse_iq_norm, epochs, starts, len(starts),
                         grid.scores[index])
        np.divide(grid.scores, grid.support, out=grid.scores, where=grid.support > 0)
        eligible = wanted & _local_maxima(grid.scores)
        candidates = np.where(eligible, grid.scores, -np.inf)
        result = anchor_grid.retained_peaks(residuals, candidates, count, epoch_separation,
                                            cfo_separation, epochs)
        grid.timing.update(repair_cpu_s=process_time() - start, repair_tiles=tile_count,
                           verified_cells=int(wanted.sum()))
        return result
