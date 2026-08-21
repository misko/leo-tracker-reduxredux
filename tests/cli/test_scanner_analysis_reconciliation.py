from __future__ import annotations

from types import SimpleNamespace

import leo.cli.scanner as scanner_module
from leo.cli.scanner import (
    STANDARD_SCANNER_ANALYSIS_ID,
    reconcile_published_standard_scanner_analyses,
    run_published_standard_scanner_analysis,
)
from leo.storage.errors import BundleNotFoundError


def _bundle(scan_id: str, *, lower_ns: int = 1_000_000_000, upper_ns: int = 1_040_000_000):
    return SimpleNamespace(
        scan_id=scan_id,
        uri=f"bulk://scanner-recordings/2026/08/21/{scan_id}",
        manifest_sha256="sha256:" + "a" * 64,
        manifest=SimpleNamespace(
            frames=(
                SimpleNamespace(
                    host_request_monotonic_ns_lower=lower_ns,
                    host_request_monotonic_ns_upper=upper_ns,
                ),
            )
        ),
    )


class _IqStore:
    def __init__(self) -> None:
        self.bundles = {scan_id: _bundle(scan_id) for scan_id in ("scan-old", "scan-new")}

    def recording_ids(self):
        return tuple(self.bundles)

    def inspect(self, scan_id):
        return self.bundles[scan_id]


class _AnalysisStore:
    def __init__(self) -> None:
        self.existing = {"scan-old"}

    def inspect(self, scan_id, analysis_id):
        assert analysis_id == STANDARD_SCANNER_ANALYSIS_ID
        if scan_id not in self.existing:
            raise BundleNotFoundError("missing")
        bundle = _bundle(scan_id)
        return SimpleNamespace(
            report=SimpleNamespace(scan_id=scan_id),
            metrics=SimpleNamespace(
                input_uri=bundle.uri,
                input_manifest_sha256=bundle.manifest_sha256,
            ),
        )


def test_reconciliation_analyzes_only_missing_recordings(monkeypatch) -> None:
    iq_store = _IqStore()
    analysis_store = _AnalysisStore()
    calls = []

    def analyze(_iq_store, _analysis_store, bundle, *, capture_elapsed_ms):
        calls.append((bundle.scan_id, capture_elapsed_ms))
        analysis_store.existing.add(bundle.scan_id)
        return SimpleNamespace(scan_id=bundle.scan_id)

    monkeypatch.setattr(scanner_module, "run_published_standard_scanner_analysis", analyze)

    result = reconcile_published_standard_scanner_analyses(iq_store, analysis_store)  # type: ignore[arg-type]

    assert calls == [("scan-new", 40.0)]
    assert result.discovered == 2
    assert result.already_analyzed == 1
    assert result.analyzed == ("scan-new",)
    assert result.failed == ()


def test_published_standard_analysis_reuses_verified_existing_product(monkeypatch) -> None:
    bundle = _bundle("scan-existing")
    analysis_store = _AnalysisStore()
    analysis_store.existing.add(bundle.scan_id)

    def unexpected(*_args, **_kwargs):
        raise AssertionError("existing analysis must not be recomputed")

    monkeypatch.setattr(scanner_module, "live_scanner_analysis_source", unexpected)

    report = run_published_standard_scanner_analysis(  # type: ignore[arg-type]
        _IqStore(),
        analysis_store,
        bundle,
        capture_elapsed_ms=40.0,
    )

    assert report.scan_id == "scan-existing"
