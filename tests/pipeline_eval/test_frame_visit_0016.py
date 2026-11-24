import json
from types import SimpleNamespace

import numpy as np
import pytest

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader
from reports.ALGO08.v3 import frame_visit_0016 as trial


def write(tmp_path, lengths):
    header = SimpleNamespace(
        configuration=dict(sample_rate_hz=10_000_000, window_ms=20),
        radio={}, receiver_ids=(0, 1), status="complete", stop_reason="test", failure=None,
    )
    windows = []
    for sequence, count in enumerate(lengths):
        raw = np.random.default_rng(sequence).integers(
            -4096, 4096, (count, 2, 2), dtype="<i2")
        row = SimpleNamespace(sequence=sequence, target_id="test",
                              acquisition={"chronology": sequence}, powers=({}, {}))
        windows.append(SimpleNamespace(index=row, samples=raw))
    path = tmp_path / "capture"
    manifest_pin, side_pin, chunk = trial.write_capture(path, header, windows, "frames")
    return path, windows, manifest_pin, side_pin, chunk


@pytest.mark.parametrize("lengths", [(0, 40_000, 80_000, 200_000, 0), (0, 0)])
def test_complete_reader_and_prefix_decoder_preserve_exact_rows_and_ci16(tmp_path, lengths):
    path, windows, manifest_pin, side_pin, chunk = write(tmp_path, lengths)
    reader = ShortWindowReader(path)
    assert reader.manifest_sha256 == manifest_pin
    full = list(reader.windows())
    selected = trial.SelectiveMember(reader, side_pin)
    assert selected.counts["authenticated_encoded_bytes"] == chunk["compressed_bytes"]
    assert [item.index for item in full] == selected.rows
    for supplied, complete in zip(windows, full, strict=True):
        assert supplied.index.acquisition == complete.index.acquisition
        np.testing.assert_array_equal(complete.samples, supplied.samples)
        np.testing.assert_array_equal(selected.read(complete.index, full=True), supplied.samples)
        np.testing.assert_array_equal(selected.read(complete.index, full=False), supplied.samples[:80_000])


def test_refuse_sidecar_and_skipped_suffix_corruption_under_frozen_pins(tmp_path):
    path, _, _, side_pin, chunk = write(tmp_path, (200_000, 200_000))
    assert trial.refusal(path, side_pin, chunk)["issued_visits"] == 0
    suffix = trial.refusal(path, side_pin, chunk, short_sequence=1)
    assert suffix["issued_visits"] == 0 and suffix["scheduled_short_sequence"] == 1
    assert len(trial.SelectiveMember(ShortWindowReader(path), side_pin).rows) == 2


def test_independently_pinned_sidecar_cannot_reorder_or_alias_frames(tmp_path):
    path, _, _, _, _ = write(tmp_path, (200_000, 200_000))
    sidecar = path / trial.SIDE
    metadata = json.loads(sidecar.read_bytes())
    metadata["records"][1]["offset"] = 0
    content = canonical_json_bytes(metadata)
    sidecar.write_bytes(content)
    with pytest.raises(BundleCorruptionError, match="consecutive partition"):
        trial.SelectiveMember(ShortWindowReader(path), sha256_digest(content))
