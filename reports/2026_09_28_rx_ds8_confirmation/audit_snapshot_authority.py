"""Reconstruct and bind the metadata-only DS8 snapshot authority."""

import hashlib
import json
from pathlib import Path

from tools.rx_ds8_snapshot_authority import build_authority

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
READINESS = ROOT / "reports/2026_09_28_rx_causal_refit/ds8-readiness.json"
POSES = ROOT / "reports/2026_09_28_ds8_post_ds7/pose"
AUTHORITY = HERE / "snapshot-authority.json"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    from leo.operations.tle_archive import TleArchiveReader

    readiness = json.loads(READINESS.read_text())
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        reconstructed, selections = build_authority(
            readiness, POSES, store, TleArchiveReader(Path("/var/lib/leo/tle"))
        )
    finally:
        store.close()
    assert reconstructed == json.loads(AUTHORITY.read_text())
    assert all(row["strictly_before_cutoff"] for row in selections)
    pose_paths = [POSES / f"{row['session_id']}.json" for row in readiness["selected"]]
    paths = [
        AUTHORITY,
        READINESS,
        ROOT / "tools/rx_ds8_snapshot_authority.py",
        Path(__file__),
        *pose_paths,
    ]
    result = {
        "schema": "rx-ds8-snapshot-authority-audit/v1",
        "status": "pass",
        "reconstructed_exactly": True,
        "all_selections_strictly_causal": True,
        "selections": selections,
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in paths},
    }
    with (HERE / "audit-snapshot-authority.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
