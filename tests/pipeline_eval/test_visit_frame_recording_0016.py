import json
from contextlib import nullcontext
from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader
from reports.ALGO08.v3.frame_visit_0016 import SelectiveMember
from reports.ALGO08.v3.owned_capture_0016 import ordinary_capture
from reports.ALGO08.v3.visit_frame_recording_0016 import recording_input, write_table, writer_scope


def test_writer_preserves_ordinary_index_lifecycle_and_seek_on_multiple_members(tmp_path):
    metadata = SimpleNamespace(configuration=dict(sample_rate_hz=10_000_000, window_ms=20),
                               radio={}, receiver_ids=(0, 1), status="incomplete",
                               stop_reason="fault", failure="saved timeout")
    counts = [0] * 64 + [0, 40_000, 80_000, 120_000, 200_000]
    windows = []
    for i, count in enumerate(counts):
        row = SimpleNamespace(sequence=i, target_id="tx", acquisition={"global_visit": i},
                              powers=({}, {}))
        samples = np.full((count, 2, 2), i, dtype="<i2")
        samples[80_000:] += 7
        windows.append(SimpleNamespace(index=row, samples=samples))
    source_path, target_path = tmp_path / "original", tmp_path / "fresh-segment"
    ordinary_capture(source_path, metadata, windows)
    reader = ShortWindowReader(source_path)
    counters = dict(max_accounted_bytes=0)
    report, costs, events = writer_scope(reader, target_path, nullcontext, nullcontext,
                                         None, tmp_path, counters)
    assert report["manifest_sha256"] != reader.manifest_sha256
    assert report["lifecycle"]["failure"] == metadata.failure
    assert [i for _, i in events] == list(range(len(windows)))
    assert costs["payload_extent_counts"] == [(0, 65), (320_000, 1), (640_000, 1),
                                               (960_000, 1), (1_600_000, 1)]
    stock = ShortWindowReader(target_path)
    assert [w.samples.tobytes() for w in stock.windows()] == [w.samples.tobytes() for w in windows]
    assert len(report["members"]) == 2 and counters["max_accounted_bytes"] > 0
    for chunk, member in zip(stock.manifest.chunks, report["members"], strict=True):
        decoded = SelectiveMember(stock, member["side_sha256"], chunk=chunk,
                                  side_name=member["side_name"])
        table = json.loads((target_path / member["side_name"]).read_bytes())
        assert table["records"][0]["sequence"] == chunk.first_sequence
        for row in decoded.rows:
            expected = windows[row.sequence].samples
            np.testing.assert_array_equal(decoded.read(row, full=False), expected[:80_000])
            np.testing.assert_array_equal(decoded.read(row, full=True), expected)
    first, second = report["members"]
    with pytest.raises(BundleCorruptionError, match="identity"):
        SelectiveMember(stock, first["side_sha256"], chunk=stock.manifest.chunks[1],
                        side_name=first["side_name"])
    assert first["side_sha256"] != second["side_sha256"]


def test_write_table_refuses_payload_rows_outside_original_order(tmp_path):
    chunk = SimpleNamespace(window_count=2, first_sequence=64)
    with pytest.raises(ValueError, match="ordered"):
        write_table(tmp_path / "bad.json", "unused", chunk,
                    [{"sequence": 1}, {"sequence": 0}], "test")


def test_recording_input_requires_external_pin_and_carries_case_configuration(tmp_path):
    doc = dict(case="example", custody="/dev/shm/prior/receipt.json", custody_sha256="receipt",
               recording="/dev/shm/prior/raw", manifests=[["manifest", 2, 1]], windows=2,
               limit=10_000, repeat_qualified_member=False, extents=[[0, 1], [320_000, 1]])
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="both"):
        recording_input(path)
    with pytest.raises(ValueError, match="authority digest"):
        recording_input(path, "tampered")
    config = recording_input(path, sha256(path.read_bytes()).hexdigest())
    assert config.case == doc["case"] and config.extents == ((0, 1), (320_000, 1))
    assert config.manifests == (("manifest", 2, 1),) and not config.repeat_qualified_member
    assert recording_input().repeat_qualified_member
