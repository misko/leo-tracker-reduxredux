#!/usr/bin/env python3
"""Plan or enqueue only the frozen, raw-eligible DS2 adaptive captures.

The input manifest is immutable evidence from the DS2 inventory.  This tool
does not collect RF, open QNAP, or change capture data.  It reads protected
local capture manifests through the same ``leo`` account as the production
worker and, only with ``--enqueue``, creates idempotent *derived-product*
queue records for exactly those frozen session IDs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from leo.cli.adaptive_processing_queue import (
    _catalog,
    _position_methods_complete,
    _tracking_digest,
)
from leo.contracts.digests import canonical_digest
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
from leo.storage.scanner_tracking import ScannerTrackingStore

HERE = Path(__file__).resolve().parent
FROZEN_MANIFEST = HERE.parent / "2026_09_24_ds2_inventory" / "manifest.json"
EXPECTED_SESSION_COUNT = 20
PROBE_STRIDE_MS = 120
TRACKING_SITE = "spinnaker-sausalito"
GEOMETRY_REGISTRY = HERE.parents[1] / "src/leo/station/gauss-r21-lt3d-001a-20260920-v1.json"


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def digest(value: Path) -> str:
    return "sha256:" + hashlib.sha256(value.read_bytes()).hexdigest()


def frozen_scans(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Return the exact eligible DS2 set, rejecting drift or partial inputs."""
    if document.get("schema") not in {"ds2-adaptive-inventory/v1", "ds2-adaptive-inventory/v2"}:
        raise ValueError("expected the frozen DS2 inventory schema")
    rows = tuple(
        item
        for item in document.get("scans", [])
        if item.get("inclusion", {}).get("raw_capture_eligible") is True
    )
    identifiers = tuple(item.get("session_id") for item in rows)
    if len(rows) != EXPECTED_SESSION_COUNT or len(set(identifiers)) != EXPECTED_SESSION_COUNT:
        raise ValueError(
            f"frozen DS2 must contain exactly {EXPECTED_SESSION_COUNT} unique raw captures"
        )
    if any(not isinstance(item, str) or not item.startswith("scan-fw-") for item in identifiers):
        raise ValueError("frozen DS2 contains an invalid adaptive session ID")
    return rows


def geometry_summary(capture: Any) -> dict[str, Any]:
    """Serialize an explicit capture-time binding; never infer it from radio ID."""
    geometry = getattr(capture.manifest, "receiver_geometry", None)
    if geometry is None:
        return {"status": "absent_from_capture_manifest"}
    radio = geometry.radio
    assignments = tuple(radio.assignments)
    return {
        "status": "explicit_capture_binding",
        "binding_digest": geometry.binding_digest,
        "station_id": geometry.station_id,
        "station_geometry_revision": geometry.station_geometry_revision,
        "station_geometry_digest": geometry.station_geometry_digest,
        "valid_from_utc_ns": geometry.valid_from_utc_ns,
        "valid_until_utc_ns": geometry.valid_until_utc_ns,
        "radio_id": radio.radio_id,
        "radio_serial": radio.radio_serial,
        "fixture_part_id": radio.fixture_part_id,
        "fixture_digest": radio.fixture_digest,
        "assignments": [
            {
                "receiver_id": assignment.receiver_id,
                "slot_id": assignment.slot_id,
                "mapping_status": assignment.mapping_status,
                "mapping_evidence": assignment.mapping_evidence,
            }
            for assignment in assignments
        ],
    }


