#!/usr/bin/env python3
"""Validate the fresh standard-server full-scan result and emit its qualification."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


SESSION_ID = "scan-fw-f363c7f29141d0b1"
MANIFEST_SHA256 = (
    "sha256:b74c950fb172433dab804ddd14b46a3f4c6c1d2e85a09855b0bfdff5da78e015"
)
NULLABLE_FRACTIONAL_FIELDS = {
    "fractional_control_score",
    "fractional_exact_score",
    "fractional_margin",
    "fractional_offset_samples",
    "fractional_residual_cfo_hz",
    "fractional_tracking_cfo_hz",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    directory = args.directory.resolve()
    summary = json.loads((directory / "summary.json").read_text())
    receipts = sorted((directory / "visits").glob("visit-*.json"))
    inventory = json.loads((directory / "inventory.json").read_text())
    with (directory / "server-visits.jsonl").open() as stream:
        aggregate = [json.loads(line) for line in stream if line.strip()]

    assert summary["status"] == "pass"
    assert summary["fresh_processing"] is True
    assert len(receipts) == len(inventory) == len(aggregate) == 2215
    task_digest = summary["task_digest"]
    raw_hashes: set[str] = set()
    event_hashes: set[str] = set()
    channels: set[int] = set()
    edges: set[str] = set()
    status_counts: dict[str, int] = {}
    candidate_count = 0
    passing_count = 0
    previous_end: int | None = None

    for visit, receipt_path in enumerate(receipts):
        receipt = json.loads(receipt_path.read_text())
        assert receipt == aggregate[visit]
        assert receipt["status"] == "pass"
        assert receipt["visit"] == visit
        assert receipt["task_digest"] == task_digest

        source = receipt["source"]
        event = source["event"]
        geometry = receipt["geometry"]
        assert source["session_id"] == SESSION_ID
        assert source["recording_manifest_sha256"] == MANIFEST_SHA256
        assert source["raw_bytes"] == 2_400_000
        assert len(source["raw_sha256"]) == 64
        assert len(source["recording_event_sha256"]) == 64
        assert source["raw_sha256"] not in raw_hashes
        assert source["recording_event_sha256"] not in event_hashes
        raw_hashes.add(source["raw_sha256"])
        event_hashes.add(source["recording_event_sha256"])

        assert event["visit_index"] == visit
        assert event["event_sequence"] == visit
        assert event["valid_end_counter_exclusive"] - event["valid_start_counter"] == 300_000
        if previous_end is not None:
            assert event["valid_start_counter"] >= previous_end
        previous_end = event["valid_end_counter_exclusive"]
        channels.add(event["target"]["channel"])
        edges.add(event["target"]["edge"])

        assert geometry["sample_rate_hz"] == 2_500_000
        assert geometry["probe_ms"] == 20
        assert geometry["probe_stride_ms"] == 120
        assert geometry["scheduled_probe_count_per_receiver"] == 1
        assert set(receipt["candidates"]) == {"0", "1"}

        expected_inventory = {
            "channel": event["target"]["channel"],
            "edge": event["target"]["edge"],
            "raw_bytes": source["raw_bytes"],
            "raw_sha256": source["raw_sha256"],
            "recording_event_sha256": source["recording_event_sha256"],
            "valid_end_counter_exclusive": event["valid_end_counter_exclusive"],
            "valid_start_counter": event["valid_start_counter"],
            "valid_start_utc_estimate_ns": source["valid_start_utc_estimate_ns"],
            "visit": visit,
        }
        assert inventory[visit] == expected_inventory

        for receiver_text, candidates in receipt["candidates"].items():
            assert len(candidates) == 8
            receiver = int(receiver_text)
            for rank, candidate in enumerate(candidates):
                assert candidate["receiver_id"] == receiver
                assert candidate["probe_index"] == 0
                assert candidate["rank"] == rank
                for key, value in candidate.items():
                    if isinstance(value, float):
                        assert math.isfinite(value), (visit, receiver, rank, key)
                    if value is None:
                        assert key in NULLABLE_FRACTIONAL_FIELDS
                status = candidate["fractional_status"]
                status_counts[status] = status_counts.get(status, 0) + 1
                if status == "complete":
                    assert all(candidate[key] is not None for key in NULLABLE_FRACTIONAL_FIELDS)
                    assert candidate["passed_fractional_margin_gate"] == (
                        candidate["fractional_margin"] >= 0.025
                    )
                else:
                    assert status == "unbracketed"
                    assert all(candidate[key] is None for key in NULLABLE_FRACTIONAL_FIELDS)
                    assert candidate["passed_fractional_margin_gate"] is False
                candidate_count += 1
                passing_count += int(candidate["passed_fractional_margin_gate"])

    assert channels == {1, 2, 3, 4}
    assert edges == {"lower"}
    assert candidate_count == summary["candidates"] == 35_440
    assert passing_count == summary["passing_candidates"] == 10_066
    assert summary["receiver_windows"] == 4_430

    qualification = {
        "schema": "org.leo.standard-server-full-scan-qualification/v1",
        "status": "pass",
        "session_id": SESSION_ID,
        "recording_manifest_sha256": MANIFEST_SHA256,
        "task_digest": task_digest,
        "visits": len(receipts),
        "receiver_windows": 2 * len(receipts),
        "candidates": candidate_count,
        "passing_candidates": passing_count,
        "fractional_status_counts": status_counts,
        "unique_raw_sha256": len(raw_hashes),
        "unique_recording_event_sha256": len(event_hashes),
        "channels": sorted(channels),
        "edges": sorted(edges),
        "schedule": summary["dependencies"]["schedule"],
        "fresh_processing": True,
        "source_receipts_match_jsonl": True,
        "inventory_matches_source_receipts": True,
        "all_candidate_numbers_finite": True,
        "all_gate_decisions_recomputed_equal": True,
        "timing_s": summary["timing_s"],
        "dependencies": summary["dependencies"],
    }
    args.output.write_text(json.dumps(qualification, indent=2, sort_keys=True) + "\n")
    print(json.dumps(qualification, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
