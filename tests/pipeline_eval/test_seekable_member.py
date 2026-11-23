import json
from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3 import seekable_member as seek


def original(tmp_path, *, fail_after=False, wrong_member_digest=False):
    source = tmp_path / "source"
    source.mkdir()
    raw = [bytes((2 * visit + 1,)) * seek.PART_BYTES[0]
           + bytes((2 * visit + 2,)) * seek.PART_BYTES[1] for visit in range(3)]
    rows = [dict(schema_version=2, sequence=visit, target_id="target", sample_count=seek.SAMPLES,
                 receiver_count=2, payload_offset_bytes=visit * seek.WINDOW_BYTES,
                 payload_bytes=seek.WINDOW_BYTES, iq_sha256=seek.digest(samples),
                 acquisition={"visit": visit}, powers=[{}, {}])
            for visit, samples in enumerate(raw)]
    index = b"\n".join(json.dumps(row).encode() for row in rows) + b"\n"
    document = dict(schema_version=2, session_id="source",
                    configuration={"sample_rate_hz": 10_000_000, "window_ms": 20},
                    radio={}, sample_rate_hz=10_000_000, receiver_ids=[0, 1], created_utc_ns=1,
                    finalized_utc_ns=2, status="complete", stop_reason="test", window_count=3)
    chunk = dict(chunk_index=0, first_sequence=0, window_count=3,
                 payload_relative_path="iq.zst", index_relative_path="index.jsonl",
                 uncompressed_bytes=3 * seek.WINDOW_BYTES, compressed_bytes=1,
                 index_bytes=len(index), compressed_sha256=seek.digest(b"x"),
                 index_sha256=seek.digest(index), uncompressed_sha256=seek.digest(
                     b"" if wrong_member_digest else b"".join(raw)))
    document["chunks"] = [chunk]
    manifest_bytes = json.dumps(document).encode()
    (source / "manifest.json").write_bytes(manifest_bytes)
    manifest = seek.ShortWindowManifestV2.model_validate(document)

    def windows(*, start_sequence, stop_sequence):
        assert (start_sequence, stop_sequence) == (0, len(rows))
        for row, data in zip(rows, raw, strict=True):
            yield SimpleNamespace(index=seek.ShortWindowIndexV2.model_validate(row),
                                  samples=np.frombuffer(data, dtype="<i2").reshape(-1, 2, 2))
        if fail_after:
            raise ValueError("Original decoded seal did not pass")

    reader = SimpleNamespace(path=source, manifest=manifest,
                             manifest_sha256=seek.digest(manifest_bytes),
                             windows=windows, _member=lambda *_: index)
    return reader, raw


def set_contents(path, data):
    path.chmod(0o600)
    path.write_bytes(data)


def seal(tmp_path):
    reader, raw = original(tmp_path)
    sidecar = tmp_path / "sidecar"
    return sidecar, seek.create(reader, 0, sidecar), raw


def test_random_full_reconstruction_and_short_read_coverage(tmp_path):
    path, pin, raw = seal(tmp_path)
    with seek.open_member(path, pin) as member:
        hold = member.read(2, full=False)
        assert hold == raw[2][:seek.PART_BYTES[0]]
        assert member.frames == 1 and member.full_checks == 0
        assert member.read(0, full=True) == raw[0]
        assert member.verify_all() == seek.digest(b"".join(raw))
    assert hold == raw[2][:seek.PART_BYTES[0]]


def test_unread_tail_corruption_is_outside_short_evidence(tmp_path):
    path, pin, raw = seal(tmp_path)
    tail = path / "tail.zst"
    data = bytearray(tail.read_bytes())
    data[10] ^= 1
    set_contents(tail, data)
    with seek.open_member(path, pin) as member:
        assert member.read(0, full=False) == raw[0][:seek.PART_BYTES[0]]
        with pytest.raises(ValueError, match="digest"):
            member.read(0, full=True)


def test_payload_omission_and_same_size_reordering_rejected(tmp_path):
    path, pin, _ = seal(tmp_path)
    prefix = path / "prefix.zst"
    data = prefix.read_bytes()
    set_contents(prefix, data[:-1])
    with pytest.raises(ValueError, match="omits"), seek.open_member(path, pin):
        pytest.fail("Missing committed data was accepted")
    table = json.loads((path / "seek.json").read_bytes())
    second_start = table["records"][1]["parts"][0][0]
    set_contents(prefix, data[second_start:] + data[:second_start])
    with seek.open_member(path, pin) as member, pytest.raises(ValueError, match="digest"):
        member.read(0, full=False)


@pytest.mark.parametrize("operation", ["omission", "reorder"])
def test_detached_root_and_seek_table_structure(tmp_path, operation):
    path, pin, _ = seal(tmp_path)
    manifest = path / "seek.json"
    table = json.loads(manifest.read_bytes())
    table["records"] = table["records"][:-1] if operation == "omission" else table["records"][::-1]
    changed = json.dumps(table).encode()
    set_contents(manifest, changed)
    with pytest.raises(ValueError, match="digest"):
        seek.Reader(path, pin)
    with pytest.raises(ValueError, match="omits|reorders"):
        seek.Reader(path, seek.digest(changed))


def test_source_final_check_precedes_sidecar_commit(tmp_path):
    source, _ = original(tmp_path, fail_after=True)
    path = tmp_path / "sidecar"
    with pytest.raises(ValueError, match="Original decoded seal"):
        seek.create(source, 0, path)
    assert not (path / "seek.json").exists()


def test_full_readback_also_checks_original_member_digest(tmp_path):
    source, _ = original(tmp_path, wrong_member_digest=True)
    path = tmp_path / "sidecar"
    pin = seek.create(source, 0, path)
    with (seek.open_member(path, pin) as member,
          pytest.raises(ValueError, match="Original decoded member digest")):
        member.verify_all()
