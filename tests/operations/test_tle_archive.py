from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from leo.operations.tle_archive import (
    MAXIMUM_SNAPSHOT_BYTES,
    TleArchiveError,
    TleArchiveReader,
    TleSnapshotRef,
)

ELEMENT_SET = (
    "0 STARLINK-1008\n"
    "1 44714U 19074B   26232.62719907  .00001103  00000-0  92799-4 0  9992\n"
    "2 44714  53.0537 172.0234 0001334  87.1234 273.0021 15.06393004260127\n"
)


def _store(root: Path, provider: str, collected_utc_ns: int, payload: str) -> TleSnapshotRef:
    directory = root / "archive" / provider
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    path = directory / f"{collected_utc_ns}-{digest}.tle"
    path.write_text(payload)
    return TleSnapshotRef(
        collected_utc_ns=collected_utc_ns,
        provider=provider,
        sha256=digest,
        byte_size=path.stat().st_size,
        path=path,
    )


def test_snapshots_are_listed_oldest_first_across_providers(tmp_path: Path) -> None:
    _store(tmp_path, "space-track", 3_000, ELEMENT_SET)
    _store(tmp_path, "huggingface", 1_000, ELEMENT_SET + "\n")
    _store(tmp_path, "space-track", 2_000, ELEMENT_SET + "\n\n")

    listed = TleArchiveReader(tmp_path).list_snapshots()
    assert [item.collected_utc_ns for item in listed] == [1_000, 2_000, 3_000]
    assert [item.provider for item in listed] == ["huggingface", "space-track", "space-track"]


def test_provider_filter_is_honoured_and_unknown_providers_fail_closed(tmp_path: Path) -> None:
    _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    _store(tmp_path, "huggingface", 2_000, ELEMENT_SET + "\n")
    reader = TleArchiveReader(tmp_path)

    assert [item.provider for item in reader.list_snapshots("huggingface")] == ["huggingface"]
    with pytest.raises(TleArchiveError, match="unsupported TLE provider"):
        reader.list_snapshots("celestrak")


def test_files_that_are_not_collector_output_are_ignored(tmp_path: Path) -> None:
    _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    directory = tmp_path / "archive" / "space-track"
    (directory / "notes.txt").write_text("not a snapshot")
    (directory / "1000-short.tle").write_text("bad digest length")
    (directory / f"{'9' * 20}-{'a' * 64}.tle").write_text("timestamp too long")

    assert len(TleArchiveReader(tmp_path).list_snapshots()) == 1


def test_nearest_selection_prefers_proximity_over_recency(tmp_path: Path) -> None:
    _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    _store(tmp_path, "space-track", 9_000, ELEMENT_SET + "\n")
    reader = TleArchiveReader(tmp_path)

    # An anchor before every snapshot still resolves, and an anchor between two
    # resolves to the closer one even though the other is newer.
    assert reader.select_nearest(0).collected_utc_ns == 1_000
    assert reader.select_nearest(3_000).collected_utc_ns == 1_000
    assert reader.select_nearest(7_000).collected_utc_ns == 9_000
    assert reader.select_nearest(50_000).collected_utc_ns == 9_000


def test_nearest_selection_breaks_ties_reproducibly(tmp_path: Path) -> None:
    _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    _store(tmp_path, "huggingface", 3_000, ELEMENT_SET + "\n")
    reader = TleArchiveReader(tmp_path)

    chosen = {reader.select_nearest(2_000).collected_utc_ns for _ in range(8)}
    assert chosen == {1_000}


def test_empty_archive_is_unavailable_not_an_empty_constellation(tmp_path: Path) -> None:
    reader = TleArchiveReader(tmp_path)
    with pytest.raises(TleArchiveError, match="no TLE snapshot is available"):
        reader.select_nearest(1_000)

    (tmp_path / "archive" / "space-track").mkdir(parents=True)
    with pytest.raises(TleArchiveError, match="no TLE snapshot is available"):
        reader.select_nearest(1_000)

    _store(tmp_path, "huggingface", 1_000, ELEMENT_SET)
    with pytest.raises(TleArchiveError, match="no TLE snapshot is available"):
        reader.select_nearest(1_000, provider="space-track")


def test_read_returns_the_stored_text(tmp_path: Path) -> None:
    snapshot = _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    assert TleArchiveReader(tmp_path).read(snapshot) == ELEMENT_SET
    assert snapshot.digest.startswith("sha256:")
    assert len(snapshot.digest) == 71


def test_tampered_content_is_rejected_even_though_the_name_is_unchanged(tmp_path: Path) -> None:
    snapshot = _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    snapshot.path.write_text(ELEMENT_SET.replace("53.0537", "53.9999"))

    with pytest.raises(TleArchiveError, match="does not match its recorded digest"):
        TleArchiveReader(tmp_path).read(snapshot)


