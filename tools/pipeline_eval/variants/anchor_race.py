"""Rank complementary complete-anchor panels before exact capture rescoring."""

from functools import partial
from hashlib import sha256
from time import process_time_ns

import numpy as np

from .thinned_capture import intervals, scored_interior, strata

CAP = 64
CONSENSUS = 32


def top(scores, residuals, count, epoch_gap, cfo_gap, selected=()):
    """Capture's ordered suppression over positive local peaks, seeded by another panel."""
    left = np.full_like(scores, -np.inf)
    right = left.copy()
    left[:, 1:] = scores[:, :-1]
    right[:, :-1] = scores[:, 1:]
    f, e = np.nonzero(
        (scores > 0) & (scores >= left) & (scores >= right) & ((scores > left) | (scores > right))
    )
    values, cfos = scores[f, e], np.asarray(residuals)[f]
    ordering = np.lexsort((f, e, abs(cfos), -values))
    retained = list(selected)
    period = scores.shape[1]
    for i in ordering:
        epoch, cfo = int(e[i]), float(cfos[i])
        if any(
            min(abs(epoch - t), period - abs(epoch - t)) < epoch_gap and abs(cfo - v) <= cfo_gap
            for _, t, v in retained
        ):
            continue
        retained.append((float(values[i]), epoch, cfo))
        if len(retained) == count:
            break
    return retained


def nominate(a, b, residuals, epoch_gap, cfo_gap, role, visit):
    select = partial(top, residuals=residuals, epoch_gap=epoch_gap, cfo_gap=cfo_gap)
    if role == "mean":
        return select((a + b) * 0.5, count=CAP), None, 0
    persistent = select(np.minimum(a, b), count=CONSENSUS)
    both = select(np.maximum(a, b), count=CAP, selected=persistent)
    if role == "sham":
        period = a.shape[1]
        rotate = 1 + int.from_bytes(sha256(f"anchor-race:{visit}".encode()).digest()) % (period - 1)
        return [(s, (e + rotate) % period, f) for s, e, f in both], len(persistent), rotate
    if role != "race":
        raise ValueError("unsupported full-code nomination policy")
    return both, len(persistent), 0


def elapsed(start):
    return (process_time_ns() - start) / 1e6


def propose(
    acquisition,
    args,
    residuals,
    epoch_separation,
    cfo_separation,
    _retain,
    *,
    role="race",
    visit=None,
):
    samples, template, rate, absolute, symbols, epochs = args
    native = acquisition._native_acquisition.folded_anchor_score_grid
    if rate != 10_000_000 or epochs != 13_333 or len(symbols) < 8 or samples.size != 200_000:
        raise ValueError("anchor race requires the installed 20 ms, 10 MS/s capture geometry")
    step = acquisition._constant_grid_step(absolute)
    execution = (*absolute, absolute[-1] + step) if len(absolute) == 11 and step else absolute
    frequencies = np.asarray(execution, dtype=np.float64)
    duration = acquisition.OFDM_SYMBOL_DURATION_S
    starts = np.array([round(s * rate * duration) for s in symbols], dtype=np.intp)
    stops = np.array([round((s + 1) * rate * duration) for s in symbols], dtype=np.intp)
    period = rate / acquisition.FRAME_RATE_HZ
    offsets = np.arange(round(samples.size / period), dtype=np.float64) * period
    offsets = np.rint(offsets).astype(np.intp)
    prefix = acquisition._power_prefix(samples)
    frame_support, anchors = strata(len(offsets), 4), strata(len(symbols), 8)
    inputs = [(anchors[i::2], frame_support[i::2]) for i in (0, 1)]
    lanes = len(residuals)

    clock = process_time_ns()
    a, b = [
        native(
            samples, template, frequencies, starts[ai], stops[ai], offsets[mi], prefix, rate, epochs
        )[:lanes]
        for ai, mi in inputs
    ]
    proposal_ms = elapsed(clock)
    clock = process_time_ns()
    nominated, consensus_count, shift = nominate(
        a, b, residuals, epoch_separation, cfo_separation, role, visit
    )
    spans = intervals(epochs, nominated)
    select_ms = elapsed(clock)
    del a, b

    clock = process_time_ns()
    exact = np.full((lanes, epochs), np.nan, dtype=np.float64)
    for first, last in spans:
        values = native(
            samples,
            template,
            frequencies,
            starts,
            stops,
            offsets + first,
            prefix,
            rate,
            last - first,
        )
        exact[:, first:last] = values[:lanes]
    rescore_ms = elapsed(clock)
    return tuple(exact), dict(
        original_cells=epochs * lanes,
        proposal_cells=2 * epochs * lanes,
        proposal_anchor_frame_terms=epochs * lanes * sum(len(a) * len(m) for a, m in inputs),
        original_anchor_frame_terms=epochs * lanes * len(offsets) * len(symbols),
        rescored_cells=sum(b - a for a, b in spans) * lanes,
        eligible_ranges=scored_interior(epochs, spans),
        rescored_ranges=spans,
        nomination_keys=[(e, f) for _, e, f in nominated],
        nominations=len(nominated),
        consensus_count=consensus_count,
        epoch_rotation=shift,
        panels=[dict(anchors=[symbols[i] for i in a], frames=m.tolist()) for a, m in inputs],
        proposal_cpu_ms=proposal_ms,
        nomination_cpu_ms=select_ms,
        rescore_cpu_ms=rescore_ms,
    )
