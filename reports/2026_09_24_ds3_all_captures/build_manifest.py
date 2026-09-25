#!/usr/bin/env python3
"""Read-only DS3 admission inventory through the recorded 2026-09-24 audit cutoff."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RAW_ROOT = Path("/srv/bulk/leo/scanner-adaptive-recordings")
DS2 = HERE.parent / "2026_09_24_ds2_sep24_rerun_22/manifest.json"
AUDIT_UTC = datetime(2026, 9, 24, 22, 36, 58, tzinfo=UTC)
# The audit's last closed scan began at 22:20:02.797011Z.  The next scan was
# intentionally outside this frozen capture membership even though the audit
# itself happened later.
CAPTURE_CUTOFF = datetime(2026, 9, 24, 22, 20, 2, 797011, tzinfo=UTC)


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def iso(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1_000_000_000, UTC).isoformat().replace("+00:00", "Z")


def discover(raw_root: Path, cutoff: datetime) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(raw_root.glob("scan-fw-*/manifest.json")):
        envelope = load(path)
        raw = envelope.get("manifest")
        if not isinstance(raw, dict):
            continue
        timing, receipt = raw.get("timing"), raw.get("receipt")
        if not isinstance(timing, dict) or not isinstance(receipt, dict):
            continue
        start_ns = timing.get("first_sample_estimate_utc_ns")
        if not isinstance(start_ns, int):
            continue
        started = datetime.fromtimestamp(start_ns / 1_000_000_000, UTC)
        if started.date().isoformat() != "2026-09-24" or started > cutoff:
            continue
        terminal = receipt.get("terminal") or {}
        qualified = timing.get("qualified") is True
        complete = terminal.get("state") == "completed"
        admissible = qualified and complete
        events = receipt.get("events") if isinstance(receipt.get("events"), list) else []
        dwells = sorted(
            {
                round(
                    1000
                    * (event["valid_end_counter_exclusive"] - event["valid_start_counter"])
                    / timing["sample_rate_hz"],
                    6,
                )
                for event in events
                if isinstance(event, dict)
                and "valid_end_counter_exclusive" in event
                and "valid_start_counter" in event
            }
        )
        rows.append(
            {
                "session_id": raw.get("session_id"),
                "capture_start_utc": iso(start_ns),
                "recording_manifest_path": str(path),
                "recording_manifest_digest": envelope.get("sha256"),
                "capture_schema_version": raw.get("schema_version"),
                "receipt_schema_version": receipt.get("schema_version"),
                "timing_schema_version": timing.get("schema_version"),
                "radio_id": receipt.get("radio_id"),
                "sample_rate_hz": timing.get("sample_rate_hz"),
                "sample_format": raw.get("sample_format"),
                "sample_layout": raw.get("sample_layout"),
                "total_sample_count": raw.get("total_sample_count"),
                "complete_visit_count": receipt.get("complete_visit_count"),
                "dwell_ms_observed": dwells,
                "recording_complete": complete,
                "qualified_utc_timing": qualified,
                "source_span_attested": receipt.get("source_span_attested") is True,
                "device_dropped_events": receipt.get("device_dropped_events"),
                "admission_status": "included" if admissible else "excluded",
                "exclusion_reason": None
                if admissible
                else "capture_not_both_qualified_utc_and_terminal_completed",
            }
        )
    return sorted(rows, key=lambda row: (str(row["capture_start_utc"]), str(row["session_id"])))


def assemble(raw_root: Path, ds2: dict[str, Any]) -> dict[str, Any]:
    captures = discover(raw_root, CAPTURE_CUTOFF)
    if len(captures) != 56:
        raise ValueError(f"expected 56 date/cutoff captures, found {len(captures)}")
    ds2_ids = {row["session_id"] for row in ds2.get("sessions", [])}
    current_ids = {str(row["session_id"]) for row in captures}
    geometry_ids = {
        str(row["session_id"])
        for row in ds2.get("sessions", [])
        if row.get("receiver_geometry", {}).get("eligibility") != "unavailable"
    }
    for row in captures:
        row["ds2_22_member"] = row["session_id"] in ds2_ids
        row["tracking_evidence"] = "sealed_v14_receipt" if row["ds2_22_member"] else "not_in_ds2_22"
        row["geometry_binding"] = (
            "conditional_explicit" if row["session_id"] in geometry_ids else "unavailable"
        )
    included = [row for row in captures if row["admission_status"] == "included"]
    return {
        "schema": "ds3-all-captures-admission/v1",
        "date_utc": "2026-09-24",
        "audit_observed_utc": AUDIT_UTC.isoformat().replace("+00:00", "Z"),
        "capture_cutoff_utc": CAPTURE_CUTOFF.isoformat().replace("+00:00", "Z"),
        "audit_scope": "scan-fw manifests from midnight through the last closed 22:20 UTC "
        "capture, inclusive",
        "source_roots": {"raw_capture_root": str(raw_root), "ds2_22_manifest": str(DS2)},
        "reference_coordinate_present": False,
        "counts": {
            "discovered": len(captures),
            "admitted": len(included),
            "excluded": len(captures) - len(included),
            "ds2_22_members": len(current_ids & ds2_ids),
            "new_since_ds2_22": len(current_ids - ds2_ids),
            "ds2_22_missing_from_cutoff": len(ds2_ids - current_ids),
            "explicit_geometry_bindings": len(geometry_ids & current_ids),
        },
        "captures": captures,
        "exclusions": [row for row in captures if row["admission_status"] == "excluded"],
        "leakage_risks": [
            "Partition by whole session_id: both receivers, visits, and tracklets stay together.",
            "Keep pre-existing DS2 tracking evidence separate from newly admitted raw-only "
            "sessions.",
            "Do not transfer the three explicit geometry bindings to new sessions by radio "
            "identity.",
            "Freeze a seed and session-stratified assignment before fitting or association.",
            "Reference coordinates may be used only by a post-seal evaluator, never by inference.",
        ],
        "deterministic_grouping": {
            "group_key": "session_id",
            "strata": ["radio_id", "sample_rate_hz", "ds2_22_member"],
            "assignment": "sha256(seed + ':' + session_id), sorted within stratum, "
            "whole-session roles",
            "roles": ["train", "development", "postseal_evaluation"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--ds2", type=Path, default=DS2)
    parser.add_argument("--output", type=Path, default=HERE / "manifest.json")
    args = parser.parse_args()
    document = assemble(args.raw_root, load(args.ds2))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical(document))
    sha256 = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(".sha256").write_text(sha256 + "\n")
    print(canonical(document["counts"]), end="")


if __name__ == "__main__":
    main()
