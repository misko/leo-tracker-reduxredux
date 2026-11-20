"""Coarse pilot acquisition by multiplying IQ windows by a bank of short filters."""

import ctypes
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from leo.analysis.starlink.templates import FRAME_RATE_HZ, OFDM_SYMBOL_DURATION_S


def native_grid(library):
    """Bind the single-precision FIR kernel once per detector session."""
    call = ctypes.CDLL(str(Path(library).resolve())).fold_filter_bank
    float_array = np.ctypeslib.ndpointer(dtype=np.float32, flags="C_CONTIGUOUS")
    int_array = np.ctypeslib.ndpointer(dtype=np.int32, flags="C_CONTIGUOUS")
    double_array = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
    integer = ctypes.c_int
    call.argtypes = [
        float_array,
        float_array,
        integer,
        float_array,
        float_array,
        integer,
        integer,
        integer,
        int_array,
        integer,
        float_array,
        integer,
        double_array,
        int_array,
    ]
    call.restype = None

    def grid(values, template, sample_rate_hz, absolute_cfo_hz, symbols, epoch_count):
        frequencies = np.asarray(absolute_cfo_hz, dtype=float)
        values = np.asarray(values, dtype=np.complex128)
        template = np.asarray(template, dtype=np.complex128)
        if any(array.ndim != 1 for array in (values, template, frequencies)):
            raise ValueError("IQ, template and frequencies must be vectors")
        if sample_rate_hz <= 0 or epoch_count < 0:
            raise ValueError("invalid grid dimensions")
        maximum = np.iinfo(np.int32).max
        if (
            len(values) + len(template) >= maximum
            or len(frequencies) * max(epoch_count, len(template)) >= maximum
        ):
            raise ValueError("filter bank exceeds its native index range")
        if not len(frequencies):
            return ()
        xr, xi = (np.ascontiguousarray(a, dtype=np.float32) for a in (values.real, values.imag))
        scores = np.zeros((len(frequencies), epoch_count))
        support = np.zeros(epoch_count, dtype=np.int32)
        period = sample_rate_hz / FRAME_RATE_HZ
        frames = np.rint(np.arange(int(np.ceil(len(values) / period)) + 1) * period).astype(
            np.int32
        )
        frames = frames[frames < len(values)]
        prefix = np.r_[0.0, np.cumsum(values.real**2 + values.imag**2, dtype=np.float64)]
        norms = {}
        for symbol in symbols:
            start = round(symbol * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
            stop = round((symbol + 1) * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
            width = stop - start
            if start < 0 or width < 1 or stop > len(template):
                raise ValueError("invalid anchor support")
            if width > len(values):
                continue
            if width not in norms:
                energy = np.sqrt(np.maximum(prefix[width:] - prefix[:-width], 0.0))
                norms[width] = np.divide(
                    1.0, energy, out=np.zeros_like(energy), where=energy > 0
                ).astype(np.float32)
            ref = np.asarray(template[start:stop], dtype=np.complex128)
            norm = np.linalg.norm(ref)
            coefficients = (
                np.exp(-2j * np.pi / sample_rate_hz * frequencies[:, None] * np.arange(width))
                * ref.conj()
            )
            if norm:
                coefficients /= norm
            cr, ci = (
                np.ascontiguousarray(a, dtype=np.float32)
                for a in (coefficients.real, coefficients.imag)
            )
            call(
                xr,
                xi,
                len(values),
                cr,
                ci,
                len(frequencies),
                width,
                start,
                frames,
                len(frames),
                norms[width],
                epoch_count,
                scores,
                support,
            )
        np.divide(scores, support[None, :], out=scores, where=support[None, :] > 0)
        return tuple(scores)

    return grid


def score_grid(values, template, sample_rate_hz, absolute_cfo_hz, symbols, epoch_count):
    """Return the complete normalized score map for the acquisition hypotheses."""
    frequencies = np.asarray(absolute_cfo_hz, dtype=float)
    if not len(frequencies):
        return ()
    starts = np.rint(np.asarray(symbols) * sample_rate_hz * OFDM_SYMBOL_DURATION_S).astype(int)
    stops = np.rint((np.asarray(symbols) + 1) * sample_rate_hz * OFDM_SYMBOL_DURATION_S).astype(int)
    if np.any(starts < 0) or np.any(stops > len(template)) or np.any(stops <= starts):
        raise ValueError("invalid anchor support")
    period = sample_rate_hz / FRAME_RATE_HZ
    frames = np.rint(np.arange(int(np.ceil(len(values) / period)) + 1) * period).astype(int)
    frames = frames[frames < len(values)]
    scores = np.zeros((epoch_count, len(frequencies)))
    support = np.zeros(epoch_count, dtype=int)
    prefix = np.r_[0.0, np.cumsum(values.real**2 + values.imag**2, dtype=np.float64)]
    for width in np.unique(stops - starts):
        if width > len(values):
            continue
        local = starts[stops - starts == width]
        taps = np.arange(width)
        references = np.asarray(template[local[:, None] + taps], dtype=np.complex128)
        norm = np.sqrt(np.einsum("ij,ij->i", references.conj(), references).real)
        # Absolute output phase cancels in the magnitude. Move CFO rotation onto the short
        # filter taps so all candidate CFOs and symbols share a single IQ window matrix.
        rotation = np.exp((-2j * np.pi / sample_rate_hz) * taps[:, None] * frequencies)
        bank = np.ascontiguousarray(
            (references.conj().T[:, :, None] * rotation[:, None, :]).reshape(width, -1)
        )
        windows = sliding_window_view(values, width)
        for first in range(0, len(windows), 512):
            end = min(first + 512, len(windows))
            corr = np.ascontiguousarray(windows[first:end], dtype=np.complex128) @ bank
            magnitude = np.abs(corr).reshape(end - first, len(local), len(frequencies))
            energy = np.maximum(prefix[first + width : end + width] - prefix[first:end], 0)
            denominator = np.sqrt(energy)[:, None] * norm
            np.divide(
                magnitude, denominator[:, :, None], out=magnitude, where=denominator[:, :, None] > 0
            )
            magnitude[denominator <= 0] = 0
            for j, offset in enumerate(local):
                origins = frames + offset
                active = origins[(origins < end) & (origins + epoch_count > first)]
                for origin in active:
                    a, b = max(first, origin), min(end, origin + epoch_count)
                    scores[a - origin : b - origin] += magnitude[a - first : b - first, j]
                    support[a - origin : b - origin] += 1
    np.divide(scores, support[:, None], out=scores, where=support[:, None] > 0)
    return tuple(np.ascontiguousarray(scores.T))


def retained_peaks(residuals, score_rows, count, epoch_separation, cfo_separation, epoch_count):
    """Select the same local peaks and ties as heap-based nonmaximum suppression."""
    if len(score_rows) != len(residuals):
        raise ValueError("each CFO must have a score row")
    if not len(score_rows) or not epoch_count:
        return ()
    frequencies = np.asarray(residuals)
    scores = np.asarray(score_rows, dtype=float)
    if scores.shape != (len(frequencies), epoch_count):
        raise ValueError("unexpected score grid dimensions")
    if epoch_count == 1:
        eligible = scores > 0
    else:
        padded = np.pad(scores, ((0, 0), (1, 1)), constant_values=-np.inf)
        left, right = padded[:, :-2], padded[:, 2:]
        eligible = (scores >= left) & (scores >= right) & ((scores > left) | (scores > right))
    remaining = np.where(eligible, scores, -np.inf)
    selected = []
    for _ in range(count):
        best = remaining.max()
        if best == -np.inf:
            break
        rows, epochs = np.nonzero(remaining == best)
        idx = 0 if len(rows) == 1 else np.lexsort((rows, epochs, abs(frequencies[rows])))[0]
        r, e = rows[idx], epochs[idx]
        selected.append((float(best), int(e), float(frequencies[r])))
        remaining[r, e] = -np.inf
        close = np.flatnonzero(abs(frequencies - frequencies[r]) <= cfo_separation)
        # Suppression uses a strict circular epoch radius on the original map.
        neighborhood = (e + np.arange(1 - epoch_separation, epoch_separation)) % epoch_count
        remaining[np.ix_(close, neighborhood)] = -np.inf
    return tuple(selected)


def fractional_sampler(original):
    """Reuse one normalized Lanczos kernel when a complete index grid has one fractional part."""

    def sample(values, positions, *, half_width=8):
        locations = np.asarray(positions, dtype=float)
        if (
            not locations.size
            or np.ndim(values) != 1
            or not np.isfinite(locations).all()
            or type(half_width) is not int
            or half_width < 2
        ):
            return original(values, positions, half_width=half_width)
        base = np.floor(locations).astype(np.int64)
        fraction = locations - base
        offset = fraction.flat[0]
        if offset == 0 or not np.all(fraction == offset) or min(offset, 1 - offset) < 1e-10:
            return original(values, positions, half_width=half_width)
        if base.min() < half_width - 1 or base.max() + half_width >= len(values):
            return original(values, positions, half_width=half_width)
        taps = np.arange(1 - half_width, half_width + 1)
        delta = offset - taps
        weights = np.sinc(delta) * np.sinc(delta / half_width)
        weights /= weights.sum()
        return np.sum(
            np.asarray(values, dtype=np.complex128)[base[..., None] + taps] * weights, axis=-1
        )

    return sample
