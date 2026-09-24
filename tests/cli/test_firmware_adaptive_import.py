import json
from pathlib import Path

import numpy as np
import pytest
import zstandard as zstd

import leo.cli.firmware_adaptive_import as importer
from leo.scanner.adaptive_hop import (
    AdaptiveHopReceiptV4,
    AdaptiveHopReceiptV5,
    AdaptiveHopReceiptV6,
)
from leo.scanner.host_adaptive import HostAdaptiveHopReceiptV4, HostAdaptiveHopReceiptV5
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_history import AdaptiveHopPresentationStore


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
    target_bandwidth = 10_000_000 if rate == 15_000_000 else rate
    first_frequency = importer.scheduled_low_band_targets(bandwidth_hz=target_bandwidth)[
        0
    ].if_center_hz
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
                    "frequency_hz": first_frequency,
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


def variable_dual_document(rate: int, dwell_ms: int, *, slow_attack: bool = False) -> dict:
    value = dual_document(rate)
    value["setup"].update(protocol_version=3, dwell_ms=dwell_ms)
    value["visits"][0]["record"]["protocol_version"] = 3
    settings = value["evidence"]["preparation"]["original"]
    configured = json.loads(json.dumps(settings))
    configured["gain_modes"] = ["slow_attack", "slow_attack"] if slow_attack else ["manual"] * 2
    configured["gain_db"] = [0.0, 0.0] if slow_attack else [50.0, 50.0]
    value["evidence"]["preparation"]["configured"] = configured
    dwell = rate * dwell_ms // 1_000
    end = value["visits"][0]["record"]["valid_end"]
    value["visits"][0]["record"]["valid_start"] = end - dwell
    return value


@pytest.mark.parametrize("dwell_ms", [120, 240, 360])
@pytest.mark.parametrize("slow_attack", [False, True])
def test_protocol_three_receipt_preserves_actual_interval_and_gain(
    dwell_ms: int, slow_attack: bool
) -> None:
    rate = 2_500_000
    receipt = importer._receipt(
        variable_dual_document(rate, dwell_ms, slow_attack=slow_attack),
        "sha256:" + "b" * 64,
    )

    assert isinstance(receipt, AdaptiveHopReceiptV6)
    duration = receipt.events[0].valid_end_counter_exclusive - receipt.events[0].valid_start_counter
    assert duration == rate * dwell_ms // 1_000
    assert receipt.valid_sample_count == rate * dwell_ms // 1_000
    assert receipt.plan.geometry.active_valid_visit_ms == dwell_ms
    assert receipt.plan.geometry.gain_mode.value == ("slow_attack" if slow_attack else "manual")
    assert receipt.plan.geometry.gain_db == (None if slow_attack else 50.0)


def test_protocol_three_long_visit_stays_below_chunk_limit(tmp_path) -> None:
    rate = 10_000_000
    dwell_ms = 360
    archive = tmp_path / "scan-fw-variable-long"
    archive.mkdir()
    value = variable_dual_document(rate, dwell_ms)
    value["evidence"]["utc_timing"] = {
        "begin_before_realtime_ns": 1_790_000_000_000_000_000,
        "begin_before_monotonic_ns": 1_000_000_000,
        "begin_after_realtime_ns": 1_790_000_000_000_100_000,
        "begin_after_monotonic_ns": 1_000_050_000,
        "terminal_realtime_ns": 1_790_000_300_000_000_000,
        "terminal_monotonic_ns": 301_000_000_000,
    }
    samples = rate * dwell_ms // 1_000
    raw = np.zeros((samples, 2, 2), dtype="<i2").tobytes()
    compressed = zstd.ZstdCompressor(level=1).compress(raw)
    (archive / "visit-000000.ci16.zst").write_bytes(compressed)
    value["visits"][0]["iq"].update(
        uncompressed_bytes=len(raw),
        compressed_sha256=importer.sha256_digest(compressed),
        uncompressed_sha256=importer.sha256_digest(raw),
    )
    (archive / "manifest.json").write_text(json.dumps(value))
    bulk = tmp_path / "bulk"
    bulk.mkdir()

    session_id = importer.import_archive(archive, bulk)
    store = AdaptiveHopIqStore(bulk, read_only=True)
    try:
        manifest = store.inspect(session_id).manifest
        assert manifest.schema_version == 12
        assert len(manifest.chunks) == 1
        assert manifest.chunks[0].uncompressed_bytes == len(raw)
        assert manifest.chunks[0].uncompressed_bytes < 64 * 1024 * 1024
        assert manifest.compression.policy_id == "adaptive-one-visit-chunks-v1"
        assert manifest.compression.target_uncompressed_bytes == len(raw)
    finally:
        store.close()


