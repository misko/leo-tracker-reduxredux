from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter


def writer(root: Path, *, chunk_windows: int = 2) -> ShortWindowWriter:
    return ShortWindowWriter(
        root,
        "test-windows",
        configuration={"window_ms": 20},
        radio={"serial": "fake"},
        receiver_ids=(0, 1),
        chunk_windows=chunk_windows,
    )


def append(sink: ShortWindowWriter, sequence: int, samples: np.ndarray) -> None:
    sink.append(
        sequence=sequence,
        target_id=f"if-{sequence % 8}",
        samples=samples,
        acquisition={"sample_start": sequence * 50_000},
        powers=({"decision": "quiet"}, {"decision": "active"}),
    )


def test_chunk_rotation_bit_exact_quiet_and_partial_windows(tmp_path: Path) -> None:
    rng = np.random.default_rng(913)
    expected = [
        rng.integers(-32768, 32768, size=(count, 2, 2), dtype=np.int16)
        for count in (50_000, 50_000, 123, 0, 50_000)
    ]
    sink = writer(tmp_path)
    for sequence, values in enumerate(expected):
        append(sink, sequence, values)
    path = sink.finish(stop_reason="max_visits")
    reader = ShortWindowReader(path)
    assert reader.manifest.window_count == 5
    assert [chunk.window_count for chunk in reader.manifest.chunks] == [2, 2, 1]
    observed = list(reader.windows())
    for before, after in zip(expected, observed, strict=True):
        np.testing.assert_array_equal(before, after.samples)
        assert not after.samples.flags.writeable
        assert after.index.powers[0]["decision"] == "quiet"
    assert not sink.partial.exists()


def test_incomplete_capture_is_published_with_failure(tmp_path: Path) -> None:
    sink = writer(tmp_path)
    append(sink, 0, np.zeros((50_000, 2, 2), dtype="<i2"))
    reader = ShortWindowReader(sink.finish(stop_reason="source_failure", failure="USB lost"))
    assert reader.manifest.status == "incomplete"
    assert reader.manifest.failure == "USB lost"
    assert len(list(reader.windows())) == 1


def test_empty_recording_and_abort_are_distinct(tmp_path: Path) -> None:
    sink = writer(tmp_path)
    path = sink.finish(stop_reason="cancelled", failure="cancelled before capture")
    assert list(ShortWindowReader(path).windows()) == []
    other = writer(tmp_path / "other")
    append(other, 0, np.zeros((3, 2, 2), dtype="<i2"))
    other.abort()
    assert other.partial.exists()
    assert not other.destination.exists()
    assert not (other.partial / "manifest.json").exists()


@pytest.mark.parametrize("member", ["payload_relative_path", "index_relative_path"])
def test_member_corruption_is_detected_before_returning_iq(tmp_path: Path, member: str) -> None:
    sink = writer(tmp_path)
    append(sink, 0, np.zeros((50_000, 2, 2), dtype="<i2"))
    path = sink.finish(stop_reason="max_visits")
    reader = ShortWindowReader(path)
    victim = path / getattr(reader.manifest.chunks[0], member)
    payload = bytearray(victim.read_bytes())
    payload[len(payload) // 2] ^= 1
    victim.write_bytes(payload)
    with pytest.raises(BundleCorruptionError, match="member changed"):
        next(reader.windows())


def test_per_window_digest_and_sequence_are_verified(tmp_path: Path) -> None:
    sink = writer(tmp_path)
    append(sink, 0, np.zeros((50_000, 2, 2), dtype="<i2"))
    path = sink.finish(stop_reason="max_visits")
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    chunk = manifest["chunks"][0]
    index_path = path / chunk["index_relative_path"]
    row = json.loads(index_path.read_bytes())
    row["iq_sha256"] = "sha256:" + "0" * 64
    payload = canonical_json_bytes(row) + b"\n"
    index_path.write_bytes(payload)
    chunk["index_bytes"] = len(payload)
    chunk["index_sha256"] = sha256_digest(payload)
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(BundleCorruptionError, match="IQ length or digest"):
        next(ShortWindowReader(path).windows())


def test_writer_rejects_bad_geometry_and_nonconsecutive_samples(tmp_path: Path) -> None:
    sink = writer(tmp_path)
    with pytest.raises(ValueError, match="consecutive"):
        append(sink, 1, np.zeros((50_000, 2, 2), dtype="<i2"))
    for samples in (
        np.zeros((50_001, 2, 2), dtype="<i2"),
        np.zeros((50_000, 1, 2), dtype="<i2"),
        np.zeros((50_000, 2, 2), dtype="<f4"),
    ):
        with pytest.raises(ValueError, match="CI16"):
            append(sink, 0, samples)
    sink.abort()


def test_writer_refuses_qnap_and_duplicate_recordings(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="QNAP"):
        writer(Path("/mnt/qnap01/short-window-forbidden"))
    link = tmp_path / "qnap"
    link.symlink_to("/mnt/qnap01", target_is_directory=True)
    with pytest.raises(ValueError, match="QNAP"):
        writer(link / "short-window-forbidden")
    sink = writer(tmp_path)
    sink.finish(stop_reason="empty")
    with pytest.raises(FileExistsError):
        writer(tmp_path)


def test_reader_rejects_escaping_chunk_path(tmp_path: Path) -> None:
    sink = writer(tmp_path)
    append(sink, 0, np.zeros((1, 2, 2), dtype="<i2"))
    path = sink.finish(stop_reason="max_visits")
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["chunks"][0]["payload_relative_path"] = "../outside.zst"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(BundleCorruptionError):
        ShortWindowReader(path)
