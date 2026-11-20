"""Physically exact same-window, same-path Doppler differences from anonymous GLRT."""

from collections import defaultdict
from itertools import combinations

import numpy as np

from ..reference import tracker
from . import doppler_turns as native

METHOD = "paired_doppler"
BOUNDARY = "Native GLRT exact co-observation and independent paired Doppler support"
PERIOD = 1 / 4.4e-6
ARMS = ("c0", "fitted_c")


def fold(hz, period=PERIOD):
    return hz - period * np.rint(hz / period)


def observables(a, b, rf_a, rf_b):
    """Affine RF calibration has a design column only if the carriers differ."""
    return fold(np.asarray(a) - np.asarray(b)), (rf_a - rf_b) / 1e9


def read_peaks(probe):
    found = []
    for p in sorted(
        probe["candidates"], key=lambda x: (-x["fractional_margin"], x["candidate_rank"])
    ):
        if not p["passed_fractional_margin_gate"] or p["fractional_epoch_offset_samples"] is None:
            continue
        hz = float(fold(p["fractional_tracking_cfo_hz"]))
        phase = p["integer_epoch_sample"] + p["fractional_epoch_offset_samples"]
        if np.isfinite([hz, phase]).all() and all(abs(fold(hz - a[0])) >= 160 for a in found):
            found.append((hz, phase, p["candidate_rank"]))
        if len(found) == tracker.MAX_CANDIDATES:
            break
    return found


def separated(a, b, sample_rate):
    return (
        a[2] != b[2]
        and abs(fold(a[0] - b[0])) >= 800
        and abs(fold(a[1] - b[1], sample_rate / 750)) >= 4
    )


def verified(a, b, raw, sample_rate):
    time, i, j = np.intersect1d(a["t"], b["t"], return_indices=True)
    ledger = []
    for t, k, m in zip(time, i, j, strict=True):
        left, right = a["f"][k], b["f"][m]
        counter, peaks = raw[float(t)]
        peak_a = [p for p in peaks if abs(fold(left - p[0])) <= 1e-6]
        peak_b = [p for p in peaks if abs(fold(right - p[0])) <= 1e-6]
        if len(peak_a) == len(peak_b) == 1 and separated(peak_a[0], peak_b[0], sample_rate):
            ledger.append(
                (float(t), counter, float(left), float(right), peak_a[0][2], peak_b[0][2])
            )
    return ledger


def scope(capture):
    counters = defaultdict(set)
    live, windows = {}, {}
    raw_two_peak, raw_opportunities, offset_rows = 0, 0, 0
    rows = sorted(capture.probes, key=lambda r: (r["valid_start_counter"], r["probe_start_ms"]))
    for p in rows:
        counter = p["valid_start_counter"]
        offset = p["probe_start_ms"]
        rx, channel, rf = (p[k] for k in ("receiver_id", "channel", "actual_rf_hz"))
        path = rx, int(channel > 4)
        counters[counter, offset, path].add(rf)
        if offset != 0:
            offset_rows += 1
            continue
        at = (counter - capture.first_counter) / capture.sample_rate_hz + capture.probe_ms / 2000
        block = int(at // 30)
        lane = rx, channel, rf
        peaks = read_peaks(p)
        if peaks:
            k = block, lane
            if k not in windows:
                windows[k] = {}
            if at in windows[k]:
                raise ValueError("duplicate native receiver visit at one physical window")
            windows[k][at] = counter, peaks
            raw_two_peak += any(
                separated(a, b, capture.sample_rate_hz) for a, b in combinations(peaks, 2)
            )
            raw_opportunities += 1
        if block not in live:
            live[block] = native.AnonymousTracks()
        live[block].ingest(at, lane, [a[0] for a in peaks])
    overlaps, pair_rows, linked = 0, [], 0
    for block, layer in live.items():
        by_lane = defaultdict(list)
        for arc in layer.arcs():
            by_lane[arc["lane"]].append(arc)
            linked += 1
        for lane, arcs in by_lane.items():
            options = []
            for first, second in combinations(arcs, 2):
                joined = verified(first, second, windows[block, lane], capture.sample_rate_hz)
                overlaps += bool(joined)
                if len(joined) >= 10 and joined[-1][0] - joined[0][0] >= 12:
                    options.append(joined)
            if options:
                best = max(options, key=lambda r: (r[-1][0] - r[0][0], len(r)))
                pair_rows.append(dict(block=block, lane=lane, witnesses=best))
    candidates = {}
    for r in pair_rows:
        key = r["block"], r["lane"][1:]
        witness = r["witnesses"]
        mark = (witness[-1][0] - witness[0][0], len(witness))
        if key not in candidates or mark > candidates[key][0]:
            candidates[key] = mark, r
    pairs = [r for _, r in candidates.values()]
    return dict(
        raw_probes=len(rows),
        native_rf_lanes=len({(p["channel"], p["actual_rf_hz"]) for p in rows}),
        exact_receiver_path_windows=len(counters),
        simultaneous_distinct_rf_path_windows=sum(len(rf) >= 2 for rf in counters.values()),
        nonzero_probe_offset_rows=offset_rows,
        gated_receiver_windows=raw_opportunities,
        separated_two_peak_windows=raw_two_peak,
        linked_arcs=linked,
        partial_exact_arc_overlaps=overlaps,
        persistent_pairs=len(pairs),
        pair_cfo_witnesses=sum(len(r["witnesses"]) for r in pairs),
        pair_rf_lanes=len({r["lane"][2] for r in pairs}),
        train_pair_blocks=len({r["block"] for r in pairs if r["block"] % 3 != 1}),
        held_pair_blocks=len({r["block"] for r in pairs if r["block"] % 3 == 1}),
        c_identifiable=False,
        pairs=pairs,
    )


def measure(capture):
    evidence = scope(capture)
    supported = min(evidence["train_pair_blocks"], evidence["held_pair_blocks"]) >= 2
    return dict(
        status="withheld",
        reason="paired_position_pending"
        if supported
        else "insufficient_exact_coincident_pair_blocks",
        boundary=BOUNDARY,
        metrics=evidence | dict(position_attempted=False, supports_geometry=supported),
        arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
    )