def registry_geometry_summary(capture: Any) -> dict[str, Any]:
    """Resolve a registry authority only after matching sealed capture identity/time."""
    receipt = capture.manifest.receipt
    radio_id = getattr(receipt, "radio_id", None)
    radio_serial = getattr(receipt, "radio_serial", None)
    captured_utc_ns = capture.manifest.created_utc_ns
    registry = json.loads(GEOMETRY_REGISTRY.read_text())
    matches = [
        radio
        for radio in registry["radios"]
        if radio["radio_id"] == radio_id and radio["radio_serial"] == radio_serial
    ]
    if len(matches) != 1:
        return {
            "status": "no_explicit_registry_match",
            "capture_radio_id": radio_id,
            "capture_radio_serial": radio_serial,
        }
    if not registry["valid_from_utc_ns"] <= captured_utc_ns <= registry["valid_until_utc_ns"]:
        return {
            "status": "registry_outside_capture_validity",
            "capture_created_utc_ns": captured_utc_ns,
            "valid_from_utc_ns": registry["valid_from_utc_ns"],
            "valid_until_utc_ns": registry["valid_until_utc_ns"],
        }
    radio = matches[0]
    return {
        "status": "explicit_registry_match",
        "authority_path": str(GEOMETRY_REGISTRY.relative_to(HERE.parents[1])),
        "authority_sha256": digest(GEOMETRY_REGISTRY),
        "station_id": registry["station_id"],
        "station_geometry_revision": registry["geometry_revision"],
        "station_geometry_digest": registry["geometry_digest"],
        "capture_created_utc_ns": captured_utc_ns,
        "valid_from_utc_ns": registry["valid_from_utc_ns"],
        "valid_until_utc_ns": registry["valid_until_utc_ns"],
        "fixture_part_id": radio["fixture_part_id"],
        "fixture_digest": radio["fixture_digest"],
        "assignments": [
            {
                "receiver_id": assignment["receiver_id"],
                "slot_id": assignment["slot_id"],
                "mapping_status": assignment["mapping_status"],
                "mapping_evidence": assignment["mapping_evidence"],
            }
            for assignment in radio["assignments"]
        ],
    }


def action_for(*, capture: Any, status: Any, phase: Any, tracking: ScannerTrackingStore) -> str:
    """Choose one bounded product action without starting an analysis locally."""
    # The current V14 product is the local counterpart of the public
    # authoritative tracking endpoint.  Do not requeue it merely because the
    # older analysis-status presentation omits completed-track evidence.
    if tracking.analysis_status(capture.manifest.session_id).state == "complete":
        return "tracking_complete"
    if status.state != "figures_ready" or phase is None or phase.state != "complete":
        return "enqueue_analysis"
    if status.metrics_manifest_sha256 is None:
        raise ValueError("figures-ready analysis lacks its metrics manifest digest")
    products_complete = _position_methods_complete(
        tracking.root,
        capture.manifest.session_id,
        expected_input_manifest_sha256=capture.manifest_sha256,
    )
    if products_complete:
        return "already_complete"
    return "enqueue_tracking"


def plan(*, bulk_root: Path, manifest_path: Path) -> dict[str, Any]:
    """Read exact manifests and status products, producing a non-mutating plan."""
    document = json.loads(manifest_path.read_text())
    rows = frozen_scans(document)
    captures = AdaptiveHopIqStore(bulk_root, read_only=True)
    presentation = AdaptiveHopAnalysisPresentationStore(bulk_root)
    tracking = ScannerTrackingStore(bulk_root, read_only=True)
    entries: list[dict[str, Any]] = []
    try:
        for frozen in rows:
            session_id = frozen["session_id"]
            capture = captures.inspect(session_id)
            if capture.manifest_sha256 != frozen["input_manifest_sha256"]:
                raise ValueError(f"{session_id}: capture manifest differs from frozen inventory")
            status = presentation.status_for_capture(capture, probe_stride_ms=PROBE_STRIDE_MS)
            phase = presentation.relative_phase_status(session_id, probe_stride_ms=PROBE_STRIDE_MS)
            action = action_for(capture=capture, status=status, phase=phase, tracking=tracking)
            analysis_configuration_digest = canonical_digest(
                {
                    "metrics": status.binding_sha256,
                    "relative_phase": "adaptive-broadband-pilot-relative-phase-v1",
                }
            )
            entries.append(
                {
                    "session_id": session_id,
                    "input_manifest_sha256": capture.manifest_sha256,
                    "capture_schema_version": capture.manifest.schema_version,
                    "action": action,
                    "analysis_status": status.state,
                    "analysis_binding_sha256": status.binding_sha256,
                    "analysis_configuration_sha256": analysis_configuration_digest,
                    "relative_phase_state": None if phase is None else phase.state,
                    "metrics_manifest_sha256": status.metrics_manifest_sha256,
                    "receiver_geometry": geometry_summary(capture),
                    "registry_geometry": registry_geometry_summary(capture),
                }
            )
    finally:
        captures.close()
    return {
        "schema": "ds2-frozen-backfill-plan/v1",
        "mode": "dry_run",
        "source_inventory": str(manifest_path),
        "source_inventory_sha256": digest(manifest_path),
        "expected_session_count": EXPECTED_SESSION_COUNT,
        "source_data": "read-only local bulk capture manifests; QNAP not opened",
        "actions": entries,
        "counts": {
            "frozen_sessions": len(entries),
            "enqueue_analysis": sum(item["action"] == "enqueue_analysis" for item in entries),
            "enqueue_tracking": sum(item["action"] == "enqueue_tracking" for item in entries),
            "tracking_complete": sum(item["action"] == "tracking_complete" for item in entries),
            "already_complete": sum(item["action"] == "already_complete" for item in entries),
            "explicit_geometry_bindings": sum(
                item["receiver_geometry"]["status"] == "explicit_capture_binding"
                for item in entries
            ),
            "explicit_registry_geometry_matches": sum(
                item["registry_geometry"]["status"] == "explicit_registry_match"
                for item in entries
            ),
        },
    }


