from contextlib import closing
import json
from pathlib import Path
import subprocess

import numpy as np
import pytest
import zstandard as zstd

from leo.contracts.digests import sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.fast_scan import FastSegmentSource
from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from reports.ALGO08.v3.first_third_ingress import chunk_rows
from reports.ALGO08.v3.native_verified_drain import NativeDrain, build


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    path = tmp_path_factory.mktemp("compiled-drain")
    hasher = path / "paired-sha256.so"
    source = Path(__file__).resolve().parents[2] / "tools/pipeline_eval/variants/experimental/paired_sha256.c"
    subprocess.run(["cc", "-O2", "-Wno-deprecated-declarations", "-fPIC", "-shared", str(source),
                    "-lcrypto", "-o", str(hasher)], check=True)
    binary, _ = build(path, hasher, zstd="-lzstd")
    return binary


@pytest.fixture
def fixture(tmp_path):
    target = dict(target_id="rx", edge="lower", channel=1, rf_center_hz=10_700_000_000,
                  lnb_lo_hz=9_750_000_000)
    writer = ShortWindowWriter(tmp_path, "verified-drain", configuration={
        "window_ms": 20, "sample_rate_hz": 10_000_000, "targets": [target],
    }, radio={"serial": "TEST"}, receiver_ids=(0, 1), chunk_windows=2, schema_version=2)
    samples = np.zeros((200000, 2, 2), dtype="<i2")
    raw = []
    for visit in range(2):
        samples[0, 1, 0] = 17 + visit
        writer.append(sequence=visit, target_id="rx", samples=samples, acquisition={
            "global_visit": visit, "sample_start": 200000*visit, "sample_end": 200000*(visit+1),
            "actual_if_center_hz": 950_000_000,
        }, powers=({}, {}))
        raw.append(samples.tobytes())
    return writer.finish(stop_reason="native-drain-test"), raw


def source(root):
    reader = ShortWindowReader(root)
    return FastSegmentSource(dict(path=str(root), manifest_digest=reader.manifest_sha256))


def authenticated_members(segment):
    assert segment.reader.manifest_sha256 == segment.manifest_digest
    chunk, = segment.reader.manifest.chunks
    rows = chunk_rows(segment, chunk)
    compressed = segment.reader._member(chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256)
    return chunk, rows, compressed


def test_streaming_native_checks_each_decoded_window_and_member(fixture, library):
    root, _ = fixture
    segment = source(root)
    chunk, rows, compressed = authenticated_members(segment)
    assert len(list(segment.windows())) == 2
    with closing(NativeDrain(library)) as native:
        result = native.check(compressed, rows, chunk)
        assert result["decoded_bytes"] == chunk.uncompressed_bytes
        assert result["windows"] == 2
        assert result["checksum"] == 1


@pytest.mark.parametrize("field", ("window", "member"))
def test_already_authenticated_compressed_and_index_bytes_do_not_prove_decoded_digest(fixture, library, field):
    root, raw = fixture
    manifest_path = root / "manifest.json"
    document = json.loads(manifest_path.read_bytes())
    manifest = document["chunks"][0]
    stale_digest = sha256_digest(b"\0" * len(raw[0]))
    if field == "window":
        index_path = root / manifest["index_relative_path"]
        contents = [json.loads(line) for line in index_path.read_bytes().splitlines()]
        contents[0]["iq_sha256"] = stale_digest
        index = b"".join(json.dumps(line).encode() + b"\n" for line in contents)
        index_path.write_bytes(index)
        manifest.update(index_bytes=len(index), index_sha256=sha256_digest(index))
    else:
        manifest["uncompressed_sha256"] = sha256_digest(b"\0" * manifest["uncompressed_bytes"])
    # Bind a freshly constructed manifest to the actual matching input
    # digests. This is a new inconsistent producer, not in-transit tampering.
    manifest_path.write_text(json.dumps(document))
    segment = source(root)
    chunk, rows, compressed = authenticated_members(segment)
    assert len(rows) == 2
    with pytest.raises(BundleCorruptionError):
        list(segment.windows())
    with closing(NativeDrain(library)) as native:
        with pytest.raises(BundleCorruptionError, match=f"decoded {field} digest changed"):
            native.check(compressed, rows, chunk)


@pytest.mark.parametrize("advertise_size", (False, True))
def test_concatenated_frames_decline_native_and_leave_canonical_decoder_available(fixture, library, advertise_size):
    root, raw = fixture
    segment = source(root)
    chunk, rows, _ = authenticated_members(segment)
    encoder = zstd.ZstdCompressor(write_checksum=True, write_content_size=advertise_size)
    payload = b"".join(encoder.compress(window) for window in raw)
    member = segment.reader.path / chunk.payload_relative_path
    member.write_bytes(payload)
    manifest = segment.reader.path / "manifest.json"
    document = json.loads(manifest.read_bytes())
    document["chunks"][0].update(compressed_sha256=sha256_digest(payload), compressed_bytes=len(payload))
    manifest.write_text(json.dumps(document))
    official = source(root)
    assert len(list(official.windows())) == 2
    with closing(NativeDrain(library)) as native:
        assert native.check(payload, rows, chunk) is None


def test_native_rejects_zstd_truncation_and_decoded_surplus(fixture, library):
    root, raw = fixture
    chunk, rows, compressed = authenticated_members(source(root))
    encoder = zstd.ZstdCompressor(write_content_size=False, write_checksum=True)
    with closing(NativeDrain(library)) as native:
        with pytest.raises(BundleCorruptionError, match="compressed frame"):
            native.check(compressed[:-1], rows, chunk)
        with pytest.raises(BundleCorruptionError, match="extent changed"):
            native.check(encoder.compress(b"".join(raw) + b"surplus"), rows, chunk)
