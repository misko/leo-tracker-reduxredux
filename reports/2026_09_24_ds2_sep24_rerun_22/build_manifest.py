#!/usr/bin/env python3
"""Seal the DS2 September 24 successor corpus from 20 sealed + 2 V14 products.

This is deliberately an offline merger.  The first twenty receipts are copied
from the sealed DS2 report and the two additions are read from their completed,
report-local V14 documents.  No scanner endpoint, observer site, or reference
coordinate is consulted or persisted.
"""

# Long persisted-contract strings are intentionally kept intact for auditability.
# ruff: noqa: E501
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_09_24_ds2_final_manifest"
TRACKING_ROOT = (
    HERE.parent
    / "2026_09_24_variable_dwell_backfill"
    / "tracking/scanner-shared-tracking-v14"
)
RAW_ROOT = Path("/srv/bulk/leo/scanner-adaptive-recordings")
ADDITIONAL_SESSION_IDS = (
    "scan-fw-294be7850b76a34d",
    "scan-fw-ff02a0ba4200d0dc",
)
EXPECTED_SOURCE_SESSIONS = 20
EXPECTED_SESSIONS = 22
GEOMETRY_SESSION_IDS = {
    "scan-fw-f3ce5fe73aa40506",
    "scan-fw-9f3d5067d149118e",
    "scan-fw-cfcf667726e80735",
}


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical(value).encode())


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def utc_from_ns(value: Any) -> str:
    if not isinstance(value, int):
        raise ValueError("capture manifest has no integer first-sample UTC")
    return datetime.fromtimestamp(value / 1_000_000_000, UTC).isoformat().replace("+00:00", "Z")


def coordinate_free(value: Any) -> bool:
    """Reject accidental observer or reference-coordinate propagation."""
    forbidden = {"observer_site", "reference_coordinate", "center_wgs84", "latitude_deg", "longitude_deg"}
    if isinstance(value, dict):
        return all(key not in forbidden and coordinate_free(item) for key, item in value.items())
    if isinstance(value, list):
        return all(coordinate_free(item) for item in value)
    return True


def source_inputs(source_manifest: dict[str, Any], receipt_index: dict[str, Any]) -> list[dict[str, Any]]:
    if source_manifest.get("schema") != "ds2-whole-corpus-manifest/v1":
        raise ValueError("source must be the sealed DS2 whole-corpus v1 manifest")
    if source_manifest.get("manifest_sealed") is not True:
        raise ValueError("source DS2 manifest is not sealed")
    sessions = source_manifest.get("sessions")
    if not isinstance(sessions, list) or len(sessions) != EXPECTED_SOURCE_SESSIONS:
        raise ValueError("source DS2 manifest must contain exactly twenty sessions")
    ids = [row.get("session_id") for row in sessions if isinstance(row, dict)]
    if len(ids) != EXPECTED_SOURCE_SESSIONS or len(set(ids)) != EXPECTED_SOURCE_SESSIONS:
        raise ValueError("source DS2 session IDs are invalid")
    receipts = receipt_index.get("receipts")
    if not isinstance(receipts, dict) or set(receipts) != set(ids):
        raise ValueError("source receipt index does not bind exactly the source sessions")
    if set(ids) & set(ADDITIONAL_SESSION_IDS):
        raise ValueError("new sessions already occur in the sealed source corpus")
    return sessions


