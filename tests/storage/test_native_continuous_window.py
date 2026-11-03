from dataclasses import replace
from threading import Event

import numpy as np
import pytest

from leo.scanner.continuous_recording import run_continuous_recording
from leo.storage.continuous_window import ContinuousWindowWriter
from leo.storage.short_window import ShortWindowReader
from tests.scanner.test_continuous_recording import configuration, Source


class NativeSource(Source):
    def next_window(self):
        window = super().next_window()
        return replace(window, acquisition=replace(window.acquisition,
            samples=np.zeros((200_000, 2, 2), dtype="<i2"), sample_rate_hz=10_000_000,
            sample_start=window.visit * 400_000))


def test_native_recording_rotates_and_reopens_exact_20ms_windows(tmp_path):
    config = configuration(sample_rate_hz=10_000_000)
    source = NativeSource(count=9)
    sink = ContinuousWindowWriter(tmp_path, "native", config, radio={})
    result = run_continuous_recording(source, config, sink, queue_bytes=16_000_000)
    assert result.fault is None
    assert result.written_windows == sink.durable_windows == 9
    assert sink.segment_index == 2
    rows = []
    for segment in sorted(tmp_path.glob("native-segment-*")):
        reader = ShortWindowReader(segment)
        assert reader.manifest.schema_version == 2
        assert reader.manifest.sample_rate_hz == 10_000_000
        rows.extend(reader.windows())
    assert all(row.samples.shape == (200_000, 2, 2) for row in rows)
    assert all(row.index.acquisition["complete"] for row in rows)
    assert all(row.index.acquisition["sample_rate_hz"] == 10_000_000 for row in rows)
    assert all(p["decision"] == "quiet" for row in rows for p in row.index.powers)


def test_native_reserve_accounts_for_complete_segment():
    config = configuration(sample_rate_hz=10_000_000)
    assert config.window_bytes == 1_600_000
    with pytest.raises(ValueError, match="reserve"):
        replace(config, reserve_bytes=config.window_bytes - 1)
