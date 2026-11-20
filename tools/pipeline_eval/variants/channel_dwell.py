"""Retain a causal original-detector prefix with concentrated RF dwell."""

from collections import Counter
from hashlib import sha256

from . import capture_bursts

MODES = ("dwell96", "delayed96", "dwell416", "delayed416")
BUDGET = {mode: 96 if mode.endswith("96") else 416 for mode in MODES}
DELAY = 384


def primary_channel(recording):
    return sha256(f"channel-dwell-rf-v1:{recording}".encode()).digest()[0] % 8 + 1


def schedule(metadata, primary, mode):
    if primary not in range(1, 9) or mode not in MODES:
        raise ValueError("unknown RF lane or dwell schedule")
    small = BUDGET[mode] == 96
    lanes = (primary,) if small else (primary, (primary + 3) % 8 + 1)
    start = DELAY if mode.startswith("delayed") else 0
    stride = 2 if small else 1
    count = BUDGET[mode] // len(lanes)
    slots = range(start, start + stride * count, stride)
    ordinals, selected = Counter(), []
    for visit, channel in metadata:
        if channel in lanes and ordinals[channel] in slots:
            selected.append(visit)
        ordinals[channel] += 1
    if len(selected) != BUDGET[mode] or len(set(selected)) != len(selected):
        raise ValueError("recording cannot spend the exact visit budget")
    return selected


def prefix(document, selected, identity):
    stop = max(selected)
    src = document["source"]
    delivered = document["delivery_clocks"][: stop + 1]
    kept = [p for p in src["probes"] if p["visit_index"] <= stop]
    end = max(p["valid_start_counter"] for p in kept if p["visit_index"] == stop)
    samples = round(src["sample_rate_hz"] * src["probe_ms"] / 1000)
    if any(p["valid_start_counter"] > end for p in kept):
        raise ValueError("a retained clock starts after the frozen sample frontier")
    if end + samples > document["last_sample_counter"]:
        raise ValueError("frontier exceeds the original capture")
    provenance = document["provenance"]
    exclusions = [r for r in provenance["excluded_windows"] if r["visit"] <= stop]
    skipped = sum("fast score" in r["reason"].lower() for r in exclusions)
    derived = dict(
        document,
        delivery_clocks=delivered,
        last_sample_counter=end + samples,
        source=dict(src, probes=kept, capture_end_utc_ns=None),
        provenance=dict(
            provenance,
            excluded_windows=exclusions,
            window_count=len(delivered),
            invalid_capture=len(exclusions) - skipped,
            skipped_fast_score=skipped,
            processed_windows=len(kept) // 2,
            scope="Recorded causal RF dwell prefix",
        ),
    )
    return capture_bursts.select_document(derived, selected, identity)
