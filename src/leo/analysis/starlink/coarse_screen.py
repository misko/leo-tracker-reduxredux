"""Isolated screened acquisition prototype, with a complete FP64 fallback.

Only the acquisition-specific adapter uses partial score maps. The public/full
grid functions remain exact. No precomputed grid or reference winner enters the
screened inference path. This module is not enabled in production.
"""

import numpy as np

from ._screen_bounds import bound
from ._screen_exact import ExactColumns
from ._screen_selection import select


def screen_grid(native, acquisition, values, template, rate, frequencies, symbols, epochs):
    starts = np.asarray([round(s * rate * acquisition.OFDM_SYMBOL_DURATION_S)
                         for s in symbols], dtype=np.intp)
    stops = np.asarray([round((s + 1) * rate * acquisition.OFDM_SYMBOL_DURATION_S)
                        for s in symbols], dtype=np.intp)
    period = rate / acquisition.FRAME_RATE_HZ
    offsets, frame = [], 0
    while (offset := round(frame * period)) < values.size:
        offsets.append(offset)
        frame += 1
    prefix = acquisition._power_prefix(values)
    rows = []
    for start in range(0, len(frequencies), 24):
        tile = frequencies[start:start + 24]
        padded = (*tile, *((tile[-1],) * (24 - len(tile))))
        grid = native.folded_anchor_score_grid(
            np.asarray(values, np.complex128), np.asarray(template, np.complex128),
            np.asarray(padded, dtype=float), starts, stops, np.asarray(offsets, np.intp),
            prefix, float(rate), epochs)
        rows.extend(grid[i] for i in range(len(tile)))
    return tuple(rows)


def acquire(acquisition, args, residuals, count, epoch_separation, cfo_separation,
            *, observer=None):
    """Return exact selected tuples and a map exact at every refinement neighbor."""
    cached_full = None
    epochs = args[-1]

    def full(*unused):
        nonlocal cached_full
        if cached_full is None:
            cached_full = acquisition._folded_anchor_score_grid(*args)
        return cached_full

    def fallback(reason):
        rows = full()
        selected = acquisition._retain_score_map_peaks(
            residuals, rows, count, epoch_separation, cfo_separation, epochs)
        if observer is not None:
            observer(dict(path='full', reason=reason, columns=epochs))
        return rows, selected

    if acquisition._folded_anchor_score_grid_backend() != 'avx2_fma':
        return fallback('unsupported backend')
    try:
        from . import _screen_native
        from ._screen_native import _native_acquisition as native
    except ImportError:
        return fallback('screen extension unavailable')
    screen_kind = getattr(_screen_native, 'SCREEN_KIND', 'fp32')
    selected_bound = bound
    if screen_kind == 'integer_vnni':
        if native.folded_anchor_score_grid_backend() != 'avx2_fma':
            return fallback('integer screen hardware unavailable')
        from ._screen_integer import bound as selected_bound
    elif screen_kind != 'fp32':
        return fallback('unknown screen kind')
    eligibility = selected_bound(acquisition, args)
    if not eligibility['eligible']:
        return fallback(eligibility['reason'])
    if eligibility['absolute_error'] > .01:
        # A broad interval is valid but unlikely to prune well. This changes
        # execution cost only: fallback retains the complete scientific grid.
        return fallback('broad interval')
    approximate = np.asarray(screen_grid(native, acquisition, *args))
    if approximate.shape != (len(residuals), epochs) or not np.isfinite(approximate).all():
        return fallback('invalid screen scores')
    restored = approximate.copy()
    exact = ExactColumns(acquisition, full, args)

    def evaluate(columns):
        values = exact(columns)
        restored[:, columns] = values
        return values

    selected = select(approximate, eligibility['absolute_error'], residuals, count,
                      epoch_separation, cfo_separation, evaluate)
    if selected['fallback'] is not None:
        return fallback(selected['fallback'])
    # A dense request may already have produced the complete original grid.
    # Return it instead of retaining unused approximate entries.
    rows = cached_full if cached_full is not None else tuple(restored)
    if observer is not None:
        observer(dict(path='screened', screen_kind=screen_kind, columns=selected['exact_columns'],
                      native_calls=exact.native_calls, dense_calls=exact.dense_fallback_calls,
                      absolute_error=eligibility['absolute_error']))
    return rows, selected['retained']
