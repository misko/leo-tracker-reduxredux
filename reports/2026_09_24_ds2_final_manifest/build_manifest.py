#!/usr/bin/env python3
"""Freeze DS2 as one whole-session development corpus after V14 tracking completes.

This builder intentionally has no train/validation/test split.  It binds the
twenty sessions fixed by the DS2 inventory to their authoritative tracking
receipts, and makes the only positioning prior a Sacramento-centred 250 km
blind search region.  Evaluation coordinates are deliberately absent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
TRACKING_ENDPOINT = "http://127.0.0.1:8090/api/v1/scanner/tracking"
EXPECTED_SESSIONS = 20
REGISTRY = HERE.parents[1] / "src/leo/station/gauss-r21-lt3d-001a-20260920-v1.json"


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical(value).encode())


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def fetch_tracking(endpoint: str, session_id: str) -> dict[str, Any]:
    with urlopen(f"{endpoint.rstrip('/')}/{session_id}", timeout=20) as response:  # noqa: S310
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError(f"{session_id}: tracking endpoint did not return an object")
    return value


def inventory_rows(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    if inventory.get("schema") not in {"ds2-adaptive-inventory/v1", "ds2-adaptive-inventory/v2"}:
        raise ValueError("unexpected DS2 inventory schema")
    rows = [
        row
        for row in inventory.get("scans", [])
        if isinstance(row, dict) and row.get("inclusion", {}).get("raw_capture_eligible") is True
    ]
    identifiers = [row.get("session_id") for row in rows]
    if len(rows) != EXPECTED_SESSIONS or len(set(identifiers)) != EXPECTED_SESSIONS:
        raise ValueError("DS2 must have exactly twenty unique raw-eligible sessions")
    if any(not isinstance(item, str) or not item.startswith("scan-fw-") for item in identifiers):
        raise ValueError("DS2 inventory contains an invalid session ID")
    return rows


def geometry_by_session(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if plan.get("schema") != "ds2-frozen-backfill-plan/v1":
        raise ValueError("unexpected DS2 backfill plan schema")
    output: dict[str, dict[str, Any]] = {}
    for row in plan.get("actions", []):
        if not isinstance(row, dict) or not isinstance(row.get("session_id"), str):
            raise ValueError("backfill plan has an invalid action")
        output[row["session_id"]] = {
            "capture": row.get("receiver_geometry"),
            "registry": row.get("registry_geometry"),
        }
    if len(output) != EXPECTED_SESSIONS:
        raise ValueError("backfill plan does not bind all twenty DS2 sessions")
    return output


def safe_receipt(response: dict[str, Any]) -> dict[str, Any]:
    """Keep only content-addressed tracking evidence, never observer position."""
    product = response.get("product") if isinstance(response.get("product"), dict) else {}
    return {
        "schema": "ds2-authoritative-tracking-receipt/v1",
        "session_id": response.get("session_id"),
        "state": response.get("state"),
        "phase": response.get("phase"),
        "product_schema_version": product.get("schema_version"),
        "analysis_id": product.get("analysis_id"),
        "input_manifest_sha256": product.get("input_manifest_sha256"),
        "analysis_manifest_sha256": product.get("analysis_manifest_sha256"),
        "configuration_digest": product.get("configuration_digest"),
        "candidate_policy_digest": product.get("tle_match_config_digest"),
        "tle_snapshot_digest": (product.get("eligible_tle_snapshot") or {}).get("digest"),
        "tracklet_count": len(product.get("tracklets", [])),
        "tle_candidate_count": len(product.get("tle_candidates", [])),
        "review_count": product.get("review_count"),
        "artifact_count": len(product.get("artifacts", [])),
        "artifacts": [
            {key: artifact.get(key) for key in ("name", "sha256", "byte_count")}
            for artifact in product.get("artifacts", [])
            if isinstance(artifact, dict)
        ],
    }


def session_geometry(binding: dict[str, Any]) -> dict[str, Any]:
    capture = binding.get("capture")
    registry = binding.get("registry")
    if not isinstance(capture, dict) or capture.get("status") != "explicit_capture_binding":
        return {
            "eligibility": "unavailable",
            "reason": "no_explicit_capture_time_receiver_geometry",
        }
    if not isinstance(registry, dict) or registry.get("status") != "explicit_registry_match":
        return {
            "eligibility": "unavailable",
            "reason": "no_matching_valid_registry_authority",
        }
    assignments = capture.get("assignments")
    if not isinstance(assignments, list) or len(assignments) != 2:
        raise ValueError("explicit geometry requires exactly two receiver assignments")
    mapping_status = sorted(
        {item.get("mapping_status") for item in assignments if isinstance(item, dict)}
    )
    if mapping_status != ["provisional"]:
        raise ValueError("unexpected DS2 geometry mapping status")
    return {
        "eligibility": "conditional_provisional_mapping",
        "model_use": "geometry and cone diagnostics only; marginalize both RX-to-slot permutations",
        "geometry_authority_path": str(REGISTRY.resolve()),
        "geometry_authority_sha256": sha256_bytes(REGISTRY.read_bytes()),
        "station_geometry_digest": registry.get("station_geometry_digest"),
        "capture_binding_digest": capture.get("binding_digest"),
        "fixture_part_id": capture.get("fixture_part_id"),
        "fixture_digest": capture.get("fixture_digest"),
        "assignments": assignments,
        "mapping_uncertainty": {
            "status": "provisional",
            "required_treatment": "symmetric_two_mapping_marginalization",
            "not_permitted": "reporting a selected RX-to-slot permutation as calibrated fact",
        },
    }


def build(
    inventory: dict[str, Any],
    plan: dict[str, Any],
    endpoint: str,
    output: Path,
    observed_utc: str | None = None,
) -> dict[str, Any]:
    rows = inventory_rows(inventory)
    geometry = geometry_by_session(plan)
    receipt_root = output / "tracking_receipts"
    cohorts: defaultdict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    all_sessions: list[dict[str, Any]] = []
    pending_receipts: list[tuple[Path, dict[str, Any]]] = []
    for row in sorted(
        rows,
        key=lambda item: (str(item.get("captured_at")), str(item["session_id"])),
    ):
        session_id = row["session_id"]
        response = fetch_tracking(endpoint, session_id)
        receipt = safe_receipt(response)
        if response.get("state") != "complete" or not receipt["analysis_manifest_sha256"]:
            raise RuntimeError(f"{session_id}: V14 tracking product is not complete")
        if receipt["input_manifest_sha256"] != row["input_manifest_sha256"]:
            raise RuntimeError(f"{session_id}: tracking input digest differs from frozen inventory")
        if not receipt["candidate_policy_digest"]:
            raise RuntimeError(f"{session_id}: tracking product lacks candidate-policy digest")
        receipt_path = receipt_root / f"{session_id}.json"
        pending_receipts.append((receipt_path, receipt))
        session = {
            "session_id": session_id,
            "captured_at": row["captured_at"],
            "radio_id": row["radio_id"],
            "sample_rate_hz": row["sample_rate_hz"],
            "input_manifest_sha256": row["input_manifest_sha256"],
            "tracking": {
                "status": "complete",
                "tracking_product_digest": receipt["analysis_manifest_sha256"],
                "candidate_policy_digest": receipt["candidate_policy_digest"],
                "receipt_path": str(receipt_path.resolve()),
                "cache": {
                    "status": "not_materialized",
                    "reason": "DS2 inference has not yet built a receipt-bound prediction cache",
                },
            },
            "receiver_geometry": session_geometry(geometry[session_id]),
        }
        all_sessions.append(session)
        cohorts[(str(row["radio_id"]), int(row["sample_rate_hz"]))].append(session)
    policy_digests = {item["tracking"]["candidate_policy_digest"] for item in all_sessions}
    if len(policy_digests) != 1:
        raise RuntimeError("DS2 tracking products use more than one candidate policy")
    # Do not leave a partly bound corpus when one trailing product is pending.
    # All authoritative receipts are checked before the first artifact write.
    receipt_root.mkdir(parents=True, exist_ok=True)
    for receipt_path, receipt in pending_receipts:
        receipt_path.write_text(canonical(receipt))
    cohort_rows = []
    for (radio_id, sample_rate_hz), sessions in sorted(cohorts.items()):
        cohort_rows.append(
            {
                "cohort_id": f"{radio_id}-{sample_rate_hz}",
                "radio_id": radio_id,
                "sample_rate_hz": sample_rate_hz,
                "session_ids": [item["session_id"] for item in sessions],
                "session_count": len(sessions),
                "joint_inference_eligible": len(sessions) >= 2,
                "geometry_session_ids": [
                    item["session_id"]
                    for item in sessions
                    if item["receiver_geometry"]["eligibility"] == "conditional_provisional_mapping"
                ],
            }
        )
    observed = observed_utc or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "schema": "ds2-whole-corpus-manifest/v1",
        "manifest_sealed": True,
        "observed_utc": observed,
        "corpus_role": "development_evaluation_only",
        "whole_session_policy": (
            "every raw-eligible capture is included once; no train_validation_test_partition"
        ),
        "reference_coordinate_in_manifest": False,
        "position_evaluation": "external_post_inference_only",
        "inventory_manifest_sha256": sha256_json(inventory),
        "backfill_plan_sha256": sha256_json(plan),
        "candidate_policy_digest": next(iter(policy_digests)),
        "association_policy": {
            "input": "sealed V14 tracklet and candidate-review evidence",
            "blind_inference_requirement": (
                "recompute candidate predictions at every tested geographic cell; "
                "do not freeze a prior location's candidate identities"
            ),
            "identity_claims_permitted": False,
        },
        "blind_priors": [
            {
                "id": "sacramento-250km",
                "center_wgs84": {"latitude_deg": 38.5816, "longitude_deg": -121.4944},
                "radius_km": 250.0,
                "source": "fixed administrative-centre initialization",
                "reference_used_for_selection": False,
            }
        ],
        "sessions": all_sessions,
        "cohorts": cohort_rows,
        "geometry_policy": {
            "ordinary_models": "all 20 completed sessions",
            "geometry_and_cone_models": "only sessions with explicit capture-time geometry",
            "eligible_sessions": [
                item["session_id"]
                for item in all_sessions
                if item["receiver_geometry"]["eligibility"] == "conditional_provisional_mapping"
            ],
            "mapping_policy": "symmetric_two_mapping_marginalization required",
            "other_sessions": "not geometry eligible; do not infer fixture from radio identity",
        },
        "counts": {
            "sessions": len(all_sessions),
            "completed_tracking_products": len(all_sessions),
            "cohorts": len(cohort_rows),
            "geometry_conditional_sessions": sum(
                item["receiver_geometry"]["eligibility"] == "conditional_provisional_mapping"
                for item in all_sessions
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=HERE.parent / "2026_09_24_ds2_inventory" / "manifest.json",
    )
    parser.add_argument(
        "--backfill-plan",
        type=Path,
        default=HERE.parent / "2026_09_24_ds2_backfill" / "plan.json",
    )
    parser.add_argument("--output", type=Path, default=HERE)
    parser.add_argument("--endpoint", default=TRACKING_ENDPOINT)
    parser.add_argument(
        "--observed-utc",
        help=(
            "explicit seal timestamp; an existing sealed manifest's timestamp is reused by default"
        ),
    )
    args = parser.parse_args()
    previous = args.output / "manifest.json"
    previous_observed = None
    if previous.is_file():
        prior = read_object(previous)
        if prior.get("schema") == "ds2-whole-corpus-manifest/v1":
            candidate = prior.get("observed_utc")
            if isinstance(candidate, str):
                previous_observed = candidate
    manifest = build(
        read_object(args.inventory),
        read_object(args.backfill_plan),
        args.endpoint,
        args.output,
        observed_utc=args.observed_utc or previous_observed,
    )
    path = args.output / "manifest.json"
    path.write_text(canonical(manifest))
    (args.output / "manifest.sha256").write_text(
        hashlib.sha256(path.read_bytes()).hexdigest() + "\n"
    )
    receipt_root = args.output / "tracking_receipts"
    receipt_index = {
        "schema": "ds2-authoritative-tracking-receipt-index/v1",
        "manifest_sha256": sha256_bytes(path.read_bytes()),
        "receipts": {
            item.stem: sha256_bytes(item.read_bytes())
            for item in sorted(receipt_root.glob("scan-fw-*.json"))
        },
    }
    if len(receipt_index["receipts"]) != EXPECTED_SESSIONS:
        raise RuntimeError("receipt index must bind exactly twenty completed tracking products")
    index_path = args.output / "tracking-receipts.json"
    index_path.write_text(canonical(receipt_index))
    (args.output / "tracking-receipts.sha256").write_text(
        hashlib.sha256(index_path.read_bytes()).hexdigest() + "\n"
    )
    print(canonical({"output": str(path), "counts": manifest["counts"]}), end="")


if __name__ == "__main__":
    main()
