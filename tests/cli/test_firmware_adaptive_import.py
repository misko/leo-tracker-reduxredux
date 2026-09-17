from pathlib import Path

import pytest

import leo.cli.firmware_adaptive_import as importer


def document(*, first_frequency: int = 959_687_498) -> dict:
    rate = 10_000_000
    return {
        "schema": "org.leo.firmware-adaptive-iq/v1",
        "physical_receiver": 0,
        "session_id": "scan-fw-test",
        "setup": {
            "source_rate_hz": rate,
            "analog_bandwidth_hz": rate,
            "transition_budget_ms": 20,
            "duration_ms": 300_000,
            "generation": 7,
            "session": 11,
            "analysis_digest": "a" * 64,
        },
        "visits": [
            {
                "iq": {"relative_path": "visit-000000.ci16.zst"},
                "record": {
                    "frequency_hz": first_frequency,
                    "selection_counter": 1_000_000_000,
                    "transition_before": 1_000_010_000,
                    "valid_start": 1_000_200_000,
                    "valid_end": 1_001_400_000,
                },
            }
        ],
    }


def test_firmware_events_require_the_actual_canonical_pilot_center() -> None:
    exact = document()
    plan = importer._plan(exact)

    event = importer._events(exact, plan)[0]
    assert event.actual_lo_frequency_hz == 959_687_498
    assert event.actual_if_offset_hz == 2

    offset = document(first_frequency=960_000_000)
    with pytest.raises(importer.UnsupportedFirmwareArchiveError, match="not centred"):
        importer._events(offset, importer._plan(offset))


def test_pending_import_keeps_known_unsupported_archives_visible(monkeypatch, tmp_path) -> None:
    for name in ("scan-fw-old", "scan-fw-new"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "manifest.json").write_text("{}")

    def fake_import(path: Path, _bulk: Path) -> str:
        if path.name == "scan-fw-old":
            raise importer.UnsupportedFirmwareArchiveError("old center")
        return path.name

    monkeypatch.setattr(importer, "import_archive", fake_import)

    imported, unsupported = importer.import_pending(tmp_path, tmp_path / "bulk")

    assert imported == ("scan-fw-new",)
    assert unsupported == ({"session_id": "scan-fw-old", "reason": "old center"},)
