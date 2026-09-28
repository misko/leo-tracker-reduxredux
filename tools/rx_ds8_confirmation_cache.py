"""Package frozen DS8 public tracking inputs for receiver confirmation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DS8 = ROOT / "reports/2026_09_28_ds8_post_ds7/manifest.json"
DEFAULT_POSES = ROOT / "reports/2026_09_28_ds8_post_ds7/pose"


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def validate_pose(pose: dict, expected: dict) -> None:
    body = {key: value for key, value in pose.items() if key != "binding_digest"}
    if digest(canonical(body)) != pose.get("binding_digest"):
        raise ValueError("invalid pose binding digest")
    authority = pose.get("pose_authority", {})
    if digest(canonical(authority)) != pose.get("pose_authority_digest"):
        raise ValueError("invalid pose authority digest")
    if (
        pose.get("session_id") != expected["session_id"]
        or pose.get("manifest_sha256") != expected["input_manifest_sha256"]
        or pose.get("binding_digest") != expected["pose_binding_digest"]
        or authority.get("revision") != expected["pose_revision"]
    ):
        raise ValueError("pose/readiness binding mismatch")
    if not (
        authority["valid_from_utc_ns"] <= expected["capture_start_utc_ns"]
        and expected["capture_end_utc_ns"] <= authority["valid_until_utc_ns"]
    ):
        raise ValueError("pose authority does not cover capture")


def validate_tracking(raw, row: dict, expected_visits: set[int]) -> None:
    for name in ("session_id", "input_manifest_sha256", "analysis_manifest_sha256"):
        if getattr(raw, name, None) != row[name]:
            raise ValueError(f"{row['session_id']}: {name} mismatch")
    if raw.__class__.__module__ + "." + raw.__class__.__name__ != row["tracking_contract"]:
        raise ValueError(f"{row['session_id']}: public contract mismatch")
    if raw.qualified is not True or raw.sample_rate_hz != row["sample_rate_hz"]:
        raise ValueError(f"{row['session_id']}: qualification or sample rate mismatch")
    probes = list(raw.probes)
    if len(probes) != row["probes"]:
        raise ValueError(f"{row['session_id']}: probe count mismatch")
    if {probe.visit_index for probe in probes} != expected_visits:
        raise ValueError(f"{row['session_id']}: incomplete visit membership")
    keyed = {
        (probe.visit_index, probe.probe_index, probe.probe_start_ms, probe.receiver_id): probe
        for probe in probes
    }
    identities = {
        (probe.visit_index, probe.probe_index, probe.receiver_id) for probe in probes
    }
    if len(keyed) != len(probes) or len(identities) != len(probes):
        raise ValueError(f"{row['session_id']}: duplicate probes")
    for probe in probes:
        if (
            probe.receiver_id not in (0, 1)
            or not isinstance(probe.valid_start_counter, int)
            or probe.valid_start_counter < 0
            or not math.isfinite(float(probe.actual_rf_hz))
            or float(probe.actual_rf_hz) <= 0
        ):
            raise ValueError(f"{row['session_id']}: invalid receiver/RF/timestamp metadata")
        other = keyed.get(
            (probe.visit_index, probe.probe_index, probe.probe_start_ms, 1 - probe.receiver_id)
        )
        comparable = ("channel", "edge", "valid_start_counter", "actual_rf_hz")
        if other is None or any(
            getattr(probe, name) != getattr(other, name) for name in comparable
        ):
            raise ValueError(f"{row['session_id']}: missing or nonsimultaneous receiver pair")


def package(
    readiness,
    ds8,
    poses_dir: Path,
    output_dir: Path,
    tracking_store,
    capture_store,
    source_hashes=None,
):
    """Validate and exclusively serialize the frozen four-record panel."""
    if readiness.get("schema") != "rx-ds8-confirmation-readiness/v1":
        raise ValueError("unsupported readiness schema")
    selected = readiness.get("selected", [])
    if len(selected) != 4 or len({row["session_id"] for row in selected}) != 4:
        raise ValueError("readiness must contain four unique sessions")
    if source_hashes is not None:
        expected_ds8 = readiness.get("source_sha256", {}).get("ds8_manifest")
        actual_ds8 = source_hashes["ds8_manifest"].removeprefix("sha256:")
        if expected_ds8 != actual_ds8:
            raise ValueError("readiness/DS8 manifest payload hash mismatch")
    captures = {row["session_id"]: row for row in ds8.get("captures", [])}
    prepared = []
    for row in selected:
        sid = row["session_id"]
        sealed = captures.get(sid)
        if sealed is None or any(
            sealed[key] != row[target]
            for key, target in (
                ("manifest_sha256", "input_manifest_sha256"),
                ("sample_rate_hz", "sample_rate_hz"),
                ("capture_start_utc_ns", "capture_start_utc_ns"),
                ("capture_end_utc_ns", "capture_end_utc_ns"),
            )
        ):
            raise ValueError(f"{sid}: sealed DS8 metadata mismatch")
        if (
            sealed.get("terminal_state") != "completed"
            or sealed.get("terminal_error_code") != 0
            or not sealed.get("utc_qualified")
            or sealed.get("receiver_ids") != [0, 1]
        ):
            raise ValueError(f"{sid}: sealed capture is incomplete")
        pose_path = poses_dir / f"{sid}.json"
        pose_payload = pose_path.read_bytes()
        if digest(pose_payload) != sealed["pose_file_sha256"]:
            raise ValueError(f"{sid}: pose file digest mismatch")
        pose = json.loads(pose_payload)
        validate_pose(pose, row)
        capture = capture_store.inspect(sid)
        if capture.manifest_sha256 != row["input_manifest_sha256"]:
            raise ValueError(f"{sid}: capture store manifest mismatch")
        expected_visits = {event.visit_index for event in capture.manifest.receipt.events}
        if len(expected_visits) != sealed["visits"]:
            raise ValueError(f"{sid}: sealed visit count mismatch")
        raw = tracking_store.load(sid)
        validate_tracking(raw, row, expected_visits)
        payload = pickle.dumps(raw, protocol=5)
        prepared.append((row, pose, digest(pose_payload), payload))

    output_dir.mkdir(parents=True, exist_ok=False)
    cache_dir = output_dir / "cache"
    cache_dir.mkdir()
    inventory, sessions = [], []
    for row, pose, pose_digest, payload in prepared:
        cache_path = cache_dir / f"{row['session_id']}.pickle"
        with cache_path.open("xb") as stream:
            stream.write(payload)
        inventory.append(
            {
                "session_id": row["session_id"],
                "ready": True,
                "split": "evaluation",
                "sample_rate_hz": row["sample_rate_hz"],
                "input_manifest_sha256": row["input_manifest_sha256"],
                "analysis_manifest_sha256": row["analysis_manifest_sha256"],
                "cache_file": str(cache_path.resolve()),
                "cache_sha256": digest(payload),
            }
        )
        sessions.append(
            {
                "split": "evaluation",
                "pose": pose,
                "pose_file_sha256": pose_digest,
                "cache_sha256": digest(payload),
                "analysis_manifest_sha256": row["analysis_manifest_sha256"],
            }
        )
    (output_dir / "inventory.json").write_text(
        json.dumps(inventory, indent=2, allow_nan=False) + "\n"
    )
    receipt = {
        "schema": "rx-ds8-confirmation-cache/v1",
        "status": "complete",
        "sessions": sessions,
        "readiness_sha256": (source_hashes or {}).get(
            "readiness", digest(canonical(readiness))
        ),
        "ds8_manifest_sha256": (source_hashes or {}).get(
            "ds8_manifest", digest(canonical(ds8))
        ),
        "candidate_or_outcome_fields_inspected": False,
        "public_contract": "leo.contracts.scanner_tracking.TrackingInput",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(receipt, indent=2, allow_nan=False) + "\n"
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ds8-manifest", type=Path, default=DEFAULT_DS8)
    parser.add_argument("--pose-dir", type=Path, default=DEFAULT_POSES)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    readiness_payload = args.readiness.read_bytes()
    ds8_payload = args.ds8_manifest.read_bytes()
    readiness = json.loads(readiness_payload)
    expected_ds8 = readiness.get("source_sha256", {}).get("ds8_manifest")
    if expected_ds8 != hashlib.sha256(ds8_payload).hexdigest():
        raise ValueError("readiness/DS8 manifest payload hash mismatch")
    tracking = ScannerTrackingInputStore(args.bulk_root)
    captures = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    try:
        result = package(
            readiness,
            json.loads(ds8_payload),
            args.pose_dir,
            args.output_dir,
            tracking,
            captures,
            {
                "readiness": digest(readiness_payload),
                "ds8_manifest": digest(ds8_payload),
            },
        )
    finally:
        tracking.close()
        captures.close()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
