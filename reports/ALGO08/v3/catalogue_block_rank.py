"""Scoped cold-rank prototype with a full-shape original bias reduction."""

from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from textwrap import dedent
from types import MethodType
from unittest.mock import patch

import numpy as np

import catalogue_block_bound as block


def reduced_profile(observed, predictions, retained, diagonal, padded):
    """Apply the white profile while keeping the stock height and BLAS bias call."""
    raw = observed - predictions
    mean = -raw.mean(axis=1) / block.PERIOD
    if np.any(np.abs(mean - np.floor(mean) - .5) < 1e-8):
        return None
    alias = np.rint(mean)
    raw += alias[:, None] * block.PERIOD
    z = raw * diagonal
    information = diagonal @ diagonal
    padded.fill(0.)
    padded[retained] = z
    bias = (padded @ diagonal)[retained] / (information + 1 / block.BIAS**2)
    innovations = z - bias[:, None] * diagonal
    residual = raw - bias[:, None]
    cost = np.sum(innovations**2, axis=1) + (bias / block.BIAS) ** 2
    cost += np.log1p(block.BIAS**2 * information)
    return dict(alias=alias, bias=bias, residual=residual, innovations=block.NOISE*innovations,
                rms=np.sqrt(np.mean(residual**2, axis=1)), cost=cost)


class SelectedRows:
    def __init__(self, values, lookup):
        self.values, self.lookup = values, lookup

    def __getitem__(self, row):
        local = self.lookup[row]
        if local < 0:
            raise ValueError("An excluded block supplied a required rank diagnostic")
        return self.values[local]


class BlockCurves:
    def __init__(self, scan, stock, projected, screen, counts):
        self.scan, self.stock, self.projected, self.screen, self.counts = scan, stock, projected, screen, counts
        self.base, self.eligible, self.indexes = None, False, {}
        self.pad = np.empty(0, dtype=np.float64)
        self.samples = [block.sample_indices(len(row)) for row in scan.index]

    def _fallback(self, i, y, f, e, method):
        self.counts["full_fallback"] += 1
        track, columns = self.scan.tracks[i], self.scan.index[i]
        predicted, visible = self.stock(track, columns, f, e)
        return self.scan.curve(i, y, predicted, method), visible

    def __call__(self, i, y, f, e, method):
        self.counts["calls"] += 1
        sample = self.samples[i]
        if (method not in ("shared_phase", "receiver_smooth") or type(f) is not self.projected
                or type(e) is not self.projected or f.changed_rows is not e.changed_rows or sample is None
                or y.dtype != np.dtype(np.float64) or not block.white_domain(y) or len(y) > 4096):
            return self._fallback(i, y, f, e, method)
        if self.base is not f.base:
            self.base = f.base
            self.eligible = bool(f.base.dtype == np.dtype(np.float64) and np.isfinite(f.base).all()
                                 and np.max(np.abs(f.base)) <= block.MAX_ABS_HZ / 2.)
            self.indexes.clear()
        scale = self.scan.tracks[i]["rf_hz"] / 11.5e9
        if not self.eligible or not np.isfinite(scale) or abs(scale) > 2.:
            return self._fallback(i, y, f, e, method)
        all_columns = self.scan.index[i]
        if i not in self.indexes:
            cols = all_columns[sample]
            self.indexes[i] = block.nominal_blocks(scale*f.base[:, cols], e.base[:, cols], sample)
            self.counts["index_builds"] += 1
        index = self.indexes[i]
        if index is None:
            return self._fallback(i, y, f, e, method)
        nrows = f.base.shape[0]
        shifted = np.zeros(nrows, dtype=bool)
        shifted[f.changed_rows] = True
        lower = index.lower(y)
        _, incumbent = block.independent_incumbent(index, lower, y, shifted, f.base, e.base, all_columns, scale)
        # Inflate the feasible stock upper bound for the full supported dot
        # length, and round the lower estimate toward the unresolved interval.
        incumbent *= 1. + 1e-9
        lower *= 1. - 1e-9
        certificate = block.reject_blocks(index, lower, incumbent, len(y))
        certificate[np.searchsorted(index.starts, np.flatnonzero(index.rows == 0)[0], side="right") - 1] = False
        keep = np.ones(nrows, dtype=bool)
        keep[index.rows] = ~index.repeated(certificate)
        keep[f.changed_rows] = True
        keep[0] = True
        retained = np.flatnonzero(keep)
        if len(retained) < 2 or len(retained) >= nrows / 2:
            return self._fallback(i, y, f, e, method)

        predictions = np.asfortranarray(scale*f.base[np.ix_(retained, all_columns)])
        heights = e.base[np.ix_(retained, all_columns)]
        changed = np.searchsorted(retained, f.changed_rows)
        predictions[changed] = scale*f.values[:, all_columns]
        heights[changed] = e.values[:, all_columns]
        inverse, volume = self.scan.white[i]
        if volume != 0. or predictions.dtype != np.dtype(np.float64):
            return self._fallback(i, y, f, e, method)
        if self.pad.size < nrows*len(y):
            self.pad = np.empty(nrows*len(y), dtype=np.float64)
        padded = self.pad[:nrows*len(y)].reshape((nrows, len(y)), order="F")
        result = reduced_profile(y, predictions, retained, np.diag(inverse), padded)
        if result is None:
            return self._fallback(i, y, f, e, method)
        self.counts.update(compact_calls=1, rows_saved=nrows-len(retained), original_rows=nrows,
                           rows_retained=len(retained), padded_cells=padded.size)
        visible = np.zeros(nrows, dtype=bool)
        visible[retained] = heights.min(axis=1) >= 0
        finite = (result["rms"] <= 450.) & (np.abs(result["bias"]) <= 3000.)
        possible = np.flatnonzero(finite)
        passing = np.zeros(nrows, dtype=bool)
        if len(possible):
            passing[retained[possible]] = self.screen(result["innovations"][possible], self.scan.tracks[i]["times"])["noise_screen_pass"]
        lookup = np.full(nrows, -1, dtype=np.intp)
        lookup[retained] = np.arange(len(retained))
        terms = dict(passing=passing, parts=np.ones(nrows, dtype=int), split_at=np.full(nrows, -1, dtype=int))
        for name in ("rms", "bias", "cost"):
            terms[name] = np.full(nrows, np.inf)
            terms[name][retained] = result[name]
        for name in ("residual", "innovations", "alias"):
            terms[name] = SelectedRows(result[name], lookup)
        terms["diagnostics"] = dict(noise_screen_pass=passing.copy())
        return terms, visible


