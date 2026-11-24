from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

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
