#!/usr/bin/env python3
"""Bind the frozen DS3 capture inventory to receipt-bound inference inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DS2_MANIFEST = HERE.parent / "2026_09_24_ds2_sep24_rerun_22/manifest.json"
DEFAULT_CACHE = Path("/var/tmp/leo-ds3-sep24-until-223658-cache")
GEOMETRY_PLAN = HERE / "geometry-cone-plan.json"
FIXTURE_DIGEST = "sha256:6e6f8798e1465691fdb6ad973bc37443651408c4060f091144b1a470fb0817a4"


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def build(
    inventory_path: Path, cache_root: Path, ds2_path: Path, geometry_plan_path: Path
) -> dict[str, Any]:
    inventory = load(inventory_path)
    if inventory.get("schema") != "ds3-all-captures-admission/v1":
        raise ValueError("unexpected DS3 inventory schema")
    if inventory.get("reference_coordinate_present") is not False:
        raise ValueError("DS3 inventory must not contain a reference coordinate")
    captures = inventory.get("captures")
    if not isinstance(captures, list) or len(captures) != 56:
        raise ValueError("the frozen DS3 inventory must contain exactly 56 captures")

    ds2 = load(ds2_path)
    prior_geometry = {
        row["session_id"]: row["receiver_geometry"]
        for row in ds2.get("sessions", [])
        if isinstance(row, dict)
        and isinstance(row.get("receiver_geometry"), dict)
        and row["receiver_geometry"].get("eligibility") == "conditional_provisional_mapping"
    }
    geometry_plan = load(geometry_plan_path)
    if geometry_plan.get("schema") != "ds3-lt3d-geometry-cone-plan/v1":
        raise ValueError("unexpected DS3 geometry plan schema")
    geometry: dict[str, dict[str, Any]] = {}
    for row in geometry_plan.get("captures", []):
        if not isinstance(row, dict) or row.get("status") != "eligible":
            continue
        session_id = str(row["session_id"])
        if session_id in prior_geometry:
            geometry[session_id] = prior_geometry[session_id]
            continue
        mapping = row["mapping_hypotheses"][0]
        geometry[session_id] = {
            "eligibility": "conditional_provisional_mapping",
            "capture_binding_digest": row["binding_digest"],
            "fixture_digest": FIXTURE_DIGEST,
            "fixture_part_id": row["fixture_part_id"],
            "station_geometry_digest": row["station_geometry_digest"],
            "assignments": [
                {
                    "receiver_id": receiver_id,
                    "slot_id": mapping[str(receiver_id)],
                    "mapping_status": "provisional",
                }
                for receiver_id in (0, 1)
            ],
            "mapping_uncertainty": {
                "status": "provisional",
                "required_treatment": "symmetric_two_mapping_marginalization",
            },
            "model_use": "geometry and cone diagnostics only",
        }
    sessions: list[dict[str, Any]] = []
    groups: defaultdict[tuple[str, int], list[str]] = defaultdict(list)
    tracks = observations = 0
    for capture in captures:
        if capture.get("admission_status") != "included":
            raise ValueError(f"capture is not admitted: {capture.get('session_id')}")
        session_id = str(capture["session_id"])
        receipt_path = cache_root / session_id / "cache_receipt.json"
        state_path = cache_root / session_id / "state_cache.npz"
        if not receipt_path.is_file() or not state_path.is_file():
            raise ValueError(f"cache is incomplete: {session_id}")
        receipt = load(receipt_path)
        evidence = receipt.get("prepared_evidence", {})
        if receipt.get("session_id") != session_id:
            raise ValueError(f"cache session mismatch: {session_id}")
        if receipt.get("bindings", {}).get("state_cache") != digest(state_path):
            raise ValueError(f"cache state digest mismatch: {session_id}")
        if evidence.get("input_manifest_sha256") != capture.get("recording_manifest_digest"):
            raise ValueError(f"cache input digest mismatch: {session_id}")
        track_count = int(evidence.get("eligible_track_count", 0))
        observation_count = int(evidence.get("eligible_observation_count", 0))
        if track_count <= 0 or observation_count <= 0:
            raise ValueError(f"cache has no eligible evidence: {session_id}")
        tracks += track_count
        observations += observation_count
        row: dict[str, Any] = {
            "session_id": session_id,
            "captured_at": capture["capture_start_utc"],
            "radio_id": capture["radio_id"],
            "sample_rate_hz": capture["sample_rate_hz"],
            "input_manifest_sha256": capture["recording_manifest_digest"],
            "tracking": {
                "status": "complete",
                "tracking_product_digest": evidence["analysis_manifest_sha256"],
                "cache": {
                    "status": "materialized",
                    "receipt_sha256": digest(receipt_path),
                    "state_sha256": digest(state_path),
                    "eligible_track_count": track_count,
                    "eligible_observation_count": observation_count,
                },
            },
        }
        if session_id in geometry:
            row["receiver_geometry"] = geometry[session_id]
        sessions.append(row)
        groups[(str(capture["radio_id"]), int(capture["sample_rate_hz"]))].append(session_id)

    sessions.sort(key=lambda row: (row["captured_at"], row["session_id"]))
    cohorts = [
        {
            "cohort_id": f"{radio}-{rate}",
            "radio_id": radio,
            "sample_rate_hz": rate,
            "session_count": len(ids),
            "session_ids": sorted(ids),
            "geometry_session_ids": sorted(sid for sid in ids if sid in geometry),
            "joint_inference_eligible": len(ids) > 1,
        }
        for (radio, rate), ids in sorted(groups.items())
    ]
    return {
        "schema": "ds2-whole-corpus-manifest/v1",
        "dataset_name": "DS3",
        "manifest_sealed": True,
        "whole_session_policy": "all 56 frozen captures included once",
        "reference_coordinate_in_manifest": False,
        "position_evaluation": "external_post_inference_only",
        "position_initialization": "no coordinate is bound by this corpus manifest",
        "audit_observed_utc": inventory["audit_observed_utc"],
        "capture_cutoff_utc": inventory["capture_cutoff_utc"],
        "source_inventory_sha256": digest(inventory_path),
        "sessions": sessions,
        "cohorts": cohorts,
        "geometry_policy": {
            "eligible_sessions": sorted(geometry),
            "binding_count": len(geometry),
            "other_sessions": "not geometry eligible",
        },
        "counts": {
            "sessions": len(sessions),
            "eligible_tracks": tracks,
            "eligible_observations": observations,
            "cohorts": len(cohorts),
            "geometry_conditional_sessions": len(geometry),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=HERE / "manifest.json")
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--ds2-manifest", type=Path, default=DS2_MANIFEST)
    parser.add_argument("--geometry-plan", type=Path, default=GEOMETRY_PLAN)
    parser.add_argument("--output", type=Path, default=HERE / "inference-manifest.json")
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(args.output.suffix + ".sha256").exists():
        raise FileExistsError(f"refusing to replace sealed output: {args.output}")
    value = canonical(
        build(args.inventory, args.cache_root, args.ds2_manifest, args.geometry_plan)
    )
    args.output.write_text(value)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(value.encode()).hexdigest() + "\n"
    )


if __name__ == "__main__":
    main()
