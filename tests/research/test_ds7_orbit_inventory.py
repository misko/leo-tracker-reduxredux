from __future__ import annotations

import hashlib
from pathlib import Path

from leo.operations.tle_archive import TleArchiveReader, TleSnapshotRef
from tools.ds7_orbit_inventory import build_inventory, newest_per_object

OLD = (
    "0 STARLINK-1008\n"
    "1 44714U 19074B   26232.62719907  .00001103  00000-0  92799-4 0  9992\n"
    "2 44714  53.0537 172.0234 0001334  87.1234 273.0021 15.06393004260127\n"
)
NEW = OLD.replace(
    "26232.62719907  .00001103  00000-0  92799-4 0  9992",
    "26233.62719907  .00001103  00000-0  92799-4 0  9993",
)


def _store(
    root: Path, collected: int, payload: str, provider: str = "space-track"
) -> TleSnapshotRef:
    folder = root / "archive" / provider
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    path = folder / f"{collected}-{digest}.tle"
    path.write_text(payload)
    return TleSnapshotRef(collected, provider, digest, len(payload), path)


def test_newest_per_object_uses_element_epoch_not_last_snapshot(tmp_path: Path) -> None:
    # Newer elements arrived first; a later collector response regressed.
    newer = _store(tmp_path, 1_800_000_000_000_000_000, NEW)
    older = _store(tmp_path, 1_800_100_000_000_000_000, OLD)
    selected, future = newest_per_object(TleArchiveReader(tmp_path), (newer, older))
    assert future == 0
    assert selected[44714].source == newer


def test_inventory_uses_earliest_start_and_does_not_accept_post_capture(tmp_path: Path) -> None:
    before = _store(tmp_path, 1_800_000_000_000_000_000, OLD)
    _store(tmp_path, 1_800_200_000_000_000_000, NEW)
    plan = {
        "dataset_id": "ds7-test",
        "dataset_sha256": "sha256:" + "a" * 64,
        "content_sha256": "sha256:" + "b" * 64,
        "captures": [
            {
                "session_id": "s1",
                "manifest_sha256": "sha256:" + "c" * 64,
                "capture_start_utc_ns": 1_800_150_000_000_000_000,
                "capture_start_earliest_utc_ns": 1_800_100_000_000_000_000,
            }
        ],
    }
    result = build_inventory(plan, TleArchiveReader(tmp_path), tmp_path / "out", 1)
    product = result["captures"][0]["products"][0]
    assert product["latest_snapshot"]["sha256"] == before.digest
    assert product["causal_snapshot_count"] == 1
    assert Path(product["newest_per_object"]["path"]).read_text() == OLD