def safe_receipt(product: dict[str, Any]) -> dict[str, Any]:
    """Retain content-addressed V14 evidence while removing observer details."""
    return {
        "schema": "ds2-authoritative-tracking-receipt/v1",
        "session_id": product.get("session_id"),
        "state": "complete",
        "phase": "complete",
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


def additional_input(session_id: str, raw_envelope: dict[str, Any], tracking_envelope: dict[str, Any]) -> dict[str, Any]:
    raw = raw_envelope.get("manifest")
    product = tracking_envelope.get("document")
    if not isinstance(raw, dict) or not isinstance(product, dict):
        raise ValueError(f"{session_id}: expected raw and V14 document envelopes")
    if raw.get("session_id") != session_id or product.get("session_id") != session_id:
        raise ValueError(f"{session_id}: source session ID mismatch")
    raw_digest = raw_envelope.get("sha256")
    if not isinstance(raw_digest, str) or product.get("input_manifest_sha256") != raw_digest:
        raise ValueError(f"{session_id}: V14 input digest does not bind its raw capture")
    if product.get("schema_version") != 14 or product.get("analysis_id") != "scanner-shared-tracking-v14":
        raise ValueError(f"{session_id}: not a V14 tracking product")
    if product.get("trajectory_state") != "complete" or product.get("tle_state") != "complete":
        raise ValueError(f"{session_id}: V14 tracking product is not complete")
    if not product.get("analysis_manifest_sha256") or not product.get("tle_match_config_digest"):
        raise ValueError(f"{session_id}: V14 tracking product lacks required digests")
    timing = raw.get("timing")
    receipt = raw.get("receipt")
    if not isinstance(timing, dict) or not isinstance(receipt, dict):
        raise ValueError(f"{session_id}: raw manifest lacks timing or capture receipt")
    if timing.get("qualified") is not True or receipt.get("source_span_attested") is not True:
        raise ValueError(f"{session_id}: raw capture is not qualified and attested")
    if (receipt.get("terminal") or {}).get("state") != "completed":
        raise ValueError(f"{session_id}: raw capture did not complete")
    if timing.get("sample_rate_hz") != product.get("sample_rate_hz"):
        raise ValueError(f"{session_id}: raw and V14 sample rates differ")
    radio_id = receipt.get("radio_id")
    if not isinstance(radio_id, str):
        raise ValueError(f"{session_id}: raw receipt has no radio ID")
    return {
        "session_id": session_id,
        "captured_at": utc_from_ns(timing.get("first_sample_estimate_utc_ns")),
        "radio_id": radio_id,
        "sample_rate_hz": timing["sample_rate_hz"],
        "input_manifest_sha256": raw_digest,
        "tracking_product_digest": product["analysis_manifest_sha256"],
        "candidate_policy_digest": product["tle_match_config_digest"],
        "receipt": safe_receipt(product),
        "raw_capture": {
            "manifest_sha256": raw_digest,
            "uncompressed_sha256": raw.get("uncompressed_sha256"),
            "uncompressed_bytes": raw.get("uncompressed_bytes"),
            "total_sample_count": raw.get("total_sample_count"),
            "timing_qualified": True,
            "source_span_attested": True,
        },
    }


def cohorts(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: defaultdict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for session in sessions:
        grouped[(str(session["radio_id"]), int(session["sample_rate_hz"]))].append(session)
    return [
        {
            "cohort_id": f"{radio_id}-{sample_rate_hz}",
            "radio_id": radio_id,
            "sample_rate_hz": sample_rate_hz,
            "session_ids": [item["session_id"] for item in rows],
            "session_count": len(rows),
            "joint_inference_eligible": len(rows) >= 2,
            "geometry_session_ids": [
                item["session_id"]
                for item in rows
                if item["receiver_geometry"]["eligibility"] == "conditional_provisional_mapping"
            ],
        }
        for (radio_id, sample_rate_hz), rows in sorted(grouped.items())
    ]


def assemble(
    source_manifest: dict[str, Any],
    receipt_index: dict[str, Any],
    source_receipts: dict[str, dict[str, Any]],
    additions: list[dict[str, Any]],
    *,
    source_manifest_digest: str,
    source_receipt_index_digest: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    source_rows = source_inputs(source_manifest, receipt_index)
    if set(source_receipts) != {row["session_id"] for row in source_rows}:
        raise ValueError("source receipt files do not match source manifest membership")
    if [item["session_id"] for item in additions] != list(ADDITIONAL_SESSION_IDS):
        raise ValueError("successor must admit the two designated additional sessions once each")
    policies = {
        row.get("tracking", {}).get("candidate_policy_digest")
        for row in source_rows
        if isinstance(row.get("tracking"), dict)
        and isinstance(row["tracking"].get("candidate_policy_digest"), str)
    }
    policies.update(item["candidate_policy_digest"] for item in additions)
    if len(policies) != 1:
        raise ValueError("all twenty-two V14 products must share one candidate policy")

    receipts = dict(source_receipts)
    sessions: list[dict[str, Any]] = []
    for row in source_rows:
        session_id = row["session_id"]
        geometry = row.get("receiver_geometry")
        if session_id in GEOMETRY_SESSION_IDS:
            if not isinstance(geometry, dict) or geometry.get("eligibility") != "conditional_provisional_mapping":
                raise ValueError(f"{session_id}: original explicit geometry binding is unavailable")
            safe_geometry = geometry
        else:
            safe_geometry = {
                "eligibility": "unavailable",
                "reason": "no_explicit_capture_time_receiver_geometry",
            }
        receipt = source_receipts[session_id]
        if receipt.get("session_id") != session_id or receipt.get("state") != "complete":
            raise ValueError(f"{session_id}: source receipt is not a complete authoritative receipt")
        sessions.append(
            {
                "session_id": session_id,
                "captured_at": row["captured_at"],
                "radio_id": row["radio_id"],
                "sample_rate_hz": row["sample_rate_hz"],
                "input_manifest_sha256": row["input_manifest_sha256"],
                "tracking": {
                    "status": "complete",
                    "tracking_product_digest": row["tracking"]["tracking_product_digest"],
                    "candidate_policy_digest": row["tracking"]["candidate_policy_digest"],
                    "receipt_path": f"tracking_receipts/{session_id}.json",
                    "cache": {"status": "not_materialized", "reason": "successor cache is not yet built"},
                },
                "receiver_geometry": safe_geometry,
            }
        )
    for item in additions:
        session_id = item["session_id"]
        receipts[session_id] = item["receipt"]
        sessions.append(
            {
                "session_id": session_id,
                "captured_at": item["captured_at"],
                "radio_id": item["radio_id"],
                "sample_rate_hz": item["sample_rate_hz"],
                "input_manifest_sha256": item["input_manifest_sha256"],
                "tracking": {
                    "status": "complete",
                    "tracking_product_digest": item["tracking_product_digest"],
                    "candidate_policy_digest": item["candidate_policy_digest"],
                    "receipt_path": f"tracking_receipts/{session_id}.json",
                    "cache": {"status": "not_materialized", "reason": "successor cache is not yet built"},
                },
                "raw_capture": item["raw_capture"],
                "receiver_geometry": {
                    "eligibility": "unavailable",
                    "reason": "successor admission preserves only the original three DS2 explicit bindings",
                },
            }
        )
    sessions.sort(key=lambda row: (row["captured_at"], row["session_id"]))
    if len(sessions) != EXPECTED_SESSIONS or len({row["session_id"] for row in sessions}) != EXPECTED_SESSIONS:
        raise ValueError("successor membership must contain exactly twenty-two unique sessions")
    admission = {
        "schema": "ds2-successor-admission-plan/v1",
        "source_corpus": {
            "session_count": EXPECTED_SOURCE_SESSIONS,
            "manifest_sha256": source_manifest_digest,
            "receipt_index_sha256": source_receipt_index_digest,
        },
        "new_session_admissions": [
            {
                "session_id": item["session_id"],
                "raw_manifest_sha256": item["input_manifest_sha256"],
                "tracking_product_digest": item["tracking_product_digest"],
                "candidate_policy_digest": item["candidate_policy_digest"],
                "requirements": [
                    "qualified and source-span-attested raw capture",
                    "completed report-local V14 trajectory and TLE matching",
                    "V14 input digest equals raw manifest digest",
                ],
                "geometry_admission": "not admitted; retain only the original three DS2 geometry bindings",
            }
            for item in additions
        ],
        "reference_coordinate_present": False,
        "whole_session_policy": "each admitted capture appears once; no train_validation_test_partition",
    }
    manifest = {
        "schema": "ds2-whole-corpus-manifest/v1",
        "manifest_sealed": True,
        "corpus_role": "development_evaluation_only",
        "successor_of": "ds2-whole-corpus-manifest/v1",
        "whole_session_policy": "every admitted capture is included once; no train_validation_test_partition",
        "reference_coordinate_in_manifest": False,
        "position_evaluation": "external_post_inference_only",
        "position_initialization": "no coordinate is bound by this corpus manifest",
        "source_manifest_sha256": source_manifest_digest,
        "source_tracking_receipt_index_sha256": source_receipt_index_digest,
        "admission_plan_sha256": sha256_json(admission),
        "candidate_policy_digest": next(iter(policies)),
        "association_policy": {
            "input": "sealed V14 tracklet and candidate-review evidence",
            "blind_inference_requirement": "recompute candidate predictions at every tested geographic cell; do not freeze a prior location's candidate identities",
            "identity_claims_permitted": False,
        },
        "sessions": sessions,
        "cohorts": cohorts(sessions),
        "geometry_policy": {
            "ordinary_models": "all 22 completed sessions",
            "geometry_and_cone_models": "only the original three explicit capture-time bindings",
            "eligible_sessions": sorted(GEOMETRY_SESSION_IDS),
            "mapping_policy": "symmetric_two_mapping_marginalization required",
            "other_sessions": "not geometry eligible; do not infer fixture from radio identity or later raw metadata",
        },
        "counts": {
            "sessions": len(sessions),
            "completed_tracking_products": len(sessions),
            "cohorts": len(cohorts(sessions)),
            "geometry_conditional_sessions": len(GEOMETRY_SESSION_IDS),
            "newly_admitted_sessions": len(additions),
        },
    }
    if not coordinate_free(admission) or not coordinate_free(manifest) or not all(coordinate_free(row) for row in receipts.values()):
        raise ValueError("successor output must not contain a coordinate")
    return manifest, admission, receipts


def write_sealed(path: Path, value: Any) -> str:
    content = canonical(value).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(digest + "\n")
    return "sha256:" + digest


def build(source: Path, tracking_root: Path, raw_root: Path, output: Path) -> dict[str, Any]:
    source_manifest_path = source / "manifest.json"
    source_index_path = source / "tracking-receipts.json"
    source_manifest = read_object(source_manifest_path)
    receipt_index = read_object(source_index_path)
    source_receipts = {
        session_id: read_object(source / "tracking_receipts" / f"{session_id}.json")
        for session_id in receipt_index.get("receipts", {})
    }
    additions = [
        additional_input(
            session_id,
            read_object(raw_root / session_id / "manifest.json"),
            read_object(tracking_root / session_id / "manifest.json"),
        )
        for session_id in ADDITIONAL_SESSION_IDS
    ]
    manifest, admission, receipts = assemble(
        source_manifest,
        receipt_index,
        source_receipts,
        additions,
        source_manifest_digest=sha256_bytes(source_manifest_path.read_bytes()),
        source_receipt_index_digest=sha256_bytes(source_index_path.read_bytes()),
    )
    for session_id, receipt in sorted(receipts.items()):
        write_sealed(output / "tracking_receipts" / f"{session_id}.json", receipt)
    manifest_digest = write_sealed(output / "manifest.json", manifest)
    admission_digest = write_sealed(output / "admission-plan.json", admission)
    receipt_index_value = {
        "schema": "ds2-authoritative-tracking-receipt-index/v1",
        "manifest_sha256": manifest_digest,
        "receipts": {
            path.stem: sha256_bytes(path.read_bytes())
            for path in sorted((output / "tracking_receipts").glob("scan-fw-*.json"))
        },
    }
    if len(receipt_index_value["receipts"]) != EXPECTED_SESSIONS:
        raise RuntimeError("successor receipt index must bind exactly twenty-two receipts")
    receipt_index_digest = write_sealed(output / "tracking-receipts.json", receipt_index_value)
    return {
        "manifest": manifest_digest,
        "admission_plan": admission_digest,
        "tracking_receipt_index": receipt_index_digest,
        "counts": manifest["counts"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--tracking-root", type=Path, default=TRACKING_ROOT)
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    print(canonical(build(args.source, args.tracking_root, args.raw_root, args.output)), end="")


if __name__ == "__main__":
    main()
