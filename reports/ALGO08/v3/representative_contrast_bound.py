"""Prove full-catalogue discovery rivals lose on representative observation pairs."""

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from time import process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import scan as scan_kernel
from leo.analysis.research import retained_track_likelihood as likelihood


SCAN_SHA256 = "49f1f2e9d73b967f694e48033b6d02ea2e1d66285f7941c4f282f5b238e79f89"
PROFILE_SHA256 = "73c24d054d5676c7d7051779a6960f8f692ce0d97bc23d292470aa01f6110bcf"
MAX_HZ = 2.**21
MAX_COLUMNS = 4096
PAIR_LIMIT = 8
# Conservative absolute per-point error for rounded alias/bias subtraction,
# weighted products and the bounded white-noise dot products in this domain.
ERROR_HZ = 2.**-12
RELATIVE_MARGIN = 1e-9


def representative_pairs(count):
    pairs = min(PAIR_LIMIT, count // 2)
    indexes = np.arange(2*pairs) * (count-1) // (2*pairs-1)
    return indexes[:pairs], indexes[pairs:][::-1]


def centered_lower(y, f, pairs):
    """Sum independently demeaned disjoint pairs, rounded toward zero."""
    i, j = pairs
    left, right = y[i] - f[:, i], y[j] - f[:, j]
    distance = np.nextafter(np.abs(left - right), -np.inf)
    # Permit a wide interval around the common shift after rounded arithmetic.
    distance = np.maximum(0., distance - 2*ERROR_HZ)
    return np.sum(distance**2, axis=1) / 2 * (1 - RELATIVE_MARGIN)


def incumbent_upper(y, predicted, inverse):
    """Bound the stock score above using a fixed bias and its original alias."""
    raw = y - predicted
    center = -raw.mean() / likelihood.PERIOD
    alias = np.rint(center)
    # The full-row mean can differ with an array's reduction layout. Keep all
    # rivals when that could cross even one half-integer alias boundary.
    if abs(center-alias) >= .5 - ERROR_HZ/likelihood.PERIOD:
        return None
    aligned = raw + alias * likelihood.PERIOD
    prior = (likelihood.NOISE / likelihood.BIAS)**2
    bias = aligned.mean() * len(y) / (len(y) + prior)
    whitened = (aligned-bias) / likelihood.NOISE
    norm = np.sqrt(np.sum(whitened**2) + (bias / likelihood.BIAS)**2)
    padded = norm + np.sqrt(len(y)+1) * ERROR_HZ / likelihood.NOISE
    logvolume = np.log1p(likelihood.BIAS**2 * (inverse @ inverse))
    return (padded**2 + logvolume) * (1 + RELATIVE_MARGIN)


class RetainedRows:
    def __init__(self, values, lookup):
        self.values, self.lookup = values, lookup

    def __getitem__(self, index):
        compact = self.lookup[index]
        if np.any(compact < 0):
            raise ValueError("Discovery requested diagnostics for an excluded orbit")
        return self.values[compact]


def support(scan, index, y, predicted):
    inverse, volume = scan.white[index]
    n = len(y)
    diagonal = np.diag(inverse)
    return (12 <= n <= MAX_COLUMNS and y.dtype == predicted.dtype == np.float64 and volume == 0.
            and abs(y).max() <= MAX_HZ and predicted.min() >= -MAX_HZ and predicted.max() <= MAX_HZ
            and (diagonal == 1/likelihood.NOISE).all() and np.count_nonzero(inverse) == n)


def checked_curve(curve, scan, index, y, predicted, method, visible, counts):
    counts["tracks"] += 1
    counts["all_catalogue_rows"] += len(visible)

    def fallback(reason):
        counts[reason] += 1
        counts["exact_profile_rows"] += len(visible)
        return curve(index, y, predicted, method)

    if not support(scan, index, y, predicted):
        return fallback("unsupported")
    kept = visible.copy()
    if visible.any():
        scatter = centered_lower(y, predicted, representative_pairs(len(y)))
        j = int(np.argmin(np.where(visible, scatter, np.inf)))
        incumbent = incumbent_upper(y, predicted[j], np.diag(scan.white[index][0]))
        if incumbent is None:
            return fallback("alias_boundary")
        cost_lower = scatter / likelihood.NOISE**2 * (1 - RELATIVE_MARGIN)
        rms_fails = scatter > len(y) * 450.**2 * (1 + RELATIVE_MARGIN)
        kept &= ~((cost_lower > incumbent) & rms_fails)
    kept[0] = True
    rows = np.flatnonzero(kept)
    if len(rows) >= .75 * len(visible):
        return fallback("insufficient_pruning")
    if len(rows) == 1:
        rows = np.array([0, 1])
    compact = predicted[rows]
    if predicted.flags.f_contiguous and not predicted.flags.c_contiguous:
        compact = np.asfortranarray(compact)
    terms = curve(index, y, compact, method)
    lookup = np.full(len(visible), -1, int)
    lookup[rows] = np.arange(len(rows))
    passing = np.zeros(lookup.shape, bool)
    passing[rows] = terms["passing"]
    cost = np.full(lookup.shape, np.inf)
    cost[rows] = terms["cost"]
    for eligible in (visible & kept, visible & passing):
        scores = np.sort(cost[eligible])
        if len(scores) > 1 and scores[1] - scores[0] <= RELATIVE_MARGIN*max(1., scores[1]):
            return fallback("cost_tie")
    if np.any(np.abs(terms["rms"] - 450) <= ERROR_HZ) or np.any(np.abs(abs(terms["bias"]) - 3000) <= ERROR_HZ):
        return fallback("gate_boundary")
    counts["exact_profile_rows"] += len(rows)
    counts["horizon_rows_skipped"] += np.count_nonzero(~visible & (lookup < 0))
    counts["contrast_rows_skipped"] += np.count_nonzero(visible & (lookup < 0))
    return dict({name: RetainedRows(values, lookup) for name, values in terms.items()
                 if name not in ("passing", "cost", "diagnostics")},
                passing=passing, cost=cost, diagnostics=dict(noise_screen_pass=passing.copy()))


@contextmanager
def bounded_nominations(scan, counts, *, enabled):
    for module, expected in ((scan_kernel, SCAN_SHA256), (likelihood, PROFILE_SHA256)):
        if sha256(Path(module.__file__).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Unreviewed all-catalogue rank source: {module.__name__}")
    ordinary, curve, predictions = scan.association, scan.curve, scan.predictions

    def association(state, base, point, method, *, all_tracks=False):
        if method not in ("shared_phase", "receiver_smooth") or all_tracks or state["extra"]:
            return ordinary(state, base, point, method, all_tracks=all_tracks)
        elevation = None

        def projected(*args, **kwargs):
            nonlocal elevation
            result = predictions(*args, **kwargs)
            elevation = result[1]
            return result

        def score(index, y, predicted, method):
            if not enabled:
                counts["tracks"] += 1
                counts["all_catalogue_rows"] += len(predicted)
                counts["exact_profile_rows"] += len(predicted)
                return curve(index, y, predicted, method)
            visible = elevation[:, scan.index[index]].min(axis=1) >= 0.
            return checked_curve(curve, scan, index, y, predicted, method, visible, counts)

        cpu = process_time()
        try:
            with patch.object(scan, "predictions", projected), patch.object(scan, "curve", score):
                return ordinary(state, base, point, method)
        finally:
            counts["association_cpu_s"] += process_time() - cpu

    with patch.object(scan, "association", association):
        yield
