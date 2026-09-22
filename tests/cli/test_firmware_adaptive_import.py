from pathlib import Path

import pytest

import leo.cli.firmware_adaptive_import as importer
from leo.scanner.adaptive_hop import AdaptiveHopReceiptV2, AdaptiveHopReceiptV3
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
            "preparation": {"original": settings},
            "restoration": {"observed": settings},
        },
    }


def dual_document(rate: int, *, complete: bool = True) -> dict:
    dwell = rate * 120 // 1000
    guard = rate // 1000
    final = 10_000_000_000
    valid_start = final - dwell
    settings = {
        "center_frequency_hz": 1_000_000_000,
        "sample_rate_hz": rate,
        "bandwidth_hz": rate,
        "gain_modes": ["manual", "manual"],
        "gain_db": [40.0, 40.0],
    }
    return {
        "schema": "org.leo.firmware-adaptive-iq/v1",
        "sample_layout": "sample_rx_iq_interleaved",
        "physical_receivers": [0, 1],
        "classifier_physical_receiver": 1,
        "session_id": f"scan-fw-dual-{rate}",
        "setup": {
            "source_rate_hz": rate,
            "duration_ms": 300_000,
            "generation": 7,
            "session": 11,
            "analysis_digest": "a" * 64,
            "rx_mask": 3,
        },
        "visits": [
            {
                "iq": {"relative_path": "visit-000000.ci16.zst"} if complete else None,
                "record": {
                    "frequency_hz": 959_687_498 if rate == 2_500_000 else 960_000_000,
                    "selection_counter": valid_start - 2 * guard,
                    "transition_before": valid_start - guard,
                    "valid_start": valid_start,
                    "valid_end": final,
                },
            }
        ],
        "terminal": {"restore_after": final + 1},
        "evidence": {
            "radio_serial": importer.DUAL_SERIAL,
            "preparation": {"original": settings},
            "restoration": {"observed": settings},
        },
    }


@pytest.mark.parametrize(
    ("rate", "receipt_type"),
    [(2_500_000, AdaptiveHopReceiptV2), (10_000_000, AdaptiveHopReceiptV3)],
)
def test_dual_firmware_receipt_preserves_both_receivers(rate, receipt_type) -> None:
    receipt = importer._receipt(dual_document(rate), "sha256:" + "b" * 64)

    assert isinstance(receipt, receipt_type)
    assert receipt.radio_serial == importer.DUAL_SERIAL
    assert receipt.radio_uri == importer.DUAL_URI
    assert receipt.plan.geometry.receiver_ids == (0, 1)
    assert receipt.plan.classification_receiver == 1
    assert receipt.plan.policy.allowed_target_mask == 0x0F
    assert receipt.valid_sample_count == rate * 120 // 1000


def test_dual_firmware_receipt_refuses_unrepresented_sparse_iq() -> None:
    with pytest.raises(importer.UnsupportedFirmwareArchiveError, match="sparse dual"):
        importer._receipt(dual_document(2_500_000, complete=False), "sha256:" + "b" * 64)


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
