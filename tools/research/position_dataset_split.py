#!/usr/bin/env python3
"""Freeze leakage-aware position train/validation/test recording partitions."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

from leo.storage.adaptive_hop import AdaptiveHopIqStore

TEST_START = datetime(2026, 9, 23, 15, 15, tzinfo=UTC)
AS_OF = datetime(2026, 9, 23, 15, 45, tzinfo=UTC)
EMBARGO_MINUTES = 120
TIER_COUNTS = {"single_300s": 1, "about_1h": 6, "about_3h": 18, "about_8h": 48}


def _digest_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _digest_value(value) -> str:
    return _digest_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _capture_metadata(session_id: str) -> dict:
    with urlopen(
        f"http://127.0.0.1:8090/api/v3/scanner/adaptive-sessions/{session_id}", timeout=60
    ) as response:
        capture = json.load(response)["capture"]
    return {
        "session_id": session_id,
        "captured_at": capture["captured_at"],
        "nominal_duration_seconds": capture["nominal_duration_seconds"],
        "sample_rate_hz": capture["sample_rate_hz"],
        "edge": capture.get("selected_edge"),
    }


def _windows(rows: list[dict], count: int, tier: str) -> list[dict]:
    windows = []
    for begin in range(0, len(rows) - count + 1, count):
        group = rows[begin : begin + count]
        start = _time(group[0]["captured_at"])
        final_start = _time(group[-1]["captured_at"])
        summed = sum(int(row["nominal_duration_seconds"]) for row in group)
        elapsed = (final_start - start).total_seconds() + int(group[-1]["nominal_duration_seconds"])
        windows.append(
            {
                "window_id": f"{tier}_{len(windows) + 1:03d}",
                "session_ids": [row["session_id"] for row in group],
                "scan_count": count,
                "start": group[0]["captured_at"],
                "last_start": group[-1]["captured_at"],
                "summed_nominal_capture_seconds": summed,
                "elapsed_span_seconds": elapsed,
                "continuous_iq": False,
                "observation_and_mask_authority_digest": _digest_value(
                    [
                        {"session_id": row["session_id"], "evidence_digest": row["evidence_digest"]}
                        for row in group
                    ]
                ),
            }
        )
    return windows


def _tier_views(rows: list[dict]) -> dict:
    views = {}
    for tier, count in TIER_COUNTS.items():
        windows = _windows(rows, count, tier)
        views[tier] = {
            "target_scan_count": count,
            "status": "available" if windows else "unavailable",
            "windows": windows,
            "unused_remainder_session_ids": [
                row["session_id"] for row in rows[len(windows) * count :]
            ],
        }
    return views


def _partition_candidate_metadata(rows: list[dict], validation_end: datetime):
    """Partition by capture start; publication timestamps are discovery hints only."""
    effective = max(TEST_START, validation_end + timedelta(minutes=EMBARGO_MINUTES))
    post_cutoff = [row for row in rows if TEST_START <= _time(row["captured_at"]) < AS_OF]
    quarantine = [row for row in post_cutoff if _time(row["captured_at"]) < effective]
    reserve = [row for row in post_cutoff if _time(row["captured_at"]) >= effective]
    return effective, quarantine, reserve


def _validate(document: dict) -> None:
    parts = document["partitions"]
    names = (
        "training",
        "development_validation",
        "embargo_quarantine",
        "test_embargo_quarantine",
        "prospective_test_reserve",
    )
    for name in names:
        ids = parts[name]["session_ids"]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate recording within {name}")
    train, validation, quarantine, test_quarantine, reserve = (
        set(parts[name]["session_ids"]) for name in names
    )
    sets = (train, validation, quarantine, test_quarantine, reserve)
    if any(a.intersection(b) for index, a in enumerate(sets) for b in sets[index + 1 :]):
        raise ValueError("recording partitions overlap")
    train_end = _time(parts["training"]["latest_nominal_capture_end"])
    validation_start = _time(parts["development_validation"]["earliest_capture_start"])
    if validation_start - train_end < timedelta(minutes=document["embargo"]["primary_minutes"]):
        raise ValueError("primary temporal embargo is violated")
    exposed = set(document["provenance"]["exposed_session_ids"])
    if reserve.intersection(exposed):
        raise ValueError("exposed recordings entered prospective reserve")
    if reserve:
        validation_end = _time(parts["development_validation"]["latest_nominal_capture_end"])
        reserve_start = min(
            _time(row["captured_at"]) for row in parts["prospective_test_reserve"]["metadata"]
        )
        if reserve_start - validation_end < timedelta(
            minutes=document["embargo"]["primary_minutes"]
        ):
            raise ValueError("validation-to-test temporal embargo is violated")
    for name in ("training", "development_validation"):
        authority = set(parts[name]["session_ids"])
        for tier in parts[name]["duration_tiers"].values():
            seen_in_tier: set[str] = set()
            for window in tier["windows"]:
                if not set(window["session_ids"]).issubset(authority):
                    raise ValueError("duration window crosses its recording partition")
                if seen_in_tier.intersection(window["session_ids"]):
                    raise ValueError("duration windows overlap within a tier")
                seen_in_tier.update(window["session_ids"])
                if window["summed_nominal_capture_seconds"] <= 0:
                    raise ValueError("duration window capture accounting changed")


def load_partition(
    manifest_path: Path, name: str, *, require_available: bool = True
) -> tuple[str, ...]:
    """Load one recording partition only after verifying the frozen manifest."""
    document = json.loads(manifest_path.read_text())
    expected = document.pop("content_digest_without_this_field", None)
    if expected != _digest_value(document):
        raise ValueError("dataset manifest digest mismatch")
    _validate(document)
    if name not in document["partitions"]:
        raise KeyError(name)
    partition = document["partitions"][name]
    if require_available and str(partition["status"]).startswith("unavailable"):
        raise ValueError(f"partition {name} is unavailable")
    return tuple(partition["session_ids"])


def build(args) -> dict:
    original_raw = args.original_selection.read_bytes()
    original = json.loads(original_raw)
    original_scans_raw = args.original_scans.read_bytes()
    original_scans = json.loads(original_scans_raw)
    day_raw = args.day_inventory.read_bytes()
    day = json.loads(day_raw)
    original_evidence_raw = args.original_evidence_audit.read_bytes()
    original_evidence = json.loads(original_evidence_raw)
    original_evidence_by_id = {row["session_id"]: row for row in original_evidence["scans"]}
    original_ids = set(original["session_ids"])
    exposed_day = set(day["eligible_session_ids"])
    if original_ids.intersection(exposed_day):
        raise ValueError("source inventories overlap")

    all_exposed_ids = list(original["session_ids"]) + list(day["eligible_session_ids"])
    capture_by_id = {session_id: _capture_metadata(session_id) for session_id in all_exposed_ids}
    original_by_id = {row["session_id"]: row for row in original_scans}
    training = []
    for session_id in original["session_ids"]:
        row = original_by_id[session_id]
        capture = capture_by_id[session_id]
        if capture["captured_at"] != row["captured_at"]:
            raise ValueError("original capture metadata changed")
        training.append(
            {
                **capture,
                "source": "original16-exposed",
                "evidence_digest": original_evidence_by_id[session_id]["evidence_sha256"],
            }
        )
    day_rows = {
        row["session_id"]: {
            **capture_by_id[row["session_id"]],
            "source": "day116-exposed",
            "evidence_digest": row["evidence_digest"],
        }
        for row in day["scans"]
        if row["state"] == "eligible"
    }
    train_day_ids = {
        session_id for group in day["groups"][:3] for session_id in group["session_ids"]
    }
    training.extend(day_rows[session_id] for session_id in train_day_ids)
    training.sort(key=lambda row: (row["captured_at"], row["session_id"]))
    train_end = max(
        _time(row["captured_at"]) + timedelta(seconds=int(row["nominal_duration_seconds"]))
        for row in training
    )
    validation_boundary = train_end + timedelta(minutes=EMBARGO_MINUTES)
    remaining = [day_rows[sid] for sid in day["eligible_session_ids"] if sid not in train_day_ids]
    quarantine = sorted(
        [row for row in remaining if _time(row["captured_at"]) < validation_boundary],
        key=lambda row: row["captured_at"],
    )
    validation = sorted(
        [row for row in remaining if _time(row["captured_at"]) >= validation_boundary],
        key=lambda row: row["captured_at"],
    )

    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    try:
        publications = store.publication_index()
    finally:
        store.close()
    start_ns, end_ns = int(TEST_START.timestamp() * 1e9), int(AS_OF.timestamp() * 1e9)
    candidate_ids = sorted(
        {sid for stamp, sid in publications if start_ns - 600_000_000_000 <= stamp < end_ns}
    )
    candidate_metadata = sorted(
        (_capture_metadata(sid) for sid in candidate_ids),
        key=lambda row: (row["captured_at"], row["session_id"]),
    )
    validation_end = max(
        _time(row["captured_at"]) + timedelta(seconds=int(row["nominal_duration_seconds"]))
        for row in validation
    )
    effective_test_start, test_quarantine, prospective = _partition_candidate_metadata(
        candidate_metadata, validation_end
    )
    before_test_cutoff = [
        row for row in candidate_metadata if _time(row["captured_at"]) < TEST_START
    ]
    prospective_ids = [row["session_id"] for row in prospective]
    exposed = original_ids | exposed_day
    if exposed.intersection(prospective_ids):
        raise ValueError("prospective reserve contains an exposed recording")

    sensitivity = {}
    for minutes in (30, 90, 120, 180):
        boundary = train_end + timedelta(minutes=minutes)
        kept = [row for row in remaining if _time(row["captured_at"]) >= boundary]
        sensitivity[str(minutes)] = {
            "validation_session_count": len(kept),
            "first_validation_capture": kept[0]["captured_at"] if kept else None,
            "complete_16_scan_blocks": len(kept) // 16,
        }

    document = {
        "schema": "position-recording-split/v1",
        "created_without_position_outcome_or_reference_error": True,
        "split_policy": (
            "whole exposed chronological blocks; original16 plus day blocks01-03 training; "
            "120-minute embargo; later exposed recordings retrospective development-validation; "
            "post-cutoff metadata-only recordings quarantined for prospective test"
        ),
        "within_track_partition": (
            "retain each published track_evidence.training_mask exactly; never repartition "
            "observations"
        ),
        "embargo": {
            "primary_minutes": EMBARGO_MINUTES,
            "rationale": (
                "conservative development boundary spanning more than one nominal LEO orbit; "
                "does not guarantee independence or prevent the same satellite recurring"
            ),
            "sensitivity": sensitivity,
        },
        "partitions": {
            "training": {
                "status": "exposed-development",
                "session_ids": [row["session_id"] for row in training],
                "session_count": len(training),
                "earliest_capture_start": training[0]["captured_at"],
                "latest_capture_start": training[-1]["captured_at"],
                "latest_nominal_capture_end": train_end.isoformat(),
                "duration_tiers": _tier_views(training),
            },
            "development_validation": {
                "status": "retrospective-exposed; suitable for model comparison, not final claims",
                "session_ids": [row["session_id"] for row in validation],
                "session_count": len(validation),
                "earliest_capture_start": validation[0]["captured_at"],
                "latest_capture_start": validation[-1]["captured_at"],
                "latest_nominal_capture_end": validation_end.isoformat(),
                "duration_tiers": _tier_views(validation),
            },
            "embargo_quarantine": {
                "status": "excluded from train and validation",
                "session_ids": [row["session_id"] for row in quarantine],
                "session_count": len(quarantine),
                "reason": "capture start lies inside primary post-training embargo",
            },
            "test_embargo_quarantine": {
                "status": "metadata only; excluded from prospective test",
                "session_ids": [row["session_id"] for row in test_quarantine],
                "session_count": len(test_quarantine),
                "reason": (
                    "capture start lies after exposure cutoff but inside validation-to-test embargo"
                ),
                "metadata": test_quarantine,
            },
            "prospective_test_reserve": {
                "status": (
                    "unavailable: metadata-only candidates, eligibility and outcomes unopened"
                ),
                "session_ids": [row["session_id"] for row in prospective],
                "session_count": len(prospective),
                "readiness_milestone_eligible_recordings": 48,
                "required_for_preliminary_test_freeze": 144,
                "required_nonoverlapping_48_scan_windows": 3,
                "minimum_additional_candidates_needed": max(0, 144 - len(prospective)),
                "window_start": TEST_START.isoformat(),
                "effective_test_start_after_embargo": effective_test_start.isoformat(),
                "snapshot_inventory_as_of_exclusive": AS_OF.isoformat(),
                "future_rule": (
                    "continue with the first chronological normally acquired recordings at or "
                    "after "
                    "effective_test_start_after_embargo; 48 eligible recordings is readiness only; "
                    "freeze at least 144 eligible IDs for three nonoverlapping 48-scan windows "
                    "before opening outcomes; no end "
                    "time and no new collection are authorized by this manifest"
                ),
                "metadata": prospective,
                "duration_tiers": {
                    name: {"status": "unavailable", "windows": []} for name in TIER_COUNTS
                },
            },
        },
        "duration_tier_policy": {
            "scan_counts": TIER_COUNTS,
            "window_membership": (
                "nonoverlapping within a tier; tiers are reusable views, not independent folds"
            ),
            "duration_reporting": (
                "sum API-declared nominal capture durations separately from actual elapsed span "
                "between first capture start and nominal end of the last capture"
            ),
        },
        "provenance": {
            "original_selection_digest": _digest_bytes(original_raw),
            "original_scans_digest": _digest_bytes(original_scans_raw),
            "day_inventory_digest": _digest_bytes(day_raw),
            "original_evidence_audit_digest": _digest_bytes(original_evidence_raw),
            "exposed_session_ids": sorted(exposed),
            "exposed_session_digest": _digest_value(sorted(exposed)),
            "prospective_metadata_digest": _digest_value(prospective),
            "metadata_candidates_examined_digest": _digest_value(candidate_metadata),
            "metadata_excluded_before_test_cutoff": before_test_cutoff,
            "position_diagnostics_opened_for_prospective_reserve": False,
            "split_tool_digest": _digest_bytes(Path(__file__).read_bytes()),
        },
    }
    _validate(document)
    document["content_digest_without_this_field"] = _digest_value(document)
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-selection", type=Path, required=True)
    parser.add_argument("--original-scans", type=Path, required=True)
    parser.add_argument("--day-inventory", type=Path, required=True)
    parser.add_argument("--original-evidence-audit", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("dataset output must be fresh")
    document = build(args)
    args.output.mkdir(parents=True)
    (args.output / "manifest.json").write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {name: row["session_count"] for name, row in document["partitions"].items()}, indent=2
        )
    )


if __name__ == "__main__":
    main()
