from types import SimpleNamespace

import pytest

from leo.cli.position_scan import record_position_run


def test_position_dry_run_has_no_storage_or_radio(tmp_path):
    preview = record_position_run(tmp_path, "position", "192.168.1.15", "serial", dry_run=True)
    assert len(preview["configuration"]["targets"]) == 24
    assert preview["analysis_path"] == "interior-position"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("fail", [False, True])
def test_position_cli_seals_native_iq_and_publishes_truthful_terminal(tmp_path, fail):
    from pluto_plus.adaptive_scan import VisitResult
    from pluto_plus.position_scan import PositionVisit

    from leo.contracts.position_scan import PositionRunCheckpointV1
    from leo.storage.short_window import ShortWindowReader

    def capture(uri, serial, output, **kwargs):
        record = PositionVisit(
            session=1,
            generation=2,
            visit=0,
            selection_counter=0,
            transition_before=0,
            load_after=1,
            recall_before=2,
            transition_after=10,
            valid_start=200_010,
            valid_end=400_010,
            frequency_hz=1_081_328_125,
            verified_frequency_hz=1_081_328_124,
            iq_bytes=1_600_000,
            missing_samples_before=0,
            analog_bandwidth_hz=8_000_000,
            source_rate_hz=10_000_000,
            target=0,
            profile=0,
            result=VisitResult.COMPLETE,
            eligible_mask=0xFF_FFFF,
            effective_weight=65536,
            profile_crc32=123,
            original_profile_crc32=456,
            slot_generation=1,
            sweep=0,
            plan_digest=b"a" * 32,
        )
        kwargs["on_visit"](SimpleNamespace(record=record, iq=bytes(1_600_000)), {})
        if fail:
            raise RuntimeError("fixture capture failure")
        return {
            "terminal": {"error": 0, "planned": 1},
            "host_restoration": {"fastlock_inactive": True},
        }

    if fail:
        with pytest.raises(RuntimeError, match="capture failure"):
            record_position_run(tmp_path, "position", "fixture", "serial", capture_function=capture)
    else:
        record_position_run(tmp_path, "position", "fixture", "serial", capture_function=capture)
    path = tmp_path / "position"
    checkpoint = PositionRunCheckpointV1.model_validate_json((path / "run.json").read_text())
    assert checkpoint.state == ("failed" if fail else "stopped")
    assert checkpoint.captured_windows == checkpoint.durable_windows == 1
    rows = list(ShortWindowReader(path / "native" / "position-segment-00000000").windows())
    assert len(rows) == 1 and rows[0].samples.shape == (200_000, 2, 2)
    assert rows[0].index.acquisition["axis"] == "X"
