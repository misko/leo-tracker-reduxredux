"""Pure adapter for frozen public tracking-port dictionaries.

Device counters retain retune gaps. Probe offsets are measured from each
visit's valid start, not from the concatenated IQ payload offset.
"""

import hashlib
import json

import numpy as np


def public_tracking_points(document):
    timing = document["timing"]
    if not document["qualified"] or timing is None or not timing["qualified"]:
        raise ValueError("qualified capture and explicit qualified UTC authority required")
    if timing["session_id"] != document["session_id"]:
        raise ValueError("UTC authority belongs to a different capture")
    offsets = [
        timing[f"{prefix}_realtime_ns"] - timing[f"{prefix}_monotonic_ns"]
        for prefix in ("begin_before", "begin_after", "terminal")
    ]
    earliest = timing["begin_before_monotonic_ns"] + min(offsets)
    latest = timing["begin_after_monotonic_ns"] + max(offsets)
    estimate = (earliest + latest) // 2
    if (
        latest < earliest
        or latest - earliest > 2_000_000_000
        or max(offsets) - min(offsets) > 2_000_000_000
        or any(
            timing[name] != value
            for name, value in (
                ("first_sample_earliest_utc_ns", earliest),
                ("first_sample_latest_utc_ns", latest),
                ("first_sample_estimate_utc_ns", estimate),
            )
        )
    ):
        raise ValueError("UTC authority is inconsistent with its raw host bracket")
    fs = document["sample_rate_hz"]
    probe_ms = document["probe_ms"]
    origin = timing["session_start_device_sample_counter"]
    if (
        not np.isfinite(fs)
        or fs <= 0
        or fs != timing["sample_rate_hz"]
        or not np.isfinite(probe_ms)
        or probe_ms <= 0
        or origin < 0
    ):
        raise ValueError("invalid device rate, probe duration or counter origin")
    receivers = sorted({p["receiver_id"] for p in document["probes"]})
    support = {rx: [] for rx in receivers}
    rows = []
    for probe in document["probes"]:
        offset = probe["probe_start_ms"] * fs / 1000
        if (
            not np.isfinite(offset)
            or offset < 0
            or abs(offset - round(offset)) > 1e-6
            or probe["valid_start_counter"] < origin
        ):
            raise ValueError("invalid within-visit probe offset or counter")
        start = probe["valid_start_counter"] + round(offset)
        end = start + round(probe_ms * fs / 1000)
        support[probe["receiver_id"]].append((start, end))
        rf = probe["actual_rf_hz"]
        if not np.isfinite(rf) or rf <= 0 or probe["channel"] not in range(1, 9):
            raise ValueError("invalid actual RF or channel")
        candidates = probe["candidates"]
        if any(
            not np.all(np.isfinite([c["fractional_margin"], c["fractional_tracking_cfo_hz"]]))
            for c in candidates
        ):
            raise ValueError("nonfinite fractional candidate")
        eligible = [c for c in candidates if c["passed_fractional_margin_gate"] is True]
        if not eligible:
            continue
        candidate = max(eligible, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))
        identity = json.dumps(
            [
                document["session_id"],
                document["input_manifest_sha256"],
                probe["receiver_id"],
                start,
                end,
            ],
            separators=(",", ":"),
        )
        rows.append(
            dict(
                observation_id="sha256:" + hashlib.sha256(identity.encode()).hexdigest(),
                receiver=receivers.index(probe["receiver_id"]) + 1,
                native_receiver_id=probe["receiver_id"],
                channel=probe["channel"],
                edge=probe["edge"],
                time_s=(start - origin) / fs + probe_ms / 2000,
                measured_cfo_hz=candidate["fractional_tracking_cfo_hz"],
                actual_rf_hz=rf,
                fractional_margin=candidate["fractional_margin"],
                visit_index=probe["visit_index"],
                probe_index=probe["probe_index"],
                valid_start_counter=start,
            )
        )
    for intervals in support.values():
        intervals.sort()
        if any(b[0] < a[1] for a, b in zip(intervals, intervals[1:], strict=False)):
            raise ValueError("overlapping or duplicate physical probe support")
    if len({r["observation_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate observation identity")
    rows.sort(key=lambda r: (r["receiver"], r["channel"], r["actual_rf_hz"], r["time_s"]))
    metadata = dict(
        anchor_utc_ns=estimate,
        causal_cutoff_utc_ns=earliest,
        utc_half_width_s=(latest - earliest) / 2e9,
        observation_time_authority="device counter plus within-visit probe offset; midpoint",
        receiver_factors=len(document["probes"]),
        winning_factors=len(rows),
        observation_policy="one maximum-margin gate-passing fractional peak per probe",
        observations_withheld=0,
        sample_rate_hz=fs,
        duration_s=max((b for spans in support.values() for _, b in spans), default=origin) / fs
        - origin / fs,
    )
    return rows, metadata
