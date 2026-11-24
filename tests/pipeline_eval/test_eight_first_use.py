from pathlib import Path
from types import SimpleNamespace

import numpy as np

from reports.ALGO08.v3 import eight_first_use as trial, seekable_member as seek


def test_capture_writer_roundtrips_complete_8_12_archive(tmp_path):
    capture, pin = trial.bound_capture()
    assert len(pin) == 64
    words = np.resize(np.asarray([-1649, 8191, 23, -112], dtype="<i2"), (seek.SAMPLES, 2, 2))
    item = SimpleNamespace(samples=words, index=SimpleNamespace(sequence=0, target_id="lane",
                            acquisition={"visit": 0}, powers=({}, {})))
    template = SimpleNamespace(configuration={"sample_rate_hz": 10_000_000, "window_ms": 20}, radio={}, receiver_ids=(0, 1))
    ordinary, _, stock = capture(tmp_path / "ordinary", "ordinary", template, (item,))
    stored, root_pin, alternate = capture(tmp_path / "split", "split-level-1", template, (item,),
                                         prefix_samples=seek.EIGHT_MS_SAMPLES)
    assert isinstance(ordinary, Path)
    assert stock["index_sha256"] == alternate["index_sha256"]
    assert stock["decoded_sha256"] == alternate["decoded_sha256"]
    with seek.open_member(stored, root_pin, prefix_samples=seek.EIGHT_MS_SAMPLES) as reader:
        reader.verify_encoded()
        assert reader.verified_encoded_frames == 2
        assert reader.verify_all() == seek.digest(words.tobytes())
