"""Compute optimistic compute and CI16 bounds from sealed survey delivery clocks."""

import argparse
import json
from collections import defaultdict, deque
from hashlib import sha256
from pathlib import Path

from .full_v5_check import REPO

SECOND_NS = 10**9
EVIDENCE = REPO / "reports/2026_11_18_pipeline_eval/evidence"


def _peak_in_second(clocks):
    recent = deque()
    peak = 0
    for clock in clocks:
        while recent and clock - recent[0] >= SECOND_NS:
            recent.popleft()
        recent.append(clock)
        peak = max(peak, len(recent))
    return peak


def budget(document):
    """Use one call per complete dual-RX visit and a two-core CPU ceiling."""
    source, provenance = document["source"], document["provenance"]
    rate, window_ms = source["sample_rate_hz"], source["probe_ms"]
    if (rate, window_ms) != (10_000_000, 20):
        raise ValueError("expected native 10 MS/s, 20 ms acquisition")
    if not source["qualified"] or provenance["skipped_fast_score"] != 0:
        raise ValueError("expected attested capture with no score-gated exclusions")

    clocks = [row["monotonic_ns"] for row in document["delivery_clocks"]]
    count = provenance["window_count"]
    if (
        len(clocks) != count
        or count < 2
        or any(type(value) is not int or value < 0 for value in clocks)
        or any(current <= previous for previous, current in zip(clocks, clocks[1:], strict=False))
    ):
        raise ValueError("expected an increasing delivery clock for every scheduled visit")

    receivers = defaultdict(set)
    for probe in source["probes"]:
        visit, receiver = probe["visit_index"], probe["receiver_id"]
        if type(visit) is not int or type(receiver) is not int or receiver in receivers[visit]:
            raise ValueError("expected unique receiver probes per visit")
        receivers[visit].add(receiver)
    if any(paired != {0, 1} for paired in receivers.values()):
        raise ValueError("expected two receiver probes per eligible visit")
    exclusions = [row["visit"] for row in provenance["excluded_windows"]]
    excluded = set(exclusions)
    if (
        any(type(visit) is not int for visit in exclusions)
        or len(excluded) != len(exclusions)
        or len(excluded) != provenance["invalid_capture"]
        or len(receivers) != provenance["processed_windows"]
        or receivers.keys() & excluded
        or receivers.keys() | excluded != set(range(count))
        or not receivers
    ):
        raise ValueError("eligible probes and capture exclusions must cover the recorded visits")

    visit_times = [clocks[i] for i in sorted(receivers)]
    span_s = (clocks[-1] - clocks[0]) / SECOND_NS
    eligible = len(visit_times)
    bytes_per_visit = rate * window_ms // 1000 * 2 * 4
    return dict(
        first_delivery_monotonic_ns=clocks[0],
        last_delivery_monotonic_ns=clocks[-1],
        delivery_span_s=span_s,
        scheduled_visits=count,
        eligible_dual_rx_visits=eligible,
        excluded_invalid_visits=len(excluded),
        scheduled_visits_per_s=count / span_s,
        eligible_visits_per_s=eligible / span_s,
        max_scheduled_arrivals_in_rolling_second=_peak_in_second(clocks),
        max_eligible_arrivals_in_rolling_second=_peak_in_second(visit_times),
        bytes_per_complete_ci16_visit=bytes_per_visit,
        ci16_bytes_per_s_if_all_scheduled_valid=count * bytes_per_visit / span_s,
        eligible_ci16_bytes=eligible * bytes_per_visit,
        eligible_ci16_bytes_per_s=eligible * bytes_per_visit / span_s,
        unbroken_dual_rx_ci16_bytes_per_s=rate * 2 * 4,
        single_serial_lane_cpu_ms_per_visit_ceiling=1000 * span_s / eligible,
        two_core_cpu_ms_per_visit_ceiling=2000 * span_s / eligible,
    )


def archived_budgets():
    """Bind full arrival inventories and verify their timestamp endpoints."""
    cases = json.loads((EVIDENCE / "whole-recording-time.json").read_bytes())
    for case in cases:
        ident = case["case"]
        binding = json.loads((EVIDENCE / f"full-iq/{ident}/raw-and-v5-bindings.json").read_bytes())
        path = Path(binding["native_path"])
        raw = path.read_bytes()
        digest = sha256(raw).hexdigest()
        if digest != case["native_sha256"] or digest != binding["native_sha256"]:
            raise ValueError(f"{ident} arrival archive SHA-256 differs from saved receipts")
        document = json.loads(raw)
        if document["source"]["session_id"] != binding["source_session_id"]:
            raise ValueError(f"{ident} arrival archive belongs to another session")
        measured = budget(document)
        if (
            measured["scheduled_visits"] != case["recorded_window_clocks"]
            or measured["first_delivery_monotonic_ns"] != case["first_delivery_monotonic_ns"]
            or measured["last_delivery_monotonic_ns"] != case["last_delivery_monotonic_ns"]
        ):
            raise ValueError(f"{ident} arrival archive disagrees with the clock-span receipt")
        yield dict(case=ident, delivery_archive_sha256=digest, **measured)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(list(archived_budgets()), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
