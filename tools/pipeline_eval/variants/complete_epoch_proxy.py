"""Keep all folded epochs, CFOs, frames and anchors with an 18-tap proposal."""

from time import process_time_ns

import numpy as np

from .thinned_capture import intervals, scored_interior

TAPS = 18
CAP = 96
DIAGNOSTIC_CAP = 32


def elapsed(start):
    return (process_time_ns() - start) / 1e6


def suffix(starts, stops):
    return np.maximum(starts, stops - TAPS)


def propose(acquisition, args, residuals, epoch_separation, cfo_separation, retain):
    samples, template, rate, absolute, symbols, epochs = args
    native = acquisition._native_acquisition.folded_anchor_score_grid
    lanes = len(absolute)
    step = acquisition._constant_grid_step(absolute)
    execution = (*absolute, absolute[-1] + step) if lanes == 11 and step else absolute
    frequencies = np.asarray(execution, dtype=np.float64)
    duration = acquisition.OFDM_SYMBOL_DURATION_S
    starts = np.array([round(symbol * rate * duration) for symbol in symbols], dtype=np.intp)
    stops = np.array([round((symbol + 1) * rate * duration) for symbol in symbols], dtype=np.intp)
    period = rate / acquisition.FRAME_RATE_HZ
    all_offsets = []
    while (offset := round(len(all_offsets) * period)) < samples.size:
        all_offsets.append(offset)
    offsets = np.asarray(all_offsets, dtype=np.intp)
    prefix = acquisition._power_prefix(samples)

    clock = process_time_ns()
    proxy = native(
        samples, template, frequencies, suffix(starts, stops), stops, offsets, prefix, rate, epochs
    )[:lanes]
    proposal_ms = elapsed(clock)
    clock = process_time_ns()
    nominees = [
        p
        for p in retain(residuals, proxy, CAP, epoch_separation, cfo_separation, epochs)
        if p[0] > 0
    ]
    spans = intervals(epochs, nominees)
    diagnostic = scored_interior(epochs, intervals(epochs, nominees[:DIAGNOSTIC_CAP]))
    nominate_ms = elapsed(clock)
    proxy_bytes = proxy.nbytes
    del proxy

    clock = process_time_ns()
    exact = np.full((lanes, epochs), np.nan, dtype=np.float64)
    block_bytes = 0
    for lo, hi in spans:
        block = native(
            samples, template, frequencies, starts, stops, offsets + lo, prefix, rate, hi - lo
        )
        block_bytes = max(block_bytes, block.nbytes)
        exact[:, lo:hi] = block[:lanes]
    rescore_ms = elapsed(clock)
    return tuple(exact), dict(
        original_cells=epochs * lanes,
        proposal_cells=epochs * lanes,
        rescored_cells=sum(b - a for a, b in spans) * lanes,
        eligible_ranges=scored_interior(epochs, spans),
        rescored_ranges=spans,
        cap32_eligible_ranges=diagnostic,
        original_anchor_taps=int(np.sum(stops - starts)),
        proposal_anchor_taps=int(np.sum(stops - suffix(starts, stops))),
        coarse_frames=list(range(len(offsets))),
        coarse_anchors=list(symbols),
        nominations=len(nominees),
        proposal_cpu_ms=proposal_ms,
        nomination_cpu_ms=nominate_ms,
        rescore_cpu_ms=rescore_ms,
        coarse_numpy_buffer_peak_bytes=prefix.nbytes + max(proxy_bytes, exact.nbytes + block_bytes),
    )
