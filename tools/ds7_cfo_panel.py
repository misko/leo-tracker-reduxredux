#!/usr/bin/env python3
"""Freeze and validate the reference-free DS7 pilot/CFO panel.

This tool consumes a deliberately small allowlisted inventory exported through
the public observation-product port.  It never opens recordings or DS7 pose
data.  A separate IQ experiment may consume the frozen panel after receiving a
coordinator lease.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PANEL_SCHEMA = "ds7-cfo-panel/v1"
INVENTORY_SCHEMA = "ds7-cfo-support-inventory/v1"
MATCHED_SCHEMA = "ds7-cfo-matched-epochs/v1"
SUPPORT_CLASSES = ("strong", "weak", "failed")
FORBIDDEN_FRAGMENTS = (
    "latitude",
    "longitude",
    "observer_site",
    "position",
    "pose",
    "reference_score",
    "truth",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


def _digest(document: Any) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _reject_reference_fields(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_FRAGMENTS):
                raise ValueError(f"reference-bearing field is forbidden: {path}.{key}")
            _reject_reference_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_reference_fields(child, f"{path}[{index}]")


def freeze_panel(plan: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    _reject_reference_fields(inventory)
    if inventory.get("schema") != INVENTORY_SCHEMA:
        raise ValueError(f"inventory schema must be {INVENTORY_SCHEMA}")
    if inventory.get("dataset_sha256") != plan.get("dataset_sha256"):
        raise ValueError("inventory dataset digest disagrees with plan")
    if inventory.get("reference_audit") != "reference_excluded":
        raise ValueError("inventory must declare reference_excluded")
    source = inventory.get("source")
    if not isinstance(source, dict) or source.get("port") != "public_observation_product":
        raise ValueError("inventory source must identify the public observation-product port")

    captures = {capture["session_id"]: capture for capture in plan["captures"]}
    rows = inventory.get("rows")
    if not isinstance(rows, list):
        raise ValueError("inventory rows must be a list")
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        session_id = row.get("session_id")
        if session_id in seen:
            raise ValueError(f"duplicate inventory session: {session_id}")
        seen.add(session_id)
        capture = captures.get(session_id)
        if capture is None:
            raise ValueError(f"inventory session is outside the frozen plan: {session_id}")
        if row.get("manifest_sha256") != capture["manifest_sha256"]:
            raise ValueError(f"manifest digest mismatch for {session_id}")
        if row.get("sample_rate_hz") != capture["sample_rate_hz"]:
            raise ValueError(f"sample rate mismatch for {session_id}")
        support_class = row.get("support_class")
        if support_class not in SUPPORT_CLASSES:
            raise ValueError(f"invalid support class for {session_id}")
        receivers = row.get("receiver_ids")
        if (
            not isinstance(receivers, list)
            or any(x not in (0, 1) for x in receivers)
            or (not receivers and support_class != "failed")
        ):
            raise ValueError(f"receiver_ids must contain only 0/1 for {session_id}")
        allowed = {
            "session_id",
            "manifest_sha256",
            "sample_rate_hz",
            "support_class",
            "receiver_ids",
            "tracking_state",
            "tracklet_count",
            "attempted_group_count",
            "deferred_group_count",
            "product_schema",
            "product_digest",
            "reason",
        }
        unknown = set(row) - allowed
        if unknown:
            raise ValueError(f"non-allowlisted fields for {session_id}: {sorted(unknown)}")
        validated.append(dict(row))

    # Round-robin by support class makes the selection independent of position
    # or later scores.  Within a stratum, chronology from the public plan wins.
    order = {capture["session_id"]: i for i, capture in enumerate(plan["captures"])}
    selected: list[dict[str, Any]] = []
    rates = sorted({capture["sample_rate_hz"] for capture in plan["captures"]})
    for index, rate in enumerate(rates):
        preferred = SUPPORT_CLASSES[index % len(SUPPORT_CLASSES)]
        candidates = sorted(
            (row for row in validated if row["sample_rate_hz"] == rate),
            key=lambda row: (
                row["support_class"] != preferred,
                row["tracking_state"] not in {"complete", "unavailable"},
                order[row["session_id"]],
            ),
        )
        if not candidates:
            raise ValueError(f"inventory has no row at {rate} Hz")
        selected.append(candidates[0])
    for support_class in SUPPORT_CLASSES:
        if not any(row["support_class"] == support_class for row in selected):
            candidates = sorted(
                (
                    row
                    for row in validated
                    if row["support_class"] == support_class
                    and row["session_id"] not in {item["session_id"] for item in selected}
                ),
                key=lambda row: order[row["session_id"]],
            )
            if not candidates:
                raise ValueError(f"inventory cannot cover {support_class} support")
            selected.append(candidates[0])
    if {receiver for row in selected for receiver in row["receiver_ids"]} != {0, 1}:
        raise ValueError("selected panel does not cover both receivers")

    return {
        "schema": PANEL_SCHEMA,
        "dataset_sha256": plan["dataset_sha256"],
        "plan_content_sha256": plan["content_sha256"],
        "reference_audit": "reference_excluded",
        "selection_policy": (
            "four rates; round-robin strong/weak/failed preference; chronological tie break"
        ),
        "inventory_sha256": _digest(inventory),
        "source": source,
        "captures": selected,
        "native_waveform_applicability": {
            "known_qin_edge_pilot": {
                "minimum_sample_rate_hz": 1_875_000,
                "eligible_panel_rates_hz": rates,
                "claim": "edge-pilot tones only; no full occupied Starlink channel claim",
            },
            "frame_cfo": {
                "requires": "acquisition-bound timing/CFO basin and a complete known-pilot frame",
                "does_not": "acquire timing, select a CFO alias, or establish carrier continuity",
            },
            "full_band_waveform": {
                "eligible": False,
                "reason": (
                    "2.5-10 MHz recordings do not contain the full native "
                    "Starlink downlink bandwidth"
                ),
            },
        },
        "execution": {
            "raw_iq_read_bytes": 0,
            "scoring_performed": False,
            "downstream_gate": "await versioned baseline observation product",
        },
    }


def build_cached_inventory(plan: dict[str, Any], bulk_root: Path) -> dict[str, Any]:
    """Project support strata from cached numerical tracking products only."""
    from leo.analysis.persistent_hop_trajectory import (  # noqa: PLC0415
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates  # noqa: PLC0415
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore  # noqa: PLC0415

    rows: list[dict[str, Any]] = []
    store = ScannerTrackingInputStore(bulk_root)
    try:
        for capture in plan["captures"]:
            session_id = capture["session_id"]
            try:
                raw = store.load(session_id)
                if raw.input_manifest_sha256 != capture["manifest_sha256"]:
                    raise ValueError(f"cached product manifest mismatch for {session_id}")
                points = project_scanner_candidates(raw)
                points_by_id = {point.candidate_id: point for point in points}
                graph = reconstruct_persistent_hop_trajectories(
                    points,
                    config=PersistentHopTrajectoryConfig(
                        minimum_span_s=3.0, minimum_support=6
                    ),
                )
                count = len(graph.tracklets)
                support_class = "failed" if count == 0 else "weak" if count < 6 else "strong"
                track_receivers = sorted(
                    {
                        points_by_id[point.candidate_id].receiver_id
                        for track in graph.tracklets
                        for point in track.points
                    }
                )
                candidate_receivers = sorted({point.receiver_id for point in points})
                rows.append(
                    {
                        "session_id": session_id,
                        "manifest_sha256": raw.input_manifest_sha256,
                        "sample_rate_hz": raw.sample_rate_hz,
                        "support_class": support_class,
                        "receiver_ids": track_receivers or candidate_receivers,
                        "tracking_state": "complete" if count else "no_supported_tracklets",
                        "tracklet_count": count,
                        "product_schema": type(raw).__name__,
                        "product_digest": raw.analysis_manifest_sha256,
                        "reason": (
                            "persistent trajectories: minimum span 3 s and minimum support 6"
                            if count
                            else (
                                "cached candidates produced no trajectory at the frozen "
                                "support gate"
                            )
                        ),
                    }
                )
            except (FileNotFoundError, KeyError, OSError, ValueError) as error:
                rows.append(
                    {
                        "session_id": session_id,
                        "manifest_sha256": capture["manifest_sha256"],
                        "sample_rate_hz": capture["sample_rate_hz"],
                        "support_class": "failed",
                        "receiver_ids": [],
                        "tracking_state": "unavailable",
                        "tracklet_count": 0,
                        "reason": str(error),
                    }
                )
    finally:
        store.close()
    return {
        "schema": INVENTORY_SCHEMA,
        "dataset_sha256": plan["dataset_sha256"],
        "reference_audit": "reference_excluded",
        "source": {
            "port": "public_observation_product",
            "implementation": (
                "ScannerTrackingInputStore.load + project_scanner_candidates + "
                "reconstruct_persistent_hop_trajectories"
            ),
            "payload_access": "cached numerical analysis only; no raw IQ",
            "support_gate": {"minimum_span_s": 3.0, "minimum_support": 6},
            "class_policy": {
                "failed": "0 tracklets",
                "weak": "1-5 tracklets",
                "strong": ">=6 tracklets",
            },
        },
        "rows": rows,
    }


def build_api_inventory(
    plan: dict[str, Any],
    base_url: str,
    *,
    request_timeout_s: float = 3.0,
    total_seconds: float = 90.0,
) -> dict[str, Any]:
    """Read only allowlisted tracking-status metadata from the public API."""
    started = time.monotonic()
    rows: list[dict[str, Any]] = []
    for capture in plan["captures"]:
        session_id = capture["session_id"]
        if time.monotonic() - started >= total_seconds:
            state: dict[str, Any] | None = None
            reason = "total API inventory deadline reached"
        else:
            url = f"{base_url.rstrip('/')}/api/v1/scanner/tracking/{session_id}"
            try:
                with urllib.request.urlopen(url, timeout=request_timeout_s) as response:
                    envelope = json.load(response)
                # Deliberately index only the approved envelope/product fields.
                state = {
                    "state": envelope.get("state"),
                    "failure_summary": envelope.get("failure_summary"),
                    "product": envelope.get("product"),
                }
                reason = ""
            except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
                state = None
                reason = f"public tracking status unavailable: {type(error).__name__}"
        if state is None or not isinstance(state["product"], dict):
            rows.append(
                {
                    "session_id": session_id,
                    "manifest_sha256": capture["manifest_sha256"],
                    "sample_rate_hz": capture["sample_rate_hz"],
                    "support_class": "failed",
                    "receiver_ids": [],
                    "tracking_state": "unavailable",
                    "tracklet_count": 0,
                    "reason": reason or str(state["failure_summary"]),
                }
            )
            continue
        product = state["product"]
        if product.get("input_manifest_sha256") != capture["manifest_sha256"]:
            raise ValueError(f"public tracking manifest mismatch for {session_id}")
        tracklets = product.get("tracklets")
        if not isinstance(tracklets, list):
            raise ValueError(f"public tracking tracklets are invalid for {session_id}")
        receivers = sorted(
            {tracklet.get("receiver_id") for tracklet in tracklets}
            & {0, 1}
        )
        count = len(tracklets)
        rows.append(
            {
                "session_id": session_id,
                "manifest_sha256": product["input_manifest_sha256"],
                "sample_rate_hz": capture["sample_rate_hz"],
                "support_class": "failed" if count == 0 else "pending_nonzero",
                "receiver_ids": receivers,
                "tracking_state": str(state["state"]),
                "tracklet_count": count,
                "attempted_group_count": product.get("attempted_group_count", 0),
                "deferred_group_count": product.get("deferred_group_count", 0),
                "product_schema": f"scanner-tracking/v{product.get('schema_version')}",
                "product_digest": product["analysis_manifest_sha256"],
                "reason": "public tracking status allowlist projection",
            }
        )
    complete_counts = sorted(
        row["tracklet_count"]
        for row in rows
        if row["tracking_state"] == "complete" and row["tracklet_count"] > 0
    )
    if not complete_counts:
        raise ValueError("public tracking inventory has no complete nonzero products")
    strong_threshold = complete_counts[len(complete_counts) // 2]
    for row in rows:
        if row["support_class"] == "pending_nonzero":
            row["support_class"] = (
                "strong" if row["tracklet_count"] >= strong_threshold else "weak"
            )
    return {
        "schema": INVENTORY_SCHEMA,
        "dataset_sha256": plan["dataset_sha256"],
        "reference_audit": "reference_excluded",
        "source": {
            "port": "public_observation_product",
            "endpoint": f"{base_url.rstrip('/')}/api/v1/scanner/tracking/{{session_id}}",
            "projection": (
                "state/schema/input+analysis digests/tracklet count+receiver IDs/"
                "attempted+deferred counts only"
            ),
            "request_timeout_s": request_timeout_s,
            "total_seconds": total_seconds,
            "raw_iq_read_bytes": 0,
            "class_policy": {
                "failed": "unavailable or 0 tracklets",
                "weak": f"1-{strong_threshold - 1} tracklets",
                "strong": f">={strong_threshold} tracklets",
                "threshold_basis": "upper median complete nonzero product count",
            },
        },
        "rows": rows,
    }


def validate_matched_epochs(document: dict[str, Any]) -> None:
    _reject_reference_fields(document)
    if document.get("schema") != MATCHED_SCHEMA:
        raise ValueError(f"matched document schema must be {MATCHED_SCHEMA}")
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("matched rows must be a nonempty list")
    seen: set[tuple[Any, ...]] = set()
    methods: dict[tuple[Any, ...], set[str]] = {}
    for row in rows:
        key = (row.get("session_id"), row.get("receiver_id"), row.get("epoch_utc_ns"))
        if key in seen and row.get("method") in methods.get(key, set()):
            raise ValueError(f"duplicate method at matched epoch: {key}")
        seen.add(key)
        methods.setdefault(key, set()).add(row.get("method"))
        if row.get("status") not in {"supported", "rejected", "failed", "inapplicable"}:
            raise ValueError(f"invalid matched-epoch status: {key}")
    expected = set(document.get("methods", []))
    if not expected or any(found != expected for found in methods.values()):
        raise ValueError("every matched epoch must account for every declared method")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--plan", type=Path, required=True)
    freeze.add_argument("--inventory", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    inventory = subparsers.add_parser("inventory")
    inventory.add_argument("--plan", type=Path, required=True)
    inventory.add_argument("--bulk-root", type=Path, required=True)
    inventory.add_argument("--output", type=Path, required=True)
    api_inventory = subparsers.add_parser("api-inventory")
    api_inventory.add_argument("--plan", type=Path, required=True)
    api_inventory.add_argument("--base-url", default="http://127.0.0.1:8090")
    api_inventory.add_argument("--output", type=Path, required=True)
    matched = subparsers.add_parser("validate-matched")
    matched.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "api-inventory":
        if args.output.exists():
            raise SystemExit("output already exists")
        result = build_api_inventory(_load(args.plan), args.base_url)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    elif args.command == "inventory":
        if args.output.exists():
            raise SystemExit("output already exists")
        result = build_cached_inventory(_load(args.plan), args.bulk_root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    elif args.command == "freeze":
        if args.output.exists():
            raise SystemExit("output already exists")
        result = freeze_panel(_load(args.plan), _load(args.inventory))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    else:
        validate_matched_epochs(_load(args.input))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
