"""Read-only six-hour audit through deployed recording/position reader ports.

Run with the deployed regional worker source on PYTHONPATH. Emit JSON to stdout;
no IQ is read, no services are changed, and no capture or fit is launched.
"""

import datetime as dt
import hashlib
import json
from pathlib import Path

from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.regional_position import RegionalPositionStore


START = dt.datetime.fromisoformat("2026-10-06T18:30:00+00:00").timestamp()
END = dt.datetime.fromisoformat("2026-10-07T00:30:00+00:00").timestamp()
ROOT = Path("/srv/bulk/leo")


def main():
    recording_root = ROOT / "scanner-adaptive-recordings"
    recordings = AdaptiveHopIqStore(ROOT, read_only=True)
    positions = RegionalPositionStore(ROOT)
    rows, errors = [], []
    try:
        # Directory enumeration is inventory only; reader ports validate products.
        for directory in sorted(recording_root.iterdir()):
            if not directory.is_dir() or directory.stat().st_mtime < START - 600:
                continue
            try:
                recording = recordings.inspect(directory.name)
            except Exception as error:
                errors.append({"session_id": directory.name, "error": str(error)})
                continue
            manifest = recording.manifest.model_dump(mode="json")
            timing = manifest.get("timing")
            if not timing:
                continue
            start = timing["first_sample_estimate_utc_ns"] / 1e9
            if not START <= start < END:
                continue
            receipt = manifest["receipt"]
            row = {
                "session_id": directory.name,
                "capture_start_s": start,
                "capture_start_utc": dt.datetime.fromtimestamp(start, dt.UTC).isoformat(),
                "timing": timing,
                "recording_manifest_sha256": recording.manifest_sha256,
                "terminal": receipt["terminal"],
                "capture_accounting": {
                    k: v for k, v in receipt.items()
                    if k.endswith("sample_count") or k in ("valid_duty_ppm", "complete_visit_count")
                },
                "geometry": receipt["plan"]["geometry"],
                "regional_status": "pending",
            }
            for namespace in ("scanner-shared-tracking-v15",):
                path = ROOT / namespace / directory.name / "manifest.json"
                row[namespace + "_published_s"] = path.stat().st_mtime if path.exists() else None
            status = positions.status(directory.name)
            row["regional_status"] = status.state
            if status.manifest:
                doc = status.manifest.document
                assert doc.input_manifest_sha256 == recording.manifest_sha256
                row["regional_document_sha256"] = status.manifest.document_sha256
                row["regional_document"] = doc.model_dump(mode="json")
                row["regional_published_s"] = (
                    ROOT / positions.namespace / directory.name / "manifest.json"
                ).stat().st_mtime
                row["artifact_hashes_verified"] = {
                    name: hashlib.sha256(positions.artifact(directory.name, name)).hexdigest()
                    for name in ("T1AT", "V16")
                }
            rows.append(row)
    finally:
        recordings.close()
    print(json.dumps({
        "snapshot_utc": dt.datetime.now(dt.UTC).isoformat(),
        "capture_window_utc": [dt.datetime.fromtimestamp(t, dt.UTC).isoformat() for t in (START, END)],
        "publication_time_basis": "immutable manifest filesystem mtime; availability proxy",
        "captures": sorted(rows, key=lambda r: r["capture_start_s"]),
        "inventory_errors": errors,
    }, indent=2))


if __name__ == "__main__":
    main()
