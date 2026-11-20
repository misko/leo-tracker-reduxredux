"""Extend the authenticated physical single-lane detector with partner-on-miss routing."""

import json
import sys
from unittest.mock import patch

from ..variants import second_on_miss
from ..variants.single_chain import analyze_native
from . import one_lane_whole_raw as existing
from .full_v5_check import _from_native

TRACE = "second-on-miss-lane-v1: "
STEREO = existing.stereo_slots


def detect(native, samples, receiver_id, *, include_timings=False):
    """Return the complete physical rows and whether a second native call ran."""
    primary = analyze_native(native, samples, receiver_id, include_timings=include_timings)
    (row,) = primary["rows"]
    factors = [
        replacement
        for rank, candidate in enumerate(row["candidates"])
        if (replacement := _from_native(rank, candidate)) is not None
    ]
    needed = second_on_miss.needs_partner({"candidates": factors})
    if needed:
        partner = analyze_native(native, samples, 1 - receiver_id, include_timings=include_timings)
        rows = sorted(primary["rows"] + partner["rows"], key=lambda r: r["receiver_id"])
        outcome = dict(primary, rows=rows)
        if include_timings:
            outcome["detector_cpu_ms"] += partner["detector_cpu_ms"]
    else:
        outcome = STEREO(primary, receiver_id)
    return dict(outcome, receiver_count=2), needed


def run():
    from leo.storage import fast_scan

    source_windows = fast_scan.FastSegmentSource.windows
    current = None
    traces = []

    def visit_source(source):
        nonlocal current
        for window in source_windows(source):
            current = int(window.acquisition["global_visit"])
            yield window
            current = None

    def observe(native, samples, receiver_id, *, include_timings=False):
        if current is None:
            raise ValueError("receiver dispatch has no corresponding authenticated waveform")
        output, needed = detect(native, samples, receiver_id, include_timings=include_timings)
        traces.append([current, receiver_id, needed])
        return output

    def check_slots(data, _primary):
        if [row["receiver_id"] for row in data["rows"]] != [0, 1]:
            raise ValueError("actual paired observations lost a physical slot")
        return data

    with (
        patch.object(fast_scan.FastSegmentSource, "windows", visit_source),
        patch.multiple(existing, analyze_native=observe, stereo_slots=check_slots),
    ):
        existing.run()
    print(TRACE + json.dumps(traces, separators=(",", ":")), file=sys.stderr, flush=True)


if __name__ == "__main__":
    run()
