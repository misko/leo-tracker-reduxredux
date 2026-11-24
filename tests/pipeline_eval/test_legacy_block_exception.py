import ctypes as ct
from types import SimpleNamespace

import numpy as np
import pytest

from leo.contracts.digests import sha256_digest
from reports.ALGO08.v3 import legacy_block_exception as trial, legacy_block_seek as core


def test_later_treeless_blocks_cannot_silently_reuse_exception_table(monkeypatch):
    def describe(_frame, _expected, *, block_spans):
        block_spans.extend([(5, 1, 12, 1), (6, 1, 16, 0)])
        return {"checksum": True, "sequences": 1, "match_bytes": 4, "block_counts": {"compressed": 2},
                "literal_counts": {"huffman_new": 1, "huffman_reused": 1}}

    def literal(data):
        mode = "huffman_new" if data[0] == 1 else "huffman_reused"
        return mode, 0, 0, 0, 4

    monkeypatch.setattr(trial, "inspect", describe)
    monkeypatch.setattr(trial, "literal_section", literal)
    with pytest.raises(trial.UnsupportedExceptionLayout, match="exceptional table owner"):
        trial.layout(b"\0"*5 + b"\1\2", 32)
    assert trial.layout(b"\0"*5 + b"\1\1", 32) == ([[5, 1, 0, 16, 0], [6, 1, 16, 16, 1]], 0)


@pytest.fixture
def source(monkeypatch):
    frame, raw = b"compressed", bytes(range(32))
    samples = np.frombuffer(raw, dtype="<i2").reshape(-1, 2, 2)
    row = SimpleNamespace(sequence=0, payload_offset_bytes=0, payload_bytes=len(raw), iq_sha256=sha256_digest(raw))
    chunk = SimpleNamespace(chunk_index=0, first_sequence=0, window_count=1, uncompressed_bytes=len(raw),
                            compressed_sha256=sha256_digest(frame), index_sha256="index", uncompressed_sha256=sha256_digest(raw),
                            payload_relative_path="samples.zst", compressed_bytes=len(frame))
    manifest = SimpleNamespace(chunks=(chunk,), schema_version=2, receiver_ids=(0, 1), sample_rate_hz=10_000_000)
    reader = SimpleNamespace(manifest=manifest, manifest_sha256="manifest", _member=lambda *_: frame)
    monkeypatch.setattr(core, "read_rows", lambda *_: (row,))
    monkeypatch.setattr(trial, "layout", lambda *_: ([[0, 2, 0, 16, 0], [2, 2, 16, 8, 1], [4, 2, 24, 8, 2]], 1))
    monkeypatch.setattr(trial, "PREFIX", 16)
    side = trial.encode_sidecar(core, reader, chunk, frame, [SimpleNamespace(samples=samples, index=row)])
    return reader, chunk, row, frame, raw, side


class Native:
    def __init__(self, raw):
        self.raw = raw
        self.spans = []
        self.closed = 0
        self.decline = False

    def legacy_open(self):
        return 1

    def legacy_span(self, _context, _pointer, _size, _blocks, _count, _at, start, length, address, _counts):
        self.spans.append((start, length))
        if self.decline:
            return 0
        ct.memmove(address, self.raw[start:start+length], length)
        return 1

    def legacy_close(self, _context):
        self.closed += 1


def test_selective_span_does_not_decode_exception_and_reads_its_exact_bytes_when_needed(source):
    reader, chunk, row, _, raw, side = source
    binary = Native(raw)
    prepare = trial.open_optional(core, reader, chunk, side, sha256_digest(side), binary)
    try:
        assert prepare.read(row, full=False).tobytes() == raw[:16]
        assert binary.spans == [(0, 16)]
        assert prepare.read(row, full=True).tobytes() == raw
        assert binary.spans == [(0, 16), (0, 16), (24, 8)]
        assert prepare.reads["exception_bytes"] == 8
    finally:
        prepare.close()
    assert binary.closed == 1


def test_missing_or_unsupported_map_may_decline_before_read_but_changed_pin_is_an_error(source, monkeypatch):
    reader, chunk, _, _, raw, side = source
    binary = Native(raw)
    assert trial.open_optional(core, reader, chunk, None, None, binary) is None
    with pytest.raises(core.MapError, match="external pin"):
        trial.open_optional(core, reader, chunk, side+b"!", sha256_digest(side), binary)

    def unsupported(*_):
        raise trial.UnsupportedExceptionLayout("historical HUF dependency")

    monkeypatch.setattr(trial, "layout", unsupported)
    assert trial.open_optional(core, reader, chunk, side, sha256_digest(side), binary) is None
    assert not binary.spans


def test_declined_or_invalid_decoding_taints_same_reader(source):
    reader, chunk, row, _, raw, side = source
    binary = Native(raw)
    instance = trial.open_optional(core, reader, chunk, side, sha256_digest(side), binary)
    instance.read(row, full=False)
    binary.decline = True
    with pytest.raises(core.UnsupportedLayout, match="declined"):
        instance.read(row, full=True)
    with pytest.raises(core.MapError, match="tainted"):
        instance.read(row, full=False)
    assert binary.closed == 1

    invalid = Native(raw[::-1])
    corrupt = trial.open_optional(core, reader, chunk, side, sha256_digest(side), invalid)
    with pytest.raises(core.MapError, match="window hash"):
        corrupt.read(row, full=True)
    with pytest.raises(core.MapError, match="tainted"):
        corrupt.read(row, full=False)
    assert invalid.closed == 1
