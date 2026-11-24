import json
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import zstandard as zstd

from leo.contracts.digests import sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader
from reports.ALGO08.v3 import owned_capture_0016 as trial


def entry(i, first, count, *, failure=None):
    return dict(ordinal=i, global_first=first, directory=f"segment-{i:08d}", windows=count,
                members=[dict(chunk_index=0, first_sequence=0, window_count=count)],
                status="incomplete" if failure else "complete", failure=failure)


def test_recording_envelope_checks_all_segment_and_member_boundaries():
    segments = [entry(0, 0, 64), entry(1, 64, 5, failure="saved timeout")]
    trial.validate_segments(segments, 69)
    with pytest.raises(ValueError, match="reversed or omitted"):
        trial.validate_segments(segments[::-1], 69)
    with pytest.raises(ValueError, match="window count"):
        trial.validate_segments(segments[:1], 69)
    corrupted = deepcopy(segments)
    corrupted[1]["members"][0]["first_sequence"] = 1
    with pytest.raises(ValueError, match="member coverage"):
        trial.validate_segments(corrupted, 69)
    corrupted = deepcopy(segments)
    corrupted[1]["failure"] = None
    with pytest.raises(ValueError, match="lifecycle"):
        trial.validate_segments(corrupted, 69)


def test_released_writer_keeps_recorder_fault_when_rehearsing_owned_input(tmp_path):
    header = SimpleNamespace(configuration=dict(sample_rate_hz=10_000_000, window_ms=20),
                             radio={}, receiver_ids=(0, 1), status="incomplete",
                             stop_reason="fault", failure="saved timeout")
    row = SimpleNamespace(sequence=0, target_id="tx", acquisition={"global_visit": 0},
                          powers=({}, {}))
    sample = SimpleNamespace(index=row, samples=np.zeros((200_000, 2, 2), dtype="<i2"))
    output = tmp_path / "segment-00000000"
    pin, chunks = trial.ordinary_capture(output, header, (sample,))
    sealed = ShortWindowReader(output)
    assert sealed.manifest_sha256 == pin and sealed.manifest.failure == header.failure
    assert len(chunks) == 1 and chunks[0]["window_count"] == 1
    decoded, = sealed.windows()
    assert decoded.index.acquisition == row.acquisition
    np.testing.assert_array_equal(decoded.samples, sample.samples)


def test_zstd_frames_are_backward_readable_at_visit_boundaries_only(tmp_path):
    header = SimpleNamespace(configuration=dict(sample_rate_hz=10_000_000, window_ms=20),
                             radio={}, receiver_ids=(0, 1), status="complete",
                             stop_reason="test", failure=None)
    windows, raw = [], []
    for visit in range(2):
        values = np.full((200_000, 2, 2), fill_value=visit + 1, dtype="<i2")
        acquisition = dict(global_visit=visit)
        row = SimpleNamespace(sequence=visit, target_id="tx", acquisition=acquisition,
                              powers=({}, {}))
        windows.append(SimpleNamespace(index=row, samples=values))
        raw.append(values.tobytes())
    path = tmp_path / "segment"
    original_pin, original_members = trial.ordinary_capture(path, header, windows)
    manifest = path / "manifest.json"
    document = json.loads(manifest.read_bytes())
    chunk = document["chunks"][0]
    source = path / chunk["payload_relative_path"]
    encoder = zstd.ZstdCompressor(level=1, write_checksum=True)

    def replace(parts):
        encoded = b"".join(encoder.compress(part) for part in parts)
        source.write_bytes(encoded)
        chunk.update(compressed_bytes=len(encoded), compressed_sha256=sha256_digest(encoded))
        manifest.write_text(json.dumps(document))
        return encoded

    replace(raw)
    fresh = ShortWindowReader(path)
    assert actual_bytes(fresh) == raw
    assert fresh.manifest_sha256 != original_pin
    assert chunk["compressed_sha256"] != original_members[0]["compressed_sha256"]
    assert trial.logical([chunk]) == trial.logical(original_members)

    parts = [part for value in raw for part in (value[:640_000], value[640_000:])]
    encoded = replace(parts)
    with pytest.raises(BundleCorruptionError, match="window IQ length or digest changed"):
        actual_bytes(ShortWindowReader(path))
    with zstd.ZstdDecompressor().stream_reader(encoded, read_across_frames=True) as stream:
        assert [stream.read(len(data)) for data in raw] == raw
        assert stream.read(1) == b""


