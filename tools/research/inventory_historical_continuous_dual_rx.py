"""Metadata-only inventory of post-continuity-fix dual-RX recordings."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from leo.storage import RecordingStore

ROOT = Path(__file__).resolve().parents[2]
STORE = Path("/srv/bulk/leo")
OUTPUT = ROOT / "reports/figures/2026_09_23_historical_continuous_dual_rx_inventory/inventory.json"
CUTOFF_UTC_NS = int(datetime(2026, 8, 24, tzinfo=UTC).timestamp()) * 1_000_000_000
SELECTED = {
    "cap-20260825T031521-ec8adc0e9426": dict(overlap_s=11.0, observations=1365, pilots=45),
    "cap-20260825T065355-ba3e4fb8857b": dict(overlap_s=14.863927893, observations=1806, pilots=51),
    "cap-20260825T105915-2770b84587cc": dict(
        overlap_s=7.05,
        observations=704,
        jointly_accepted_20ms=650,
        pilots=64,
        evidence="reports/2026_09_16_dual_rx_pilot_phase.md",
    ),
}


def stream_row(bundle, stream):
    d = stream.model_dump()
    settings = d.get("applied_settings") or d.get("settings") or {}
    fs = settings.get("sample_rate_hz")
    receivers = list(settings.get("receiver_ids") or ())
    count = (
        d.get("logical_sample_count") or d.get("sample_count") or d.get("requested_sample_count")
    )
    if not fs or not count:
        return None
    continuity = d.get("continuity") or {}
    return dict(
        session_id=bundle.session_id,
        stream_id=stream.stream_id,
        sample_rate_hz=fs,
        bandwidth_hz=settings.get("bandwidth_hz"),
        receiver_ids=receivers,
        duration_s=count / fs,
        state=str(d.get("state")),
        logical_sample_count=count,
        observed_sample_count=d.get("observed_sample_count", count),
        gap_count=continuity.get("gap_count"),
        missing_sample_count=continuity.get("missing_sample_count"),
        overflow_count=continuity.get("overflow_count"),
        refill_count=continuity.get("refill_count"),
        manifest_digest=bundle.manifest_sha256,
    )


def timeline_is_contiguous(blocks):
    return (
        bool(blocks)
        and blocks[0].missing_samples_before == 0
        and not blocks[0].overflow_observed
        and all(
            b.device_sample_counter == a.device_sample_counter + a.sample_count
            and b.source_sequence == a.source_sequence + 1
            and b.missing_samples_before == 0
            and not b.overflow_observed
            for a, b in zip(blocks, blocks[1:], strict=False)
        )
    )


def verify_timeline(store, session_id):
    bundle = store.inspect(session_id)
    rows = []
    for stream in bundle.manifest.streams:
        row = stream_row(bundle, stream)
        if row is None or len(row["receiver_ids"]) < 2:
            continue
        blocks = list(store.reader(bundle, stream.stream_id, verify=True).iter_timeline_metadata())
        contiguous = timeline_is_contiguous(blocks)
        row.update(
            timeline_refills=len(blocks),
            timeline_contiguous=contiguous,
            first_device_sample_counter=blocks[0].device_sample_counter,
            last_device_sample_counter_inclusive=blocks[-1].device_sample_counter
            + blocks[-1].sample_count
            - 1,
        )
        rows.append(row)
    return rows


def main():
    store = RecordingStore.open_read_only(STORE)
    try:
        reconciliation = store.reconcile()
        inventory = []
        for bundle in reconciliation.committed:
            if bundle.manifest.created_utc_ns < CUTOFF_UTC_NS:
                continue
            for stream in bundle.manifest.streams:
                row = stream_row(bundle, stream)
                if row and len(row["receiver_ids"]) >= 2 and row["duration_s"] >= 5:
                    inventory.append(row)
        rates = Counter(r["sample_rate_hz"] for r in inventory)
        continuous = Counter(
            r["sample_rate_hz"]
            for r in inventory
            if r["gap_count"] == r["missing_sample_count"] == r["overflow_count"] == 0
        )
        chosen = []
        for session, evidence in SELECTED.items():
            for row in verify_timeline(store, session):
                chosen.append(row | evidence)
        output = dict(
            schema="historical-continuous-dual-rx-inventory/v1",
            cutoff="2026-08-24T00:00:00Z",
            recording_store_committed=len(reconciliation.committed),
            inspection_issues=len(reconciliation.issues),
            dual_rx_at_least_5s_count=len(inventory),
            counts_by_sample_rate_hz={str(k): v for k, v in sorted(rates.items())},
            continuous_counts_by_sample_rate_hz={str(k): v for k, v in sorted(continuous.items())},
            no_long_10_or_15_msps_recording_store_stream=(
                rates[10_000_000] == rates[15_000_000] == 0
            ),
            selected=chosen,
            alternate=dict(
                session_id="cap-20260825T115401-774be9e8b225",
                overlap_s=11.825,
                observations=1920,
                pilots=47,
                reason="longer overlap, but cross-band source pairing adds phase-response nuisance",
            ),
            glrt_source="reports/2026_08_25_post_refill_24h_retrospective/capture-analysis-inventory.csv",
        )
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(output, indent=2, default=str) + "\n")
    finally:
        store.close()


if __name__ == "__main__":
    main()
