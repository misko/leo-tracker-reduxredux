"""Build a sanitized, causal DS8 TLE snapshot authority from public metadata."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path

LAG_NS = 505_000_000_000


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def build_authority(readiness, pose_dir: Path, tracking_store, archive):
    selected = readiness.get("selected", [])
    if len(selected) != 4 or len({row.get("session_id") for row in selected}) != 4:
        raise ValueError("readiness must contain exactly four unique sessions")
    sessions, selections = {}, []
    for row in selected:
        sid = row["session_id"]
        raw = tracking_store.load(sid)
        for key in ("input_manifest_sha256", "analysis_manifest_sha256"):
            if getattr(raw, key, None) != row[key]:
                raise ValueError(f"{sid}: public tracking {key} mismatch")
        start_ns = raw.timing.first_sample_estimate_utc_ns
        if not isinstance(start_ns, int):
            raise ValueError(f"{sid}: invalid public timing anchor")
        cutoff_ns = start_ns - LAG_NS
        snapshot = archive.select_latest_before(cutoff_ns)
        archive.read(snapshot)  # Reverify the bytes against the filename digest.
        if snapshot.collected_utc_ns >= cutoff_ns:
            raise ValueError(f"{sid}: selected snapshot is not strictly causal")
        pose = json.loads((pose_dir / f"{sid}.json").read_text())
        if pose.get("binding_digest") != row["pose_binding_digest"]:
            raise ValueError(f"{sid}: pose binding mismatch")
        site = pose.get("pose_authority", {})
        if not all(
            isinstance(site.get(key), (int, float))
            for key in ("latitude_deg", "longitude_deg")
        ):
            raise ValueError(f"{sid}: pose has no numeric site")
        sessions[sid] = {
            "input_manifest_sha256": row["input_manifest_sha256"],
            "analysis_manifest_sha256": row["analysis_manifest_sha256"],
            "site": {
                "latitude_deg": site["latitude_deg"],
                "longitude_deg": site["longitude_deg"],
            },
            "snapshot_digest": snapshot.digest,
        }
        selections.append(
            {
                "session_id": sid,
                "tracking_start_utc_ns": start_ns,
                "causal_cutoff_utc_ns": cutoff_ns,
                "snapshot_collected_utc_ns": snapshot.collected_utc_ns,
                "snapshot_digest": snapshot.digest,
                "provider": snapshot.provider,
                "strictly_before_cutoff": snapshot.collected_utc_ns < cutoff_ns,
            }
        )
    return {"sessions": sessions}, selections


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--pose-dir", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.receipt.exists():
        raise FileExistsError("authority output already exists")

    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    from leo.operations import adaptive_tle_position_inputs as preparation_module
    from leo.operations import tle_archive as archive_module
    from leo.operations.tle_archive import TleArchiveReader

    readiness_payload = args.readiness.read_bytes()
    readiness = json.loads(readiness_payload)
    store = ScannerTrackingInputStore(args.bulk_root)
    try:
        authority, selections = build_authority(
            readiness, args.pose_dir, store, TleArchiveReader(args.tle_root)
        )
    finally:
        store.close()
    sources = {}
    for module in (preparation_module, archive_module):
        path = Path(inspect.getsourcefile(module) or "")
        if not path.is_file():
            raise ValueError(f"cannot bind installed source for {module.__name__}")
        sources[module.__name__] = {"path": str(path), "sha256": digest(path.read_bytes())}
    args.output.write_text(json.dumps(authority, indent=2, allow_nan=False) + "\n")
    receipt = {
        "schema": "rx-ds8-snapshot-authority-receipt/v1",
        "selection_api": "TleArchiveReader.select_latest_before",
        "preparation_policy": "tracking_start_utc_ns - 505 seconds, strictly earlier",
        "readiness_sha256": digest(readiness_payload),
        "authority_sha256": digest(args.output.read_bytes()),
        "archive_root": str(args.tle_root),
        "selections": selections,
        "installed_sources": sources,
        "candidate_or_outcome_fields_inspected": False,
    }
    args.receipt.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