def enqueue(document: dict[str, Any], *, bulk_root: Path) -> dict[str, Any]:
    """Enqueue precisely the actions in a freshly-created DS2 plan."""
    if document["counts"]["frozen_sessions"] != EXPECTED_SESSION_COUNT:
        raise ValueError("refusing to enqueue a non-frozen DS2 plan")
    catalog = _catalog()
    captures = AdaptiveHopIqStore(bulk_root, read_only=True)
    presentation = AdaptiveHopAnalysisPresentationStore(bulk_root)
    entries: list[dict[str, Any]] = []
    try:
        for item in document["actions"]:
            session_id = item["session_id"]
            capture = captures.inspect(session_id)
            if capture.manifest_sha256 != item["input_manifest_sha256"]:
                raise ValueError(f"{session_id}: input changed after DS2 plan creation")
            if item["action"] == "enqueue_analysis":
                created = catalog.enqueue_adaptive_analysis_job(
                    session_id=session_id,
                    input_manifest_digest=capture.manifest_sha256,
                    configuration_digest=item["analysis_configuration_sha256"],
                )
                result = "enqueued" if created else "already_enqueued"
            elif item["action"] == "enqueue_tracking":
                status = presentation.status_for_capture(capture, probe_stride_ms=PROBE_STRIDE_MS)
                if status.metrics_manifest_sha256 != item["metrics_manifest_sha256"]:
                    raise ValueError(
                        f"{session_id}: metrics authority changed after DS2 plan creation"
                    )
                created = catalog.enqueue_adaptive_tracking_job(
                    session_id=session_id,
                    input_manifest_digest=capture.manifest_sha256,
                    configuration_digest=_tracking_digest(
                        capture=capture,
                        metrics_manifest_sha256=status.metrics_manifest_sha256,
                        site=TRACKING_SITE,
                    ),
                )
                result = "enqueued" if created else "already_enqueued"
            else:
                result = "already_complete"
            entries.append({"session_id": session_id, "action": item["action"], "result": result})
    finally:
        captures.close()
    return {
        **document,
        "mode": "enqueue",
        "queue_results": entries,
        "queue_counts": {
            "enqueued": sum(item["result"] == "enqueued" for item in entries),
            "already_enqueued": sum(item["result"] == "already_enqueued" for item in entries),
            "already_complete": sum(item["result"] == "already_complete" for item in entries),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--manifest", type=Path, default=FROZEN_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--enqueue", action="store_true")
    args = parser.parse_args()
    document = plan(bulk_root=args.bulk_root, manifest_path=args.manifest)
    if args.enqueue:
        document = enqueue(document, bulk_root=args.bulk_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical(document))
    print(json.dumps(document["counts"], sort_keys=True))
    if args.enqueue:
        print(json.dumps(document["queue_counts"], sort_keys=True))


if __name__ == "__main__":
    main()