def test_truncated_content_is_rejected(tmp_path: Path) -> None:
    snapshot = _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    snapshot.path.write_text(ELEMENT_SET[: len(ELEMENT_SET) // 2])

    with pytest.raises(TleArchiveError, match="does not match its recorded digest"):
        TleArchiveReader(tmp_path).read(snapshot)


def test_missing_file_is_reported_rather_than_raising_oserror(tmp_path: Path) -> None:
    snapshot = _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    snapshot.path.unlink()

    with pytest.raises(TleArchiveError, match="unreadable"):
        TleArchiveReader(tmp_path).read(snapshot)


def test_non_ascii_content_is_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "archive" / "space-track"
    directory.mkdir(parents=True)
    payload = "0 STARLINK-é\n".encode()
    digest = hashlib.sha256(payload).hexdigest()
    path = directory / f"1000-{digest}.tle"
    path.write_bytes(payload)

    snapshot = TleSnapshotRef(1_000, "space-track", digest, len(payload), path)
    with pytest.raises(TleArchiveError, match="not ASCII"):
        TleArchiveReader(tmp_path).read(snapshot)


def test_oversized_snapshot_is_refused_before_being_read(tmp_path: Path) -> None:
    snapshot = _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    oversized = TleSnapshotRef(
        collected_utc_ns=snapshot.collected_utc_ns,
        provider=snapshot.provider,
        sha256=snapshot.sha256,
        byte_size=MAXIMUM_SNAPSHOT_BYTES + 1,
        path=snapshot.path,
    )
    with pytest.raises(TleArchiveError, match="exceeds the"):
        TleArchiveReader(tmp_path).read(oversized)


def test_reader_never_writes_to_the_archive(tmp_path: Path) -> None:
    _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    before = {path: path.stat().st_mtime_ns for path in sorted(tmp_path.rglob("*"))}

    reader = TleArchiveReader(tmp_path)
    reader.read(reader.select_nearest(1_000))
    with pytest.raises(TleArchiveError):
        reader.select_nearest(1_000, provider="huggingface")

    after = {path: path.stat().st_mtime_ns for path in sorted(tmp_path.rglob("*"))}
    assert before == after


def test_unreadable_directories_become_archive_errors(tmp_path: Path) -> None:
    """A permission failure must surface as the promised error type, not a bare
    OSError from deep inside a listing loop."""

    directory = tmp_path / "archive" / "space-track"
    directory.mkdir(parents=True)
    _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    directory.chmod(0o000)
    try:
        with pytest.raises(TleArchiveError, match="could not be listed|could not be inspected"):
            TleArchiveReader(tmp_path).list_snapshots("space-track")
    finally:
        directory.chmod(0o755)


def test_symlinked_snapshots_are_refused_rather_than_followed(tmp_path: Path) -> None:
    snapshot = _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    outside = tmp_path / "outside.tle"
    outside.write_text(ELEMENT_SET)
    link = snapshot.path.parent / f"2000-{'b' * 64}.tle"
    link.symlink_to(outside)

    listed = TleArchiveReader(tmp_path).list_snapshots("space-track")
    assert [item.collected_utc_ns for item in listed] == [1_000]


def test_a_reference_outside_the_archive_root_is_refused(tmp_path: Path) -> None:
    """The reference is data, not authority.  Its location is re-derived from
    the configured root rather than trusted."""

    _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    outside = tmp_path / "elsewhere.tle"
    outside.write_text(ELEMENT_SET)
    forged = TleSnapshotRef(
        collected_utc_ns=1_000,
        provider="space-track",
        sha256=hashlib.sha256(ELEMENT_SET.encode()).hexdigest(),
        byte_size=outside.stat().st_size,
        path=outside,
    )

    with pytest.raises(TleArchiveError, match="lies outside the archive root"):
        TleArchiveReader(tmp_path).read(forged)


def test_a_symlink_planted_inside_the_root_is_not_followed(tmp_path: Path) -> None:
    _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    target = tmp_path / "target.tle"
    target.write_text(ELEMENT_SET)
    digest = hashlib.sha256(ELEMENT_SET.encode()).hexdigest()
    link = tmp_path / "archive" / "space-track" / f"2000-{digest}.tle"
    link.symlink_to(target)

    reference = TleSnapshotRef(2_000, "space-track", digest, target.stat().st_size, link)
    with pytest.raises(TleArchiveError, match="unreadable"):
        TleArchiveReader(tmp_path).read(reference)


def test_a_reference_with_an_unknown_provider_is_refused(tmp_path: Path) -> None:
    snapshot = _store(tmp_path, "space-track", 1_000, ELEMENT_SET)
    forged = TleSnapshotRef(
        snapshot.collected_utc_ns, "celestrak", snapshot.sha256, snapshot.byte_size, snapshot.path
    )
    with pytest.raises(TleArchiveError, match="unsupported TLE provider"):
        TleArchiveReader(tmp_path).read(forged)
