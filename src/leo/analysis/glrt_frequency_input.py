"""Pure adapter from exported fast-scan candidate dictionaries to frequency factors."""

import numpy as np

from leo.analysis.sparse_glrt_likelihood import FrequencyEvidence


def frequency_evidence(
    document, *, mark_temperature=0.1, uniform_marks=False, alias_period_hz=None
):
    """Retain all processed receiver windows and all distinct fractional peaks.

    Mark weights are declared research assumptions, not detector probabilities.
    Empty candidate sets contribute a neutral conditional factor. Device counters
    retain retune gaps. The UTC midpoint is accompanied by its full bracket.
    """
    if not np.isfinite(mark_temperature) or mark_temperature <= 0:
        raise ValueError("invalid mark temperature")
    if alias_period_hz is not None and (not np.isfinite(alias_period_hz) or alias_period_hz <= 0):
        raise ValueError("positive finite alias period required")
    source = document["source"]
    anchor = document["clock_anchor"]
    if anchor is None:
        raise ValueError("capture has no UTC bracket")
    before, after = (anchor[k]["realtime_ns"] for k in ("before", "after"))
    if after < before or after - before > 2_000_000_000:
        raise ValueError("invalid UTC bracket")
    clock_offsets = [
        c["realtime_ns"] - c["monotonic_ns"]
        for c in [anchor["before"], anchor["after"], *document["delivery_clocks"]]
    ]
    if max(clock_offsets) - min(clock_offsets) > 2_000_000_000:
        raise ValueError("capture clock step")
    probes = source["probes"]
    if not probes:
        raise ValueError("no GLRT probes")
    receivers = sorted({p["receiver_id"] for p in probes})
    group_labels = [(r, band) for r in receivers for band in (0, 1)]
    n, width = len(probes), max(1, max(len(p["candidates"]) for p in probes))
    y, w = np.zeros((n, width)), np.zeros((n, width))
    q, group, times, rf = np.zeros(n), np.zeros(n, dtype=int), np.zeros(n), np.zeros(n)
    ids, duplicate_count, empty = [], 0, 0
    support = {}
    for i, probe in enumerate(probes):
        rx, channel = probe["receiver_id"], probe["channel"]
        if channel not in range(1, 9):
            raise ValueError("invalid channel")
        start = probe["valid_start_counter"]
        if start < anchor["sample_counter"]:
            raise ValueError("probe precedes UTC authority")
        support.setdefault(rx, []).append(
            (start, start + round(source["probe_ms"] * 0.001 * source["sample_rate_hz"]))
        )
        ids.append(f"{source['session_id']}:{rx}:{start}")
        group[i] = group_labels.index((rx, int(channel >= 5)))
        times[i] = (start - anchor["sample_counter"]) / source["sample_rate_hz"] + source[
            "probe_ms"
        ] * 0.0005
        rf[i] = probe["actual_rf_hz"]
        if not np.isfinite(rf[i]) or rf[i] <= 0:
            raise ValueError("invalid RF hypothesis")
        retained = []
        for c in sorted(probe["candidates"], key=lambda c: -c["fractional_margin"]):
            f, mark = c["fractional_tracking_cfo_hz"], c["fractional_margin"]
            epoch = c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]
            if not np.all(np.isfinite((f, mark, epoch))):
                raise ValueError("nonfinite candidate")

            def difference(other, f=f):
                delta = f - other
                return (
                    abs(delta)
                    if alias_period_hz is None
                    else abs((delta + alias_period_hz / 2) % alias_period_hz - alias_period_hz / 2)
                )

            if any(difference(v[0]) < 1.0 and abs(epoch - v[2]) < 0.05 for v in retained):
                duplicate_count += 1
                continue
            retained.append((f, mark, epoch))
        if not retained:
            empty += 1
            w[i, 0] = 1
            continue
        count = len(retained)
        y[i, :count] = [v[0] for v in retained]
        marks = np.array([v[1] for v in retained])
        weights = (
            np.ones(count) if uniform_marks else np.exp((marks - marks.max()) / mark_temperature)
        )
        w[i, :count] = weights / weights.sum()
        q[i] = 0.5 if uniform_marks else 0.05 + 0.9 * np.clip(marks.max() / 0.1, 0, 1)
    for intervals in support.values():
        intervals.sort()
        if any(b[0] < a[1] for a, b in zip(intervals, intervals[1:], strict=False)):
            raise ValueError("overlapping/duplicate receiver evidence")
    evidence = FrequencyEvidence(tuple(ids), y, w, q, group, times)
    metadata = dict(
        anchor_utc_ns=(before + after) // 2,
        causal_cutoff_utc_ns=before,
        utc_half_width_s=(after - before) / 2e9,
        group_labels=group_labels,
        receiver_factors=n,
        empty_factors=empty,
        duplicate_candidates_removed=duplicate_count,
        distinct_candidates=int(np.count_nonzero(w)) - empty,
        duration_s=(document["last_sample_counter"] - anchor["sample_counter"])
        / source["sample_rate_hz"],
        mark_policy=(
            "uniform"
            if uniform_marks
            else f"softmax-margin-temperature-{mark_temperature}; q=0.05+0.9*clip(margin/0.1)"
        ),
        calibrated=False,
        alias_period_hz=alias_period_hz,
        **document["provenance"],
    )
    return evidence, rf, metadata
