from __future__ import annotations

import json

import numpy as np
import pytest

from leo.contracts.states import StarlinkEdge
from leo.scanner.application import (
    CapturedScannerSweep,
    CapturedScanTarget,
)
from leo.scanner.models import ScannerConfiguration, ScanTarget
from leo.scanner.ports import ScanRadioBlock, ScanRadioIdentity
from leo.storage import ScannerIqStore, live_scanner_analysis_source


def _captured(*, fail_second: bool = False) -> CapturedScannerSweep:
    targets = (
        ScanTarget(
            channel=1,
            edge=StarlinkEdge.LOWER,
            rf_center_hz=10_000,
            if_center_hz=1_000,
        ),
        ScanTarget(
            channel=1,
            edge=StarlinkEdge.UPPER,
            rf_center_hz=11_000,
            if_center_hz=2_000,
        ),
    )
    configuration = ScannerConfiguration(
        lnb_lo_hz=9_000,
        sample_rate_hz=1_000,
        bandwidth_hz=1_000,
        dwell_ms=20,
        targets=targets,
    )

    def block(index: int, if_center_hz: int) -> ScanRadioBlock:
        positions = np.arange(20, dtype=np.float32) + index * 100
        samples = np.column_stack(
            (
                positions + 1j * (positions + 1),
                positions + 2 + 1j * (positions + 3),
            )
        ).astype(np.complex64)
        return ScanRadioBlock(
            samples=samples,
            requested_if_center_hz=if_center_hz,
            actual_if_center_hz=if_center_hz + index,
            tune_ms=1.0 + index,
            listen_ms=20.0,
            host_request_utc_ns=(
                1_700_000_000_000_000_000 + index * 20_000_000,
                1_700_000_000_020_000_000 + index * 20_000_000,
            ),
            host_request_monotonic_ns=(
                1_000_000_000 + index * 20_000_000,
                1_020_000_000 + index * 20_000_000,
            ),
        )

    return CapturedScannerSweep(
        identity=ScanRadioIdentity("radio-a", "serial-a", "ip:192.0.2.1"),
        configuration=configuration,
        capture_elapsed_ms=42.0,
        targets=(
            CapturedScanTarget(targets[0], block(0, 1_000), None),
            (
                CapturedScanTarget(targets[1], None, "RuntimeError: injected failure")
                if fail_second
                else CapturedScanTarget(targets[1], block(1, 2_000), None)
            ),
        ),
    )


def test_scanner_iq_store_publishes_one_framed_payload_and_reads_it_back(tmp_path) -> None:
    store = ScannerIqStore(tmp_path)

    published = store.publish("scan-test", _captured())

    assert published is not None
    assert published.uri.endswith("/scan-test")
    assert published.path.parent.parent.parent.parent == store.bundles_root
    assert sorted(path.name for path in published.path.iterdir()) == [
        "iq.ci16.zst",
        "manifest.json",
    ]
    manifest = published.manifest
    assert manifest.total_sample_count == 40
    assert [(frame.sample_start, frame.sample_count) for frame in manifest.frames] == [
        (0, 20),
        (20, 20),
    ]
    assert [frame.actual_if_center_hz for frame in manifest.frames] == [1_000, 2_001]
    assert [frame.actual_rf_center_hz for frame in manifest.frames] == [10_000, 11_001]
    assert manifest.failures == ()

    values = store.read_ci16("scan-test")
    assert values.shape == (40, 2, 2)
    assert values.dtype == np.dtype("<i2")
    assert values[0].tolist() == [[0, 1], [2, 3]]
    assert values[20].tolist() == [[100, 101], [102, 103]]
    assert not values.flags.writeable

    source = live_scanner_analysis_source(store, published)
    assert [item.source_sample_start for item in source.frames] == [0, 20]
    assert [item.samples.shape for item in source.frames if item.samples is not None] == [
        (20, 2, 2),
        (20, 2, 2),
    ]

    persisted = json.loads((published.path / "manifest.json").read_text())
    assert persisted["scan_id"] == "scan-test"
    assert persisted["sample_layout"] == "sample_receiver_iq"


def test_scanner_iq_store_records_failed_targets_without_fake_samples(tmp_path) -> None:
    store = ScannerIqStore(tmp_path)

    published = store.publish("scan-partial", _captured(fail_second=True))

    assert published is not None
    assert published.manifest.total_sample_count == 20
    assert [frame.target_index for frame in published.manifest.frames] == [0]
    assert [failure.target_index for failure in published.manifest.failures] == [1]
    assert "injected failure" in published.manifest.failures[0].reason
    source = live_scanner_analysis_source(store, published)
    assert source.frames[1].samples is None
    assert source.frames[1].error == "RuntimeError: injected failure"


def test_scanner_iq_store_lists_durable_recordings_for_reconciliation(tmp_path) -> None:
    store = ScannerIqStore(tmp_path)

    assert store.publish("scan-first", _captured()) is not None
    assert store.publish("scan-second", _captured()) is not None

    assert store.recording_ids() == ("scan-first", "scan-second")


def test_scanner_iq_store_rejects_non_ci16_evidence_before_publication(tmp_path) -> None:
    captured = _captured()
    first = captured.targets[0]
    assert first.block is not None
    invalid = first.block.samples.copy()
    invalid[0, 0] = np.complex64(0.5 + 1j)
    replacement = ScanRadioBlock(
        samples=invalid,
        requested_if_center_hz=first.block.requested_if_center_hz,
        actual_if_center_hz=first.block.actual_if_center_hz,
        tune_ms=first.block.tune_ms,
        listen_ms=first.block.listen_ms,
        host_request_utc_ns=first.block.host_request_utc_ns,
        host_request_monotonic_ns=first.block.host_request_monotonic_ns,
    )
    captured = CapturedScannerSweep(
        identity=captured.identity,
        configuration=captured.configuration,
        capture_elapsed_ms=captured.capture_elapsed_ms,
        targets=(
            CapturedScanTarget(first.target, replacement, None),
            captured.targets[1],
        ),
    )
    store = ScannerIqStore(tmp_path)

    with pytest.raises(ValueError, match="integer-valued CI16"):
        store.publish("scan-invalid", captured)

    assert not tuple(store.bundles_root.glob("*/*/*/scan-invalid"))
    assert not (store.spool_root / "scan-invalid.scanner.partial").exists()
