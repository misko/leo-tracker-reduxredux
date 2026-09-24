#!/usr/bin/env python3
"""Build a read-only, cutoff-bounded inventory of current-day adaptive captures.

This is deliberately an inventory, not a model runner.  It reads only the
public adaptive-history and analysis-status endpoints; it never opens IQ or
writes beneath the bulk/QNAP storage roots.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
API = "http://127.0.0.1:8090/api/v3/scanner/adaptive-sessions"
DATE = "2026-09-24"


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=20) as response:  # noqa: S310 - fixed local read-only API
        return json.load(response)


def as_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def history(api: str) -> list[dict[str, Any]]:
    """Read only newest pages through the requested UTC-date boundary."""
    rows: list[dict[str, Any]] = []
    cursor = 0
    while True:
        page = read_json(f"{api}?{urlencode({'cursor': cursor, 'limit': 20})}")
        rows.extend(page["items"])
        next_cursor = page["next_cursor"]
        captured = [row.get("captured_at") for row in page["items"]]
        reached_older_date = any(
            stamp is not None and as_utc(stamp).date().isoformat() < DATE for stamp in captured
        )
        if next_cursor is None or reached_older_date:
            return rows
        cursor = int(next_cursor)


def compact_overview(value: Any) -> dict[str, Any] | None:
    """Preserve only public scalar count-like metrics; never derive a track count."""
    if not isinstance(value, dict):
        return None
    names = {
        key: item
        for key, item in value.items()
        if isinstance(item, (str, int, float, bool)) or item is None
    }
    return names or None


def analysis(api: str, session_id: str) -> dict[str, Any]:
    try:
        value = read_json(f"{api}/{session_id}/analysis")
        overview = compact_overview(value.get("overview"))
        count = None
        source = None
        for key in ("track_count", "qualified_track_count", "candidate_track_count"):
            if isinstance(overview, dict) and isinstance(overview.get(key), int):
                count, source = int(overview[key]), f"overview.{key}"
                break
        return {
            "state": value.get("state"),
            "total_visits": value.get("total_visits"),
            "checkpoint_visits": value.get("checkpoint_visits"),
            "worker_activity": value.get("worker_activity"),
            "receiver_ids": value.get("configuration", {}).get("receiver_ids"),
            "analyzer_id": value.get("configuration", {}).get("analyzer_id"),
            "metrics_manifest_sha256": value.get("metrics_manifest_sha256"),
            "overview_scalars": overview,
            "track_count": count,
            "track_count_source": source,
            "status": "available",
        }
    except Exception as error:
        # Preserve history even if a status is transiently unavailable.
        return {"status": "unavailable", "reason": type(error).__name__}


def inclusion(capture: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    raw = {
        "utc_qualified": capture.get("utc_qualified") is True,
        "completed": capture.get("terminal_state") == "completed",
        "source_span_attested": capture.get("source_span_attested") is True,
        "nominal_300_s": capture.get("nominal_duration_seconds") == 300,
        "retained_visits_positive": int(capture.get("retained_visits", 0)) > 0,
    }
    dual_rx = status.get("receiver_ids") == [0, 1]
    raw["dual_rx_declared_by_analysis"] = dual_rx
    # A history item has no geometry binding payload.  It cannot demonstrate
    # the fixture, receiver-slot mapping, or its digest.
    geometry = "unavailable_from_public_inventory_api"
    analysis_ready = status.get("state") == "completed" and status.get("track_count") is not None
    return {
        "raw_capture_eligible": all(raw.values()),
        "analysis_ready": analysis_ready,
        "geometry_status": geometry,
        "geometry_aware_model_eligible": False,
        "raw_conditions": raw,
        "exclusion_reasons": [
            name for name, passed in raw.items() if not passed
        ]
        + ([] if analysis_ready else ["no_public_completed_track_count"])
        + ["geometry_binding_not_exposed"],
    }


def build(api: str, cutoff: datetime, workers: int) -> dict[str, Any]:
    all_rows = history(api)
    candidates = []
    for item in all_rows:
        captured_at = item.get("captured_at")
        if captured_at is None:
            continue
        stamp = as_utc(captured_at)
        if stamp.date().isoformat() == DATE and stamp < cutoff:
            candidates.append(item)
    candidates.sort(key=lambda row: row["captured_at"])
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        statuses = list(pool.map(lambda row: analysis(api, row["session_id"]), candidates))
    scans = []
    for capture, status in zip(candidates, statuses, strict=True):
        scan = {
            "session_id": capture["session_id"],
            "captured_at": capture["captured_at"],
            "recorded_at": capture["recorded_at"],
            "finalized_at": capture["finalized_at"],
            "input_manifest_sha256": capture["input_manifest_sha256"],
            "radio_id": capture["radio_id"],
            "radio_serial": capture.get("radio_serial"),
            "capture_schema_version": capture["schema_version"],
            "sample_rate_hz": capture["sample_rate_hz"],
            "bandwidth_hz": capture["bandwidth_hz"],
            "valid_visit_ms": capture["valid_visit_ms"],
            "started_visits": capture["started_visits"],
            "retained_visits": capture["retained_visits"],
            "valid_duty_ppm": capture.get("valid_duty_ppm"),
            "source_span_seconds": capture.get("source_span_seconds"),
            "capture_qualified": capture["capture_qualified"],
            "analysis_state_at_cutoff": capture["analysis_state"],
            "selected_edge": capture.get("selected_edge"),
            "allowed_target_mask": capture.get("allowed_target_mask"),
            "target_coverage": [
                {
                    "target_index": row["target_index"],
                    "retained_visits": row["retained_visits"],
                    "valid_seconds": row["valid_seconds"],
                }
                for row in capture["target_coverage"]
            ],
            "analysis": status,
        }
        scan["inclusion"] = inclusion(capture, status)
        scans.append(scan)
    counts = {
        "history_items_read": len(all_rows),
        "date_before_cutoff": len(scans),
        "raw_capture_eligible": sum(row["inclusion"]["raw_capture_eligible"] for row in scans),
        "analysis_ready": sum(row["inclusion"]["analysis_ready"] for row in scans),
        "geometry_aware_model_eligible": sum(
            row["inclusion"]["geometry_aware_model_eligible"] for row in scans
        ),
        "analysis_status_unavailable": sum(
            row["analysis"]["status"] != "available" for row in scans
        ),
    }
    return {
        "schema": "ds2-adaptive-inventory/v1",
        "inventory_kind": "read_only_metadata_and_existing_analysis_status",
        "utc_cutoff_exclusive": cutoff.isoformat().replace("+00:00", "Z"),
        "date_utc": DATE,
        "history_api": api,
        "qnap_access": "not opened",
        "raw_iq_access": "not opened",
        "geometry_limitation": (
            "the public inventory API omits capture receiver-geometry bindings; "
            "protected bulk manifests were not accessible to this read-only user"
        ),
        "eligibility_policy": {
            "raw_capture": "all raw_conditions must pass",
            "analysis_ready": "public status completed and exposes an explicit track count",
            "geometry_aware_model": (
                "requires an explicit capture-time geometry binding; none inferred"
            ),
        },
        "counts": counts,
        "scans": scans,
        "bindings": {"builder": digest(Path(__file__))},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff-utc", required=True, type=as_utc)
    parser.add_argument("--api", default=API)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.cutoff_utc.date().isoformat() != DATE or not 1 <= args.workers <= 16:
        raise ValueError("cutoff must lie on the DS2 UTC date and workers must be 1..16")
    document = build(args.api.rstrip("/"), args.cutoff_utc, args.workers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical(document))
    args.output.with_suffix(".sha256").write_text(digest(args.output) + "\n")
    print(json.dumps(document["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