@pytest.mark.parametrize(
    ("rate", "receipt_type"),
    [
        (2_500_000, AdaptiveHopReceiptV4),
        (10_000_000, AdaptiveHopReceiptV4),
        (15_000_000, AdaptiveHopReceiptV5),
    ],
)
def test_dual_firmware_receipt_preserves_both_receivers(rate, receipt_type) -> None:
    receipt = importer._receipt(dual_document(rate), "sha256:" + "b" * 64)

    assert isinstance(receipt, receipt_type)
    assert receipt.radio_serial == importer.DUAL_SERIAL
    assert receipt.radio_uri == importer.DUAL_URI
    assert receipt.plan.geometry.receiver_ids == (0, 1)
    assert receipt.plan.classification_receiver == 1
    assert receipt.plan.geometry.transition_guard_samples == 0
    assert receipt.plan.policy.allowed_target_mask == 0x0F
    assert receipt.valid_sample_count == rate * 120 // 1000


def test_dual_geometry_is_an_installed_package_resource() -> None:
    binding = importer._dual_geometry_binding()

    assert binding.fixture.fixture_part_id == "LT3D-001A"
    assert binding.radio.radio_serial == importer.DUAL_SERIAL


def test_dual_firmware_receipt_refuses_unrepresented_sparse_iq() -> None:
    with pytest.raises(importer.UnsupportedFirmwareArchiveError, match="sparse dual"):
        importer._receipt(dual_document(2_500_000, complete=False), "sha256:" + "b" * 64)


def test_feature104_dual_receipt_represents_sparse_15m_iq() -> None:
    value = dual_document(15_000_000)
    second = json.loads(json.dumps(value["visits"][0]))
    dwell = 15_000_000 * 120 // 1000
    for key in ("selection_counter", "transition_before", "valid_start", "valid_end"):
        second["record"][key] += dwell
    second["iq"] = None
    value["visits"].append(second)
    value["terminal"]["restore_after"] += dwell

    receipt = importer._receipt(value, "sha256:" + "b" * 64)

    assert isinstance(receipt, AdaptiveHopReceiptV5)
    assert receipt.retained_visit_indices == (0,)
    assert receipt.complete_visit_count == 1
    assert receipt.transport_missing_sample_count == dwell
    assert receipt.visits[0].event.visit_index == 0


def test_dual_firmware_receipt_preserves_zero_gap_repeated_target() -> None:
    value = dual_document(2_500_000)
    dwell = 2_500_000 * 120 // 1000
    final = value["visits"][0]["record"]["valid_end"]
    first = value["visits"][0]
    first["record"]["valid_start"] = final - 2 * dwell
    first["record"]["valid_end"] = final - dwell
    second = json.loads(json.dumps(first))
    second["record"].update(
        selection_counter=final - dwell,
        transition_before=final - dwell,
        valid_start=final - dwell,
        valid_end=final,
    )
    value["visits"].append(second)

    receipt = importer._receipt(value, "sha256:" + "b" * 64)

    assert receipt.events[1].invalid_start_counter == receipt.events[1].valid_start_counter
    assert receipt.events[1].transition_after_counter == receipt.events[1].valid_start_counter


