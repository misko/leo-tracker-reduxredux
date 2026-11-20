"""Propose on a full epoch/CFO grid with reduced support, then score original cells."""

from time import process_time_ns

import numpy as np

FRAME_COUNT = 2
ANCHOR_COUNT = 4
NOMINATIONS = 32
RADIUS = 6


def strata(length, count):
    """Take equal-width stratum centers, preserving the original order."""
    take = min(count, length)
    return ((2 * np.arange(take, dtype=np.intp) + 1) * length) // (2 * take)


def intervals(epochs, nominated):
    mask = np.zeros(epochs, dtype=bool)
    neighbors = np.arange(-RADIUS, RADIUS + 1, dtype=np.intp)
    for _, epoch, _ in nominated:
        mask[(epoch + neighbors) % epochs] = True
    edges = np.flatnonzero(np.diff(np.r_[False, mask, False]))
    return tuple(zip(edges[::2].tolist(), edges[1::2].tolist(), strict=True))


def scored_interior(epochs, spans):
    """Eligibility for the original non-circular local-maximum test."""
    return tuple((a + (a > 0), b - (b < epochs)) for a, b in spans)


def propose(acquisition, args, residuals, epoch_separation, cfo_separation, retain):
    samples, template, rate, absolute, symbols, epochs = args
    native = acquisition._native_acquisition.folded_anchor_score_grid
    scientific_lanes = len(absolute)
    step = acquisition._constant_grid_step(absolute)
    execution = (*absolute, absolute[-1] + step) if scientific_lanes == 11 and step else absolute
    frequencies = np.asarray(execution, dtype=np.float64)
    starts = np.array(
        [round(s * rate * acquisition.OFDM_SYMBOL_DURATION_S) for s in symbols], dtype=np.intp
    )
    stops = np.array(
        [round((s + 1) * rate * acquisition.OFDM_SYMBOL_DURATION_S) for s in symbols], dtype=np.intp
    )
    period = rate / acquisition.FRAME_RATE_HZ
    frames_full = []
    while (offset := round(len(frames_full) * period)) < samples.size:
        frames_full.append(offset)
    offsets = np.asarray(frames_full, dtype=np.intp)
    prefix = acquisition._power_prefix(samples)
    anchors, frames = strata(len(starts), ANCHOR_COUNT), strata(len(offsets), FRAME_COUNT)
    time = process_time_ns()
    thin = native(
        samples,
        template,
        frequencies,
        starts[anchors],
        stops[anchors],
        offsets[frames],
        prefix,
        rate,
        epochs,
    )[:scientific_lanes]
    proposal_cpu = (process_time_ns() - time) / 1e6
    time = process_time_ns()
    peaks = retain(residuals, thin, NOMINATIONS, epoch_separation, cfo_separation, epochs)
    nominated = [p for p in peaks if p[0] > 0]
    spans = intervals(epochs, nominated)
    nomination_cpu = (process_time_ns() - time) / 1e6
    thin_bytes = thin.nbytes
    del thin
    time = process_time_ns()
    # Missing cells are NaN so the original peak finder rejects an interior
    # peak with an unscored neighbor. Physical endpoints retain their rules.
    exact = np.full((scientific_lanes, epochs), np.nan, dtype=np.float64)
    block_bytes = 0
    for a, b in spans:
        block = native(
            samples, template, frequencies, starts, stops, offsets + a, prefix, rate, b - a
        )
        block_bytes = max(block_bytes, block.nbytes)
        exact[:, a:b] = block[:scientific_lanes]
    rescore_cpu = (process_time_ns() - time) / 1e6
    report = dict(
        original_cells=epochs * scientific_lanes,
        eligible_ranges=scored_interior(epochs, spans),
        rescored_ranges=spans,
        rescored_cells=sum(b - a for a, b in spans) * scientific_lanes,
        coarse_numpy_buffer_peak_bytes=prefix.nbytes + max(thin_bytes, exact.nbytes + block_bytes),
        coarse_frames=frames.tolist(),
        coarse_anchors=[symbols[i] for i in anchors],
        nominations=len(nominated),
        proposal_cpu_ms=proposal_cpu,
        nomination_cpu_ms=nomination_cpu,
        rescore_cpu_ms=rescore_cpu,
    )
    return tuple(exact), report
