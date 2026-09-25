import json
from pathlib import Path

import numpy as np
import zstandard as zstd

import leo.scanner.adaptive_hop_analysis as detector
from leo.application.adaptive_hop_analysis import AdaptiveHopAnalysisService
from leo.cli import firmware_adaptive_import as importer
from leo.scanner.adaptive_hop_products import VariableDwellAnalysisBindingV8
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from tests.api.test_adaptive_hop_history_api import client_for
from tests.cli.test_firmware_adaptive_import import variable_dual_document
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell


def _publish_schema12(root: Path, dwell_ms: int = 240):
    archive = root / "firmware"
    archive.mkdir()
    value = variable_dual_document(2_500_000, dwell_ms)
    value["evidence"]["utc_timing"] = {
        "begin_before_realtime_ns": 1_790_000_000_000_000_000,
        "begin_before_monotonic_ns": 1_000_000_000,
        "begin_after_realtime_ns": 1_790_000_000_000_100_000,
        "begin_after_monotonic_ns": 1_000_050_000,
        "terminal_realtime_ns": 1_790_000_300_000_000_000,
        "terminal_monotonic_ns": 301_000_000_000,
    }
    samples = 2_500_000 * dwell_ms // 1_000
    raw = np.zeros((samples, 2, 2), dtype="<i2").tobytes()
    compressed = zstd.ZstdCompressor(level=1).compress(raw)
    (archive / "visit-000000.ci16.zst").write_bytes(compressed)
    value["visits"][0]["iq"].update(
        uncompressed_bytes=len(raw),
        compressed_sha256=importer.sha256_digest(compressed),
        uncompressed_sha256=importer.sha256_digest(raw),
    )
    (archive / "manifest.json").write_text(json.dumps(value))
    capture_root = root / "captures"
    capture_root.mkdir()
    session_id = importer.import_archive(archive, capture_root)
    return capture_root, session_id


def test_schema12_input_and_v8_metrics_use_separate_roots(tmp_path, monkeypatch):
    capture_root, session_id = _publish_schema12(tmp_path)
    metrics_root = tmp_path / "report" / "metrics"
    tracking_root = tmp_path / "report" / "tracking"
    metrics_root.mkdir(parents=True)
    tracking_root.mkdir(parents=True)
    capture_inventory = tuple(sorted(p.relative_to(capture_root) for p in capture_root.rglob("*")))
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)

    captures = AdaptiveHopIqStore(capture_root, read_only=True)
    products = AdaptiveHopAnalysisStore(metrics_root)
    try:
        result = AdaptiveHopAnalysisService(
            inputs=AdaptiveHopAnalysisInputStore(captures), products=products
        ).analyze_session(session_id, probe_stride_ms=120, maximum_visits=1)
    finally:
        products.close()
        captures.close()

    assert result.state == "metrics_complete"
    assert tuple(sorted(p.relative_to(capture_root) for p in capture_root.rglob("*"))) == (
        capture_inventory
    )
    presentation = AdaptiveHopAnalysisPresentationStore(
        capture_root, analysis_root=metrics_root, tracking_root=tracking_root
    )
    status = presentation.status(session_id, probe_stride_ms=120)
    assert status is not None and status.schema_version == 8
    assert status.state == "metrics_complete"
    client = client_for(capture_root, adaptive_hop_analysis=presentation)
    for api_version in ("v2", "v3"):
        response = client.get(
            f"/api/{api_version}/scanner/adaptive-sessions/{session_id}/analysis",
            params={"probe_stride_ms": 120},
        )
        assert response.status_code == 200
        assert response.json()["schema_version"] == 8
        assert response.json()["state"] == "metrics_complete"
    assert (
        client.get(
            f"/api/v1/scanner/adaptive-sessions/{session_id}/analysis",
            params={"probe_stride_ms": 120},
        ).status_code
        == 404
    )
    assert isinstance(presentation._binding(session_id, 120), VariableDwellAnalysisBindingV8)
    tracking = ScannerTrackingInputStore(capture_root, adaptive_analysis_root=metrics_root)
    try:
        source = tracking.load(session_id)
        assert source.capture_mode == "adaptive"
        assert len(source.probes) == 4
        assert tuple(probe.probe_start_ms for probe in source.probes) == (0, 0, 120, 120)
    finally:
        tracking.close()
    assert not any(tracking_root.iterdir())
