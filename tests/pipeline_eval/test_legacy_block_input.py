from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from leo.contracts.digests import sha256_digest
from leo.storage.errors import BundleCorruptionError
from test_legacy_block_seek import original

from reports.ALGO08.v3 import legacy_block_input as port


def test_preparation_matches_the_existing_map_after_full_stock_readback(tmp_path):
    reader, chunk, frame, windows = original(tmp_path)
    expected, _, _ = port.legacy.seal_map(reader, chunk, frame, windows)
    data, hashes, observed = port.prepare_member(reader, chunk)
    assert data == expected
    assert hashes == [row.index.iq_sha256 for row in windows]
    assert observed["indexed_blocks"] == len(windows)
    inventory = {
        "segments": [
            {
                "path": str(reader.path),
                "manifest_digest": reader.manifest_sha256,
                "windows": len(windows),
            }
        ]
    }
    ((bound_reader, bound_chunk),) = port.ordered_members(inventory)
    assert bound_reader.path == reader.path and bound_chunk == chunk


def test_preparation_requires_stock_eof_even_after_the_first_valid_prefix(tmp_path, monkeypatch):
    reader, chunk, _, _ = original(tmp_path)
    stock = port.stock_scope

    def broken(*args):
        yield next(stock(*args))
        raise BundleCorruptionError("late decoded checksum failure")

    monkeypatch.setattr(port, "stock_scope", broken)
    with pytest.raises(BundleCorruptionError, match="late decoded checksum"):
        port.prepare_member(reader, chunk)


def test_mixed_reader_exhausts_stock_fallback_and_checks_each_native_aperture(monkeypatch):
    first, second = (
        SimpleNamespace(
            chunk_index=i,
            first_sequence=i,
            window_count=1,
            uncompressed_bytes=16,
            compressed_bytes=12,
        )
        for i in range(2)
    )
    manifest = SimpleNamespace(chunks=(first, second), window_count=2, sample_rate_hz=10_000_000)
    reader = SimpleNamespace(manifest=manifest, manifest_sha256="capture")
    source = SimpleNamespace(start_sequence=0, stop_sequence=2, reader=reader, targets={"tx": {}})
    records = {
        ("capture", 0): {"map": None},
        ("capture", 1): {"map": "member", "map_sha256": "pin"},
    }
    audit, events = [], []
    sample = np.zeros((2, 2, 2), dtype="<i2")

    def stock(local):
        assert (local.start_sequence, local.stop_sequence) == (0, 1)
        yield SimpleNamespace(sequence=0, samples=sample)
        events.append("checked_stock_eof")

    class Coded:
        def __init__(self, selected_reader, chunk, data, pin, library):
            assert (selected_reader, chunk, data, pin) == (reader, second, b"table", "pin")
            self.rows = [
                SimpleNamespace(
                    sequence=1,
                    target_id="tx",
                    sample_count=2,
                    iq_sha256=sha256_digest(sample),
                    acquisition={},
                )
            ]
            self.counts = SimpleNamespace(report=dict)
            self.authentication = self.metadata = self.setup = {}

        def read(self, row, *, full):
            events.append((row.sequence, full))
            return sample[:1]

        def close(self):
            events.append("closed")

    monkeypatch.setattr(port, "checked_file", lambda *_: b"table")
    stream = port.mixed_windows(
        source,
        stock,
        records,
        Path("maps"),
        None,
        audit,
        SimpleNamespace(Selective=Coded, MAX_MAP=64),
    )
    assert next(stream).sequence == 0
    item = next(stream)
    assert item.sequence == 1 and item.samples.shape == sample.shape
    assert item.samples.realize(False) is item.samples.realize(False)
    with pytest.raises(ValueError, match="aperture"):
        item.samples.realize(True)
    assert list(stream) == []
    assert events == ["checked_stock_eof", (1, False), "closed"]
    assert [row["kind"] for row in audit] == ["ordinary", "map"]


def test_signed_member_roster_rejects_reordering(monkeypatch):
    reader = SimpleNamespace(manifest_sha256="manifest")
    chunks = [
        SimpleNamespace(
            chunk_index=i,
            first_sequence=i,
            window_count=1,
            uncompressed_bytes=16,
            compressed_bytes=12,
            compressed_sha256=f"payload{i}",
            index_sha256=f"index{i}",
            uncompressed_sha256=f"raw{i}",
        )
        for i in range(2)
    ]
    rows = [
        dict(port.member_identity(reader, chunk), map=None, map_sha256=None) for chunk in chunks
    ]
    inventory = {"window_count": 2}
    monkeypatch.setattr(port, "ordered_members", lambda _: ((reader, chunk) for chunk in chunks))
    custody = dict(
        schema=port.SCHEMA, session="original", inventory="digest", windows=2, members=rows
    )
    assert list(port.all_parts(custody, "original", "digest", inventory)) == [
        ("manifest", 0),
        ("manifest", 1),
    ]
    with pytest.raises(BundleCorruptionError, match="signed ordered member"):
        port.all_parts(custody | {"members": rows[::-1]}, "original", "digest", inventory)
