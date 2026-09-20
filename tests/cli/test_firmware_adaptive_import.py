import json
from pathlib import Path

import pytest

import leo.cli.firmware_adaptive_import as importer
from leo.scanner.host_adaptive import HostAdaptiveHopReceiptV4, HostAdaptiveHopReceiptV5


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


def sparse_document(rate: int) -> dict:
    dwell = rate * 120 // 1000
    guard = rate // 1000
    count = 4
    final = 10_000_000_000
    source_first = final - rate * 300
    first_valid = source_first + guard
    visits = []
    for ordinal in range(count):
        valid_start = first_valid + ordinal * (dwell + guard)
        visits.append(
            {
                "iq": None if ordinal == 1 else {"relative_path": f"visit-{ordinal:06d}.ci16.zst"},
                "record": {
                    "frequency_hz": 959_687_498,
                    "selection_counter": valid_start - 2 * guard,
                    "transition_before": valid_start - guard,
                    "valid_start": valid_start,
                    "valid_end": valid_start + dwell,
                },
            }
        )
    # The importer derives the 300-second source origin from the last record.
    shift = final - visits[-1]["record"]["valid_end"]
    for entry in visits:
        for key in ("selection_counter", "transition_before", "valid_start", "valid_end"):
            entry["record"][key] += shift
    settings = {
        "center_frequency_hz": 1_000_000_000,
        "sample_rate_hz": rate,
        "bandwidth_hz": rate,
        "gain_modes": ["manual"],
        "gain_db": [40.0],
    }
    return {
        "schema": "org.leo.firmware-adaptive-iq/v1",
        "physical_receiver": 0,
        "session_id": f"scan-fw-sparse-{rate}",
        "setup": {
            "source_rate_hz": rate,
            "duration_ms": 300_000,
            "generation": 7,
            "session": 11,
            "analysis_digest": "a" * 64,
        },
        "visits": visits,
        "terminal": {"restore_after": final + 1},
        "evidence": {
            "radio_serial": "1040007c4a94000211000b009186843ef2",
            "radio_uri": "ip:192.168.1.18",
            "preparation": {"original": settings},
            "restoration": {"observed": settings},
        },
    }


@pytest.mark.parametrize(
    ("rate", "receipt_type"),
    [
        (10_000_000, HostAdaptiveHopReceiptV5),
        (15_000_000, HostAdaptiveHopReceiptV4),
        (20_000_000, HostAdaptiveHopReceiptV4),
    ],
)
def test_sparse_firmware_receipt_preserves_source_gap_without_interpolation(
    rate, receipt_type
) -> None:
    receipt = importer._receipt(sparse_document(rate), "sha256:" + "b" * 64)

    assert isinstance(receipt, receipt_type)
    assert receipt.retained_visit_indices == (0, 2, 3)
    assert tuple(visit.event.visit_index for visit in receipt.visits) == (0, 2, 3)
    assert receipt.complete_visit_count == 3
    assert receipt.valid_sample_count == 3 * rate * 120 // 1000
    assert receipt.transport_missing_sample_count == rate * 120 // 1000
    assert receipt.unclassified_sample_count >= receipt.transport_missing_sample_count


def test_r18_archive_identity_is_bound_into_imported_receipt() -> None:
    receipt = importer._receipt(sparse_document(10_000_000), "sha256:" + "b" * 64)

    assert receipt.radio_id == "pluto-3ef2"
    assert receipt.radio_serial == "1040007c4a94000211000b009186843ef2"
    assert receipt.radio_uri == "ip:192.168.1.18"


def test_r17_archive_keeps_legacy_radio_id() -> None:
    value = sparse_document(10_000_000)
    value["evidence"]["radio_serial"] = "104000bac4950008230026001b440a003a"
    value["evidence"]["radio_uri"] = "ip:192.168.1.17"

    receipt = importer._receipt(value, "sha256:" + "b" * 64)

    assert receipt.radio_id == "pluto-003a"
    assert receipt.radio_serial == "104000bac4950008230026001b440a003a"
    assert receipt.radio_uri == "ip:192.168.1.17"


def test_archive_rejects_counter_timing_from_a_different_radio(tmp_path) -> None:
    value = sparse_document(10_000_000)
    value["evidence"]["counter_utc_timing"] = {"radio_serial": "wrong-radio"}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(value))

    with pytest.raises(ValueError, match="counter UTC radio identity differs"):
        importer._load(manifest)


def test_archive_rejects_malformed_counter_timing_identity(tmp_path) -> None:
    value = sparse_document(10_000_000)
    value["evidence"]["counter_utc_timing"] = []
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(value))

    with pytest.raises(ValueError, match="counter UTC evidence is malformed"):
        importer._load(manifest)
