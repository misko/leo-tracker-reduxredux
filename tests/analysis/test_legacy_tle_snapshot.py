from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from leo.analysis.research.legacy_tle_snapshot import (
    FrozenLegacyTleBinding,
    LegacyTleSnapshotReader,
)

ELEMENT_SET = (
    "0 STARLINK-1008\n"
    "1 44714U 19074B   26232.62719907  .00001103  00000-0  92799-4 0  9992\n"
    "2 44714  53.0537 172.0234 0001334  87.1234 273.0021 15.06393004260127\n"
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fixture(tmp_path: Path) -> tuple[LegacyTleSnapshotReader, FrozenLegacyTleBinding]:
    snapshot_root = tmp_path / "snapshots"
    raw_root = tmp_path / "raw"
    snapshot_root.mkdir()
    raw_root.mkdir()
    payload = ELEMENT_SET.encode("ascii")
    raw_sha = _sha(payload)
    raw_path = raw_root / f"{raw_sha}.tle"
    raw_path.write_bytes(payload)
    metadata = {
        "schema": "leo-tracker.catalog-store-snapshot/v1",
        "source": "space-track",
        "scope": "starlink",
        "retrieved_at": "2026-08-25T01:37:00.001224Z",
        "raw_object": f"raw/space-track/{raw_sha}.tle",
        "raw_sha256": raw_sha,
        "catalog_sha256": raw_sha,
        "satellite_count": 1,
    }
    metadata_bytes = json.dumps(metadata, sort_keys=True).encode()
    metadata_path = snapshot_root / "snapshot.json"
    metadata_path.write_bytes(metadata_bytes)
    binding = FrozenLegacyTleBinding(
        metadata_path=metadata_path,
        metadata_sha256=_sha(metadata_bytes),
        raw_path=raw_path,
        raw_sha256=raw_sha,
        raw_byte_size=len(payload),
        satellite_count=1,
        retrieved_at="2026-08-25T01:37:00.001224Z",
    )
    return LegacyTleSnapshotReader(snapshot_root=snapshot_root, raw_root=raw_root), binding


def test_exact_legacy_snapshot_is_verified_without_an_index(tmp_path: Path) -> None:
    reader, binding = _fixture(tmp_path)

    payload = reader.read(binding)

    assert payload.text == ELEMENT_SET
    assert payload.binding == binding


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("raw_sha256", "0" * 64, "digest"),
        ("raw_byte_size", 1, "byte size"),
        ("satellite_count", 2, "metadata binding|count"),
    ],
)
def test_raw_digest_size_and_count_mismatch_fail_closed(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    reader, binding = _fixture(tmp_path)

    with pytest.raises(ValueError, match=message):
        reader.read(replace(binding, **{field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", "bad"),
        ("source", "other"),
        ("scope", "all"),
        ("retrieved_at", "2026-08-25T01:38:00Z"),
        ("raw_object", "raw/space-track/substitute.tle"),
    ],
)
def test_metadata_authority_mismatch_fails_closed(
    tmp_path: Path, field: str, value: object
) -> None:
    reader, binding = _fixture(tmp_path)
    metadata = json.loads(binding.metadata_path.read_text())
    metadata[field] = value
    payload = json.dumps(metadata, sort_keys=True).encode()
    binding.metadata_path.write_bytes(payload)

    with pytest.raises(ValueError, match="metadata binding"):
        reader.read(replace(binding, metadata_sha256=_sha(payload)))


def test_symlink_fifo_and_root_escape_are_rejected(tmp_path: Path) -> None:
    reader, binding = _fixture(tmp_path)
    symlink = binding.raw_path.parent / "link.tle"
    symlink.symlink_to(binding.raw_path)
    with pytest.raises(OSError):
        reader.read(replace(binding, raw_path=symlink))

    fifo = binding.raw_path.parent / "fifo.tle"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular file"):
        reader.read(replace(binding, raw_path=fifo))

    outside = tmp_path / "outside.tle"
    outside.write_text(ELEMENT_SET)
    with pytest.raises(ValueError, match="escapes"):
        reader.read(replace(binding, raw_path=outside))

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_nested = outside_dir / "nested.tle"
    outside_nested.write_text(ELEMENT_SET)
    parent_link = binding.raw_path.parent / "linked-parent"
    parent_link.symlink_to(outside_dir, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        reader.read(replace(binding, raw_path=parent_link / outside_nested.name))
