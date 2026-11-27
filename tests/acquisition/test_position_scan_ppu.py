from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from leo.acquisition.position_scan_ppu import position_window
from leo.scanner.position_scan import PositionScanConfiguration, position_targets
from leo.scanner.short_window import ShortWindowAcquisition
from leo.storage.continuous_window import ContinuousWindowWriter
from leo.storage.short_window import ShortWindowReader


def test_native_rate_baseline_and_legacy_bounds():
    from leo.scanner.continuous_window import ContinuousWindowConfiguration

    targets = position_targets()[:8]
    low = ContinuousWindowConfiguration(targets=targets)
    high = ContinuousWindowConfiguration(targets=targets, sample_rate_hz=10_000_000)
    assert low.window_samples == 50_000 and high.window_samples == 200_000
    assert high.reserve_bytes >= 512 * 1_600_000
    with pytest.raises(ValueError, match="eight"):
        ContinuousWindowConfiguration(targets=position_targets())
    with pytest.raises(ValueError, match="20 ms"):
        ShortWindowAcquisition(
            samples=np.zeros((200_000, 2, 2), dtype="<i2"),
            requested_if_center_hz=1_000_000_000,
            actual_if_center_hz=1_000_000_000,
        )


def test_position_adapter_native_chunks_preserve_24_identity_and_power(tmp_path):
    from pluto_plus.adaptive_scan import VisitResult
    from pluto_plus.position_scan import PositionVisit

    config = PositionScanConfiguration(
        targets=position_targets(), chunk_windows=4, segment_windows=24
    )
    writer = ContinuousWindowWriter(tmp_path, "position", config, radio={})
    for sequence in range(48):
        target = sequence % 24
        hz = config.targets[target].if_center_hz
        start = (1 << 32) + sequence * 450_000
        record = PositionVisit(
            session=1,
            generation=2,
            visit=sequence,
            selection_counter=start - 220_000,
            transition_before=start - 220_000,
            load_after=start - 210_000,
            recall_before=start - 209_000,
            transition_after=start - 200_000,
            valid_start=start,
            valid_end=start + 200_000,
            frequency_hz=hz,
            verified_frequency_hz=hz - 2,
            iq_bytes=1_600_000,
            missing_samples_before=0,
            analog_bandwidth_hz=8_000_000,
            source_rate_hz=10_000_000,
            target=target,
            profile=target % 8,
            result=VisitResult.COMPLETE,
            eligible_mask=0xFF_FFFF,
            effective_weight=65536,
            profile_crc32=123,
            original_profile_crc32=456,
            slot_generation=sequence // 8 + 1,
            sweep=sequence // 24,
            plan_digest=b"a" * 32,
        )
        item = SimpleNamespace(record=record, iq=bytes(1_600_000))
        window = position_window(item, config)
        assert window["acquisition"]["actual_if_center_hz"] == hz - 2
        assert len(window["powers"]) == 2
        writer.append(**window)
    result = writer.finish(stop_reason="explicit_stop")
    assert result["durable_windows"] == 48
    rows = []
    for segment in sorted(tmp_path.glob("position-segment-*")):
        reader = ShortWindowReader(segment)
        assert reader.manifest.schema_version == 2
        rows.extend(reader.windows())
    assert [row.index.acquisition["global_visit"] for row in rows] == list(range(48))
    assert [row.index.target_id for row in rows[:24]] == [t.target_id for t in config.targets]
    assert all(row.index.acquisition["analysis_path"] == "interior-position" for row in rows)
    wrong = SimpleNamespace(record=replace(record, target=0), iq=item.iq)
    with pytest.raises(ValueError, match="logical"):
        position_window(wrong, config)
