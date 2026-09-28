#!/usr/bin/env python3
"""Bind the metadata-only four-rate geometry confirmation panel."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).resolve().parent
SOURCES = [
    ROOT / "reports/2026_09_27_roof_direction_subset/inventory.json",
    ROOT / "reports/2026_09_27_roof_balanced_confirmation/inventory.json",
    ROOT / "reports/2026_09_27_rx_disjoint_confirmation/inventory.json",
    ROOT / "reports/2026_09_27_roof_geometry_confirmation/inventory.json",
]
MANIFESTS = [
    ROOT / "reports/2026_09_27_roof_direction_subset/manifest.json",
    ROOT / "reports/2026_09_27_roof_balanced_confirmation/manifest.json",
    ROOT / "reports/2026_09_27_roof_geometry_confirmation/manifest.json",
]
PILOT = ROOT / "reports/2026_09_28_rx_training_forecast/partitions.json"
DS7 = ROOT / "reports/2026_09_27_ds7_post_ds6/manifest.json"
RATES = (2_500_000, 5_000_000, 7_500_000, 10_000_000)
SNAPSHOT_AUTHORITIES = {
    "scan-fw-40ebc07665464c7d": ROOT / "reports/2026_09_27_roof_geometry_confirmation/"
    "topology-search-scan-fw-40ebc07665464c7d.json",
    "scan-fw-f147dd8a5bc99346": ROOT / "reports/2026_09_27_roof_geometry_confirmation/"
    "topology-search-scan-fw-f147dd8a5bc99346.json",
    "scan-fw-b5604c3d838fa7ed": ROOT / "reports/2026_09_27_roof_geometry_confirmation/"
    "topology-search-scan-fw-b5604c3d838fa7ed.json",
    "scan-fw-339af454a2aab2f4": ROOT / "reports/2026_09_27_roof_balanced_confirmation/"
    "local-grid-scan-fw-339af454a2aab2f4.json",
}


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def validate_export_row(row: dict) -> None:
    """Validate fields consumed by rx_paired_opportunities.export_inventory."""
    required_strings = (
        "session_id",
        "cache_file",
        "cache_sha256",
        "input_manifest_sha256",
        "analysis_manifest_sha256",
        "split",
    )
    if any(not isinstance(row.get(key), str) or not row[key] for key in required_strings):
        raise ValueError("selected opportunity-export row lacks a required string")
    if row["split"] != "evaluation" or row.get("ready") is not True:
        raise ValueError("selected opportunity-export row must be ready evaluation evidence")
    if not isinstance(row.get("sample_rate_hz"), int) or row["sample_rate_hz"] <= 0:
        raise ValueError("selected opportunity-export row has invalid sample rate")


def validate_pipeline_manifest(manifest: dict, selected_ids: set[str]) -> None:
    sessions = manifest.get("sessions")
    if not isinstance(sessions, list) or len(sessions) != len(selected_ids):
        raise ValueError("pipeline manifest has invalid sessions")
    observed = set()
    for row in sessions:
        pose = row.get("pose")
        authority = pose.get("pose_authority") if isinstance(pose, dict) else None
        sid = pose.get("session_id") if isinstance(pose, dict) else None
        if (
            not isinstance(sid, str)
            or not isinstance(authority, dict)
            or not isinstance(authority.get("latitude_deg"), (int, float))
            or not isinstance(authority.get("longitude_deg"), (int, float))
            or row.get("split") != "evaluation"
        ):
            raise ValueError("pipeline manifest pose row is invalid")
        observed.add(sid)
    if observed != selected_ids:
        raise ValueError("pipeline manifest session IDs differ from selected inventory")


def main() -> None:
    pilot = json.loads(PILOT.read_text())
    pilot_ids = {row["session_id"] for row in pilot["recordings"]}
    ds7 = json.loads(DS7.read_text())
    ds7_ids = {row["session_id"] for row in ds7["captures"]}
    poses = {}
    ends = {}
    for path in MANIFESTS:
        for row in json.loads(path.read_text())["sessions"]:
            pose = row["pose"]
            poses[pose["session_id"]] = pose
            ends[pose["session_id"]] = pose["capture_end_utc_ns"]

    merged = {}
    memberships: dict[str, list[str]] = defaultdict(list)
    conflicts = []
    for source in SOURCES:
        for raw in json.loads(source.read_text()):
            sid = raw["session_id"]
            memberships[sid].append(str(source.relative_to(ROOT)))
            if not raw.get("ready") or not raw.get("cache_file"):
                continue
            cache = Path(raw["cache_file"])
            verified = cache.is_file() and digest(cache) == raw.get("cache_sha256")
            candidate = {
                "session_id": sid,
                "capture_start_utc_ns": raw.get("capture_start_utc_ns"),
                "capture_end_utc_ns": ends.get(sid),
                "sample_rate_hz": raw.get("sample_rate_hz"),
                "visits": raw.get("visits"),
                "probes": raw.get("probes"),
                "input_manifest_sha256": raw.get("input_manifest_sha256"),
                "analysis_manifest_sha256": raw.get("analysis_manifest_sha256"),
                "cache_file": str(cache),
                "cache_sha256": raw.get("cache_sha256"),
                "cache_hash_verified": verified,
                "ready": verified,
                "public_pickle_contract": "leo.contracts.scanner_tracking.TrackingInput",
                "pilot_overlap": sid in pilot_ids,
                "ds7_overlap": sid in ds7_ids,
                "historical_status": "previously inspected and analyzed",
            }
            old = merged.get(sid)
            if old and any(
                old[key] != candidate[key]
                for key in (
                    "input_manifest_sha256",
                    "analysis_manifest_sha256",
                    "cache_sha256",
                )
            ):
                conflicts.append(sid)
            elif old is None or candidate["capture_start_utc_ns"] is not None:
                merged[sid] = candidate
    for sid, row in merged.items():
        row["source_inventories"] = sorted(memberships[sid])
        pose = poses.get(sid)
        row["pose"] = None if pose is None else pose["pose_authority"]
        row["pose_binding_digest"] = None if pose is None else pose["binding_digest"]

    eligible = [
        row
        for row in merged.values()
        if row["cache_hash_verified"]
        and not row["pilot_overlap"]
        and row["sample_rate_hz"] in RATES
        and row["capture_start_utc_ns"] is not None
        and row["pose"] is not None
    ]
    selected = []
    for rate in RATES:
        rows = sorted(
            (row for row in eligible if row["sample_rate_hz"] == rate),
            key=lambda row: (row["capture_start_utc_ns"], row["session_id"]),
        )
        selected.append(rows[0])

    snapshot_receipts = {}
    snapshot_by_session = {}
    selected_by_id = {row["session_id"]: row for row in selected}
    if set(selected_by_id) != set(SNAPSHOT_AUTHORITIES):
        raise ValueError("selected panel differs from the frozen snapshot-authority panel")
    for sid, path in SNAPSHOT_AUTHORITIES.items():
        authority = json.loads(path.read_text())
        selected_row = selected_by_id[sid]
        expected = {
            "session_id": sid,
            "cache_sha256": selected_row["cache_sha256"],
            "input_manifest_sha256": selected_row["input_manifest_sha256"],
            "analysis_manifest_sha256": selected_row["analysis_manifest_sha256"],
        }
        if any(authority.get(key) != value for key, value in expected.items()):
            raise ValueError(f"historical snapshot authority binding mismatch: {sid}")
        snapshot = authority.get("snapshot_digest")
        if not isinstance(snapshot, str) or not snapshot.startswith("sha256:"):
            raise ValueError(f"historical snapshot authority lacks digest: {sid}")
        snapshot_by_session[sid] = snapshot
        snapshot_receipts[sid] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": digest(path),
            "fields_read": [
                "session_id",
                "cache_sha256",
                "input_manifest_sha256",
                "analysis_manifest_sha256",
                "snapshot_digest",
            ],
        }
    if len(set(snapshot_by_session.values())) != 1:
        raise ValueError("selected records do not share one historical causal snapshot")
    document = {
        "schema": "rx-geometry-confirmation-inventory/v1",
        "selection_rule": (
            "For each supported rate ascending, select earliest capture_start_utc_ns then "
            "session_id among hash-valid, pose-bound, pilot-disjoint existing derived caches."
        ),
        "outcomes_used_for_selection": False,
        "source_digests": {str(path.relative_to(ROOT)): digest(path) for path in SOURCES},
        "pilot_partitions_sha256": digest(PILOT),
        "ds7_manifest_sha256": digest(DS7),
        "snapshot_authority_source_receipts": snapshot_receipts,
        "conflicting_cache_bindings": sorted(set(conflicts)),
        "counts": {
            "unique_sessions": len(merged),
            "eligible_sessions": len(eligible),
            "selected": 4,
        },
        "selected_session_ids": [row["session_id"] for row in selected],
        "selected_inventory": [{**row, "split": "evaluation"} for row in selected],
        "pipeline_manifest": {
            "sessions": [
                {"pose": {**poses[row["session_id"]]}, "split": "evaluation"} for row in selected
            ]
        },
        "snapshot_authority": {
            "sessions": {
                row["session_id"]: {
                    "input_manifest_sha256": row["input_manifest_sha256"],
                    "analysis_manifest_sha256": row["analysis_manifest_sha256"],
                    "snapshot_digest": snapshot_by_session[row["session_id"]],
                    "site": {
                        "latitude_deg": row["pose"]["latitude_deg"],
                        "longitude_deg": row["pose"]["longitude_deg"],
                    },
                }
                for row in selected
            }
        },
        "all_sessions": sorted(merged.values(), key=lambda row: row["session_id"]),
    }
    corrected_inventory = document["selected_inventory"]
    for row in corrected_inventory:
        validate_export_row(row)
    validate_pipeline_manifest(document["pipeline_manifest"], set(selected_by_id))
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "inventory.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    exports = {
        "selected-inventory-corrected.json": corrected_inventory,
        "manifest.json": document["pipeline_manifest"],
        "snapshot-authority.json": document["snapshot_authority"],
    }
    for name, value in exports.items():
        (REPORT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
