from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from leo.scanner import (
    ScannerRunManifestV1,
    ScannerRunSweepEntryV1,
    compile_scheduled_scanner_run_intent_v1,
)
from leo.storage import ScannerRunStore


def _manifest() -> ScannerRunManifestV1:
    scheduled_for = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    intent = compile_scheduled_scanner_run_intent_v1(
        operation_key="scheduled-scanner:20260821T080000Z",
        radio_id="radio-a",
        radio_serial="serial-a",
        scheduled_for=scheduled_for,
        interval_seconds=1_200,
        maximum_lateness_seconds=120,
        run_duration_seconds=300,
        dwell_ms=120,
        gain_db=40.0,
        margin_gate=0.025,
        maximum_acquisition_candidates=8,
    )
    return ScannerRunManifestV1(
        run_id="scan-run-test",
        intent=intent,
        radio_id="radio-a",
        radio_serial="serial-a",
        radio_uri="ip:192.0.2.1",
        started_utc_ns=1_700_000_000_000_000_000,
        finalized_utc_ns=1_700_000_300_000_000_000,
        capture_elapsed_ms=300_000.0,
        status="complete",
        stop_reason="300-second capture window reached at a sweep boundary",
        sweeps=(
            ScannerRunSweepEntryV1(
                scan_id="scan-test-0001",
                capture_elapsed_ms=960.0,
                iq_bundle_uri="bulk://scanner-recordings/2026/08/21/scan-test-0001",
                iq_manifest_sha256="sha256:" + "a" * 64,
                report_filename="starlink-scan-20260821T080000Z-scan-test-0001.json",
            ),
        ),
    )


def test_scanner_run_store_atomically_publishes_and_reopens_manifest(tmp_path) -> None:
    store = ScannerRunStore(tmp_path)
    manifest = _manifest()

    published = store.publish(manifest)
    reopened = store.inspect(manifest.run_id)

    assert reopened.manifest == manifest
    assert reopened.manifest_sha256 == published.manifest_sha256
    assert reopened.uri.endswith("/scanner-runs/2023/11/14/scan-run-test")
    assert list(store.spool_root.iterdir()) == []


def test_scanner_run_store_duplicate_is_immutable_and_cleans_attempt_spool(tmp_path) -> None:
    store = ScannerRunStore(tmp_path)
    manifest = _manifest()
    store.publish(manifest)

    with pytest.raises(FileExistsError):
        store.publish(manifest)

    assert list(store.spool_root.iterdir()) == []
    assert store.inspect(manifest.run_id).manifest == manifest


def test_scanner_run_store_rejects_unsafe_identity_and_qnap_root(tmp_path) -> None:
    store = ScannerRunStore(tmp_path)

    with pytest.raises(ValueError, match="safe persisted identifier"):
        store.inspect("../escape")
    with pytest.raises(ValueError, match="beneath QNAP"):
        ScannerRunStore(Path("/mnt/qnap01/scanner-runs"))