@pytest.mark.parametrize(
    ("rate", "manifest_version", "history_version"),
    [(2_500_000, 9, 6), (15_000_000, 10, 7)],
)
def test_dual_firmware_archive_publishes_geometry_manifest(
    tmp_path, monkeypatch, rate, manifest_version, history_version
) -> None:
    archive = tmp_path / f"scan-fw-dual-{rate}"
    archive.mkdir()
    value = dual_document(rate)
    samples = rate * 120 // 1000
    if rate == 15_000_000:
        first = value["visits"][0]
        for ordinal in range(1, 5):
            repeated = json.loads(json.dumps(first))
            for key in ("selection_counter", "transition_before", "valid_start", "valid_end"):
                repeated["record"][key] += ordinal * samples
            value["visits"].append(repeated)
        value["terminal"]["restore_after"] += 4 * samples
    raw = np.zeros((samples, 2, 2), dtype="<i2").tobytes()
    compressed = zstd.ZstdCompressor(level=1).compress(raw)
    (archive / "visit-000000.ci16.zst").write_bytes(compressed)
    value["visits"][0]["iq"].update(
        uncompressed_bytes=len(raw),
        compressed_sha256=importer.sha256_digest(compressed),
        uncompressed_sha256=importer.sha256_digest(raw),
    )
    for entry in value["visits"][1:]:
        entry["iq"] = dict(value["visits"][0]["iq"])
    if rate == 15_000_000:
        value["visits"][-1]["iq"] = None
    value["evidence"]["utc_timing"] = {
        "begin_before_realtime_ns": 1_790_000_000_000_000_000,
        "begin_before_monotonic_ns": 1_000_000_000,
        "begin_after_realtime_ns": 1_790_000_000_000_100_000,
        "begin_after_monotonic_ns": 1_000_050_000,
        "terminal_realtime_ns": 1_790_000_300_000_000_000,
        "terminal_monotonic_ns": 301_000_000_000,
    }
    (archive / "manifest.json").write_text(json.dumps(value))
    (tmp_path / "bulk").mkdir()

    session_id = importer.import_archive(archive, tmp_path / "bulk")
    store = AdaptiveHopIqStore(tmp_path / "bulk", read_only=True)
    published = store.inspect(session_id)

    assert published.manifest.schema_version == manifest_version
    assert published.manifest.receipt.plan.geometry.receiver_ids == (0, 1)
    assert published.manifest.receiver_geometry.fixture.fixture_part_id == "LT3D-001A"
    assert published.manifest.receiver_geometry.radio.assignments[0].mapping_status == "provisional"
    store.close()
    page = AdaptiveHopPresentationStore(tmp_path / "bulk").page_v2(cursor=0, limit=20)
    assert page.items[0].session_id == session_id
    assert page.items[0].schema_version == history_version
    assert page.items[0].sample_rate_hz == rate
    if rate == 15_000_000:
        import leo.scanner.adaptive_hop_analysis as detector
        from leo.application.adaptive_hop_analysis import AdaptiveHopAnalysisService
        from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
        from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
        from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell

        monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
        captures = AdaptiveHopIqStore(tmp_path / "bulk", read_only=True)
        products = AdaptiveHopAnalysisStore(tmp_path / "bulk")
        try:
            result = AdaptiveHopAnalysisService(
                inputs=AdaptiveHopAnalysisInputStore(captures), products=products
            ).analyze_session(session_id, maximum_visits=4, maximum_seconds=30, probe_stride_ms=120)
            assert result.state == "metrics_complete"
        finally:
            products.close()
            captures.close()
        from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore

        status = AdaptiveHopAnalysisPresentationStore(tmp_path / "bulk").status(
            session_id, probe_stride_ms=120
        )
        assert status.schema_version == 7
        assert status.configuration.schema_version == 4
        assert status.configuration.sample_rate_hz == 15_000_000
        from tests.api.test_adaptive_hop_history_api import client_for

        client = client_for(
            tmp_path / "bulk",
            adaptive_hop_sessions_v2=AdaptiveHopPresentationStore(tmp_path / "bulk"),
            adaptive_hop_analysis=AdaptiveHopAnalysisPresentationStore(tmp_path / "bulk"),
        )
        base = f"/api/v3/scanner/adaptive-sessions/{session_id}"
        assert client.get(base).json()["schema_version"] == 7
        response = client.get(base + "/analysis?probe_stride_ms=120")
        assert response.status_code == 200
        assert response.json()["configuration"]["sample_rate_hz"] == 15_000_000


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