@contextmanager
def install(scan, tables, work, *, borrow=False):
    from cold_track_row_reuse import CentreRows, PROFILE_PIN, SCAN_PIN, SHARING_PIN, SPARSE_PIN
    from leo.analysis.localization_v3 import scan as kernel
    from leo.analysis.research import retained_track_likelihood as white
    from tools.pipeline_eval.variants import algo08_sparse_rank_projection as sparse

    original = scan.association.__func__
    pins = ((original.__code__.co_filename, SCAN_PIN), (sparse.__file__, SPARSE_PIN),
            (tables.projection.__code__.co_filename, SHARING_PIN), (white.__file__, PROFILE_PIN))
    if (borrow or original is not kernel.ScanLikelihood.association or kernel.profile is not white.profile
            or scan.curve.__func__ is not kernel.ScanLikelihood.curve
            or any(sha256(Path(name).read_bytes()).hexdigest() != pin for name, pin in pins)):
        raise ValueError("Unsupported original cached cold association")
    source = getsource(original)
    old = ('            terms = self.curve(i, y, t["rf_hz"] / 11.5e9 * f[:, ix], method)\n'
           '            visible = e[:, ix].min(axis=1) >= 0\n')
    if source.count(old) != 1:
        raise ValueError("Unexpected scoped association consumer")
    stock = CentreRows(tables, sparse.ProjectedRows, work)
    namespace = dict(original.__globals__, _bounded=BlockCurves(scan, stock, sparse.ProjectedRows,
                                                                 kernel.batch_noise_screen, work))
    exec(compile(dedent(source.replace(old, '            terms, visible = _bounded(i, y, f, e, method)\n')),
                 original.__code__.co_filename, "exec"), namespace)
    with patch.object(scan, "association", MethodType(namespace[original.__name__], scan)):
        yield
