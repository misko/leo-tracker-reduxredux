import json
from hashlib import sha256

import numpy as np
import pytest
import zstandard as zstd

from tools.pipeline_eval.variants.iq_stream import IQReadError, load_windows, run


def digest(data):
    return "sha256:" + sha256(data).hexdigest()


@pytest.fixture
def recording(tmp_path):
    samples = np.array(
        [[[-32768, 0], [1, -1]], [[32767, -42], [-32768, 42]], [[500, -315], [91, 0]]],
        dtype="<i2",
    )
    manifest_dir = tmp_path / "test-segment"
    manifest_dir.mkdir()
    target = {"target_id": "ch1-lower", "edge": "lower", "rf_center_hz": 10_700_000_000}
    raw = bytearray()
    index = []
    for sequence in range(9):
        window = (samples // (sequence + 1)).astype("<i2").tobytes()
        row = {
            "schema_version": 2,
            "sequence": sequence,
            "target_id": target["target_id"],
            "sample_count": len(samples),
            "receiver_count": 2,
            "payload_offset_bytes": len(raw),
            "payload_bytes": len(window),
            "iq_sha256": digest(window),
            "acquisition": {"sample_start": 100 + sequence * len(samples)},
            "powers": [{}, {}],
        }
        index.append(json.dumps(row) + "\n")
        raw.extend(window)
    index_bytes = "".join(index).encode()
    compressed = zstd.ZstdCompressor().compress(raw)
    chunk = {
        "chunk_index": 0,
        "first_sequence": 0,
        "window_count": 9,
        "payload_relative_path": "iq.zst",
        "index_relative_path": "index.jsonl",
        "compressed_bytes": len(compressed),
        "compressed_sha256": digest(compressed),
        "index_bytes": len(index_bytes),
        "index_sha256": digest(index_bytes),
        "uncompressed_bytes": len(raw),
        "uncompressed_sha256": digest(raw),
    }
    manifest = {
        "schema_version": 2,
        "kind": "short_window_iq_recording",
        "session_id": manifest_dir.name,
        "configuration": {"sample_rate_hz": 10_000_000, "window_ms": 20, "targets": [target]},
        "radio": {},
        "receiver_ids": [0, 1],
        "sample_rate_hz": 10_000_000,
        "window_ms": 20,
        "created_utc_ns": 0,
        "finalized_utc_ns": 1,
        "status": "complete",
        "stop_reason": "fixture",
        "window_count": 9,
        "chunks": [chunk],
    }
    (manifest_dir / "index.jsonl").write_bytes(index_bytes)
    (manifest_dir / "iq.zst").write_bytes(compressed)
    manifest_path = manifest_dir / "manifest.json"
    manifest_bytes = json.dumps(manifest).encode()
    manifest_path.write_bytes(manifest_bytes)
    case = {
        "id": "fixture",
        "panel": "DS29",
        "recording_path": str(manifest_path),
        "recording_sha256": digest(manifest_bytes),
    }
    return case, samples, manifest_dir


def test_detector_bytes_and_metadata(recording):
    case, samples, _ = recording
    first, last = load_windows(case, (8, 0))
    assert first.sequence == 0
    assert first.samples.tobytes() == samples.tobytes()
    assert first.samples.dtype == np.dtype("<i2")
    assert not first.samples.flags.writeable
    assert first.receiver_ids == (0, 1)
    assert first.sample_rate_hz == 10_000_000
    assert first.target["edge"] == "lower"
    assert first.acquisition["sample_start"] == 100
    assert last.sequence == 8
    assert last.samples.tobytes() == (samples // 9).astype("<i2").tobytes()
    assert last.iq_sha256 == digest(last.samples.tobytes())


def test_matched_stage_timing_and_bytes(recording, tmp_path):
    case, samples, _ = recording
    result = run(case, tmp_path)
    assert result["status"] == "ok", result
    metrics = result["metrics"]
    assert metrics["bitwise_equal"]
    assert metrics["windows"] == 2
    assert metrics["decoded_prefix_windows"] == 9
    assert metrics["samples_per_receiver"] == len(samples) * 2
    assert metrics["detector_ci16_bytes"] == 2 * samples.nbytes
    assert metrics["decoded_prefix_bytes"] == 9 * samples.nbytes
    for name in ("control", "candidate"):
        assert metrics[f"{name}_s"] > 0
        assert metrics[f"{name}_cpu_s"] > 0
        assert len(metrics[f"{name}_wall_repeats_s"]) == 5
        assert all(value > 0 for value in metrics[f"{name}_compressed_read_bytes"])


def test_modified_index_is_unavailable(recording, tmp_path):
    case, _, directory = recording
    index = directory / "index.jsonl"
    index.write_bytes(index.read_bytes().replace(b"100", b"101", 1))
    result = run(case, tmp_path)
    assert result["status"] == "unavailable"
    assert "IQ chunk index failed SHA-256 verification" in result["reason"]


def test_modified_iq_is_rejected_even_for_skipped_window(recording):
    case, _, directory = recording
    path = directory / "iq.zst"
    raw = bytearray(zstd.ZstdDecompressor().decompress(path.read_bytes()))
    raw[24] ^= 1
    path.write_bytes(zstd.ZstdCompressor().compress(raw))
    with pytest.raises(IQReadError, match="changed IQ window 1"):
        load_windows(case, (0, 8))


@pytest.mark.parametrize("complete", [False, True])
def test_empty_visit_keeps_signed_identity_only_for_explicit_capture_failures(recording, complete):
    case, _, directory = recording
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    chunk = manifest["chunks"][0]
    index = directory / chunk["index_relative_path"]
    lines = index.read_text().splitlines()
    row = json.loads(lines[-1])
    raw = zstd.ZstdDecompressor().decompress((directory / "iq.zst").read_bytes())
    raw = raw[: row["payload_offset_bytes"]]
    row.update(sample_count=0, payload_bytes=0, iq_sha256=digest(b""))
    row["acquisition"]["complete"] = complete
    lines[-1] = json.dumps(row)
    payload = zstd.ZstdCompressor().compress(raw)
    (directory / "iq.zst").write_bytes(payload)
    index.write_text("\n".join(lines) + "\n")
    chunk.update(
        index_bytes=index.stat().st_size,
        index_sha256=digest(index.read_bytes()),
        compressed_bytes=len(payload),
        compressed_sha256=digest(payload),
        uncompressed_bytes=len(raw),
        uncompressed_sha256=digest(raw),
    )
    path.write_text(json.dumps(manifest))
    case["recording_sha256"] = digest(path.read_bytes())
    with pytest.raises(IQReadError, match="missing IQ"):
        load_windows(case, (7, 8))
    if complete:
        with pytest.raises(IQReadError, match="missing IQ"):
            load_windows(case, (7, 8), include_empty_visits=True)
    else:
        good, empty = load_windows(case, (7, 8), include_empty_visits=True)
        assert good.samples.size > 0
        assert empty.sequence == 8 and empty.iq_sha256 == digest(b"")
        assert empty.samples.shape == (0, 2, 2)


def test_manifest_binding_and_explicitly_missing_iq(recording):
    case, _, _ = recording
    with pytest.raises(IQReadError, match="manifest failed SHA-256 verification"):
        load_windows({**case, "recording_sha256": digest(b"other manifest")})
    with pytest.raises(IQReadError, match="recording path or frozen manifest digest is missing"):
        load_windows({"id": "DS26-0036", "panel": "DS26", "recording_path": None})