def actual_bytes(reader):
    return [window.samples.tobytes() for window in reader.windows()]


@pytest.mark.parametrize("samples", [(0, 40_000, 80_000, 90_000, 200_000, 0), (0, 0)])
def test_optional_seek_table_reads_a_flushed_prefix_inside_one_visit_frame(tmp_path, samples):
    header = SimpleNamespace(configuration=dict(sample_rate_hz=10_000_000, window_ms=20),
                             radio={}, receiver_ids=(0, 1), status="complete",
                             stop_reason="test", failure=None)
    windows, raw = [], []
    for visit, count in enumerate(samples):
        values = np.full((count, 2, 2), fill_value=visit + 1, dtype="<i2")
        values[80_000:] += 10
        row = SimpleNamespace(sequence=visit, target_id="tx", acquisition={"global_visit": visit},
                              powers=({}, {}))
        windows.append(SimpleNamespace(index=row, samples=values))
        raw.append(values.tobytes())
    path = tmp_path / "segment"
    _, original = trial.ordinary_capture(path, header, windows)
    manifest = path / "manifest.json"
    document = json.loads(manifest.read_bytes())
    chunk = document["chunks"][0]
    encoder = zstd.ZstdCompressor(level=1, write_checksum=True)
    frames, records, offset = [], [], 0
    for visit, value in enumerate(raw):
        prefix_size = min(len(value), 640_000)
        if value:
            operation = encoder.compressobj(size=len(value))
            part = operation.compress(value[:prefix_size])
            part += operation.flush(zstd.COMPRESSOBJ_FLUSH_BLOCK)
            frame = part + operation.compress(value[prefix_size:]) + operation.flush()
        else:
            part = frame = b""
        records.append(dict(sequence=visit, offset=offset, frame_bytes=len(frame),
                            prefix_end=offset + len(part), prefix_size=prefix_size,
                            prefix_digest=sha256_digest(value[:prefix_size])))
        frames.append(frame)
        offset += len(frame)
    # The public manifest requires a positive encoded member size even for zero total decoded bytes.
    payload = b"".join(frames) or encoder.compress(b"")
    (path / chunk["payload_relative_path"]).write_bytes(payload)
    chunk.update(compressed_bytes=len(payload), compressed_sha256=sha256_digest(payload))
    manifest.write_text(json.dumps(document))
    installed = ShortWindowReader(path)
    assert actual_bytes(installed) == raw
    assert trial.logical([chunk]) == trial.logical(original)

    table = dict(manifest_sha256=installed.manifest_sha256, index_sha256=chunk["index_sha256"],
                 compressed_sha256=chunk["compressed_sha256"], records=records)
    sidecar = path / "optional-seek.json"
    contents = json.dumps(table).encode()
    sidecar.write_bytes(contents)
    parsed = json.loads(trial.checked(sidecar, sha256_digest(contents)))
    assert parsed["manifest_sha256"] == installed.manifest_sha256
    assert parsed["index_sha256"] == installed.manifest.chunks[0].index_sha256
    authenticated = installed._member(chunk["payload_relative_path"], len(payload),
                                      parsed["compressed_sha256"])
    for row, value in zip(parsed["records"], raw, strict=True):
        encoded = authenticated[row["offset"]:row["prefix_end"]]
        if row["prefix_size"]:
            with zstd.ZstdDecompressor().stream_reader(encoded) as stream:
                prefix = stream.read(row["prefix_size"])
            start = row["offset"]
            complete = authenticated[start:start + row["frame_bytes"]]
            assert zstd.ZstdDecompressor().decompress(complete) == value
        else:
            prefix = b""
        assert prefix == value[:row["prefix_size"]]
        assert sha256_digest(prefix) == row["prefix_digest"]
