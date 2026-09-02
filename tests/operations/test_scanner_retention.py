from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.operations import (
    CatalogRetentionService,
    HoldReceiptStore,
    PurgeExecutor,
    ScannerPurgeTombstoneStore,
    StorageUsage,
)
from leo.storage import RecordingStore


class _EmptyCatalog:
    def retention_candidates(self) -> tuple[()]:
        return ()


@dataclass(frozen=True)
class _ScannerManifest:
    created_utc_ns: int
    document: dict[str, object]

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return self.document


class _ScannerIq:
    def __init__(self, root: Path, scan_id: str = "scan-retain") -> None:
        self.root = root.resolve(strict=True)
        self.scan_id = scan_id
        self.path = root / "scanner-recordings" / "2026" / "08" / "21" / scan_id
        self.path.mkdir(parents=True)
        (self.path / "iq.ci16.zst").write_bytes(b"scanner-iq")
        self.document: dict[str, object] = {
            "schema_version": 4,
            "scan_id": scan_id,
            "created_utc_ns": 123,
        }
        (self.path / "manifest.json").write_bytes(canonical_json_bytes(self.document))
        self.uri = f"bulk://scanner-recordings/2026/08/21/{scan_id}"
        self.digest = sha256_digest(canonical_json_bytes(self.document))

    def recording_ids(self) -> tuple[str, ...]:
        return (self.scan_id,) if self.path.exists() else ()

    def inspect(self, scan_id: str):
        if scan_id != self.scan_id or not self.path.exists():
            raise FileNotFoundError(scan_id)
        return SimpleNamespace(
            scan_id=scan_id,
            path=self.path,
            uri=self.uri,
            manifest=_ScannerManifest(123, self.document),
            manifest_sha256=self.digest,
        )


class _ScannerAnalysis:
    def __init__(self, root: Path, *, available: bool = True) -> None:
        self.root = root.resolve(strict=True)
        self.available = available
        self.verification_modes: list[bool] = []

    def has_matching_input(
        self,
        scan_id: str,
        analysis_ids: tuple[str, ...],
        *,
        input_uri: str,
        input_manifest_sha256: str,
        verify_products: bool,
    ) -> bool:
        assert scan_id == "scan-retain"
        assert analysis_ids == ("standard-analysis",)
        assert input_uri.endswith("/scan-retain")
        assert input_manifest_sha256.startswith("sha256:")
        self.verification_modes.append(verify_products)
        return self.available


class _ScannerRuns:
    def __init__(self, root: Path, scanner_iq: _ScannerIq, *, complete: bool = True) -> None:
        self.root = root.resolve(strict=True)
        self._scanner_iq = scanner_iq
        self._complete = complete

    def run_ids(self) -> tuple[str, ...]:
        return ("scan-run-retain",)

    def inspect(self, run_id: str):
        assert run_id == "scan-run-retain"
        sweep = SimpleNamespace(
            scan_id=self._scanner_iq.scan_id,
            iq_bundle_uri=self._scanner_iq.uri,
            iq_manifest_sha256=self._scanner_iq.digest,
        )
        return SimpleNamespace(
            manifest=SimpleNamespace(
                status="complete" if self._complete else "failed",
                sweeps=(sweep,),
            )
        )


def _system(
    tmp_path: Path,
    *,
    analysis_available: bool = True,
    run_complete: bool = True,
    failure_injector=None,
):
    bulk = tmp_path / "bulk"
    recordings = RecordingStore(bulk)
    scanner_iq = _ScannerIq(bulk)
    scanner_analysis = _ScannerAnalysis(bulk, available=analysis_available)
    scanner_runs = _ScannerRuns(bulk, scanner_iq, complete=run_complete)
    executor = PurgeExecutor(bulk)
    tombstones = ScannerPurgeTombstoneStore(bulk)
    retention = CatalogRetentionService(
        _EmptyCatalog(),  # type: ignore[arg-type]
        recordings,
        HoldReceiptStore(bulk),
        executor,
        scanner_iq=scanner_iq,  # type: ignore[arg-type]
        scanner_analysis=scanner_analysis,  # type: ignore[arg-type]
        scanner_runs=scanner_runs,  # type: ignore[arg-type]
        scanner_tombstones=tombstones,
        scanner_analysis_ids=("standard-analysis",),
        failure_injector=failure_injector,
    )
    return scanner_iq, scanner_analysis, executor, tombstones, retention


def test_only_exactly_analyzed_scanner_iq_is_watermark_eligible(tmp_path: Path) -> None:
    scanner_iq, scanner_analysis, executor, tombstones, retention = _system(tmp_path)

    below = retention.run(StorageUsage(total_bytes=1_000, used_bytes=699), dry_run=True)
    assert below.decision.selected_session_ids == ()
    assert scanner_analysis.verification_modes == []

    result = retention.run(StorageUsage(total_bytes=1_000, used_bytes=700))
    assert result.committed == ("scanner:scan-retain",)
    assert result.failures == ()
    assert result.decision.selected_session_ids == ("scanner:scan-retain",)
    assert scanner_analysis.verification_modes == [False, True]
    assert not scanner_iq.path.exists()
    assert tombstones.get("scan-retain") is not None
    assert len(executor.pending()) == 1

    recovery = retention.recover()
    assert recovery.discarded == ("scanner:scan-retain",)
    assert recovery.restored == ()
    assert executor.pending() == ()


def test_unanalyzed_scanner_iq_is_never_selected(tmp_path: Path) -> None:
    scanner_iq, scanner_analysis, executor, tombstones, retention = _system(
        tmp_path,
        analysis_available=False,
    )

    result = retention.run(StorageUsage(total_bytes=1_000, used_bytes=700))

    assert result.decision.selected_session_ids == ()
    assert result.committed == ()
    assert scanner_analysis.verification_modes == [False]
    assert scanner_iq.path.is_dir()
    assert tombstones.get("scan-retain") is None
    assert executor.pending() == ()


def test_scanner_iq_without_a_complete_terminal_run_is_never_selected(
    tmp_path: Path,
) -> None:
    scanner_iq, scanner_analysis, executor, tombstones, retention = _system(
        tmp_path,
        run_complete=False,
    )

    result = retention.run(StorageUsage(total_bytes=1_000, used_bytes=700))

    assert result.decision.selected_session_ids == ()
    assert result.committed == ()
    assert scanner_analysis.verification_modes == []
    assert scanner_iq.path.is_dir()
    assert tombstones.get("scan-retain") is None
    assert executor.pending() == ()


class _InjectedCrash(BaseException):
    pass


@pytest.mark.parametrize(
    ("failure_point", "restored", "discarded"),
    (
        ("scanner:after_stage", ("scanner:scan-retain",), ()),
        ("scanner:after_commit", (), ("scanner:scan-retain",)),
    ),
)
def test_scanner_purge_recovery_uses_durable_tombstone_as_commit_point(
    tmp_path: Path,
    failure_point: str,
    restored: tuple[str, ...],
    discarded: tuple[str, ...],
) -> None:
    def crash(point: str) -> None:
        if point == failure_point:
            raise _InjectedCrash

    scanner_iq, _analysis, executor, tombstones, retention = _system(
        tmp_path,
        failure_injector=crash,
    )
    with pytest.raises(_InjectedCrash):
        retention.run(StorageUsage(total_bytes=1_000, used_bytes=700))
    assert len(executor.pending()) == 1

    recovered = CatalogRetentionService(
        _EmptyCatalog(),  # type: ignore[arg-type]
        RecordingStore(scanner_iq.root),
        HoldReceiptStore(scanner_iq.root),
        executor,
        scanner_iq=scanner_iq,  # type: ignore[arg-type]
        scanner_analysis=_ScannerAnalysis(scanner_iq.root),  # type: ignore[arg-type]
        scanner_runs=_ScannerRuns(scanner_iq.root, scanner_iq),  # type: ignore[arg-type]
        scanner_tombstones=tombstones,
        scanner_analysis_ids=("standard-analysis",),
    ).recover()

    assert recovered.restored == restored
    assert recovered.discarded == discarded
    assert scanner_iq.path.exists() is bool(restored)
    assert executor.pending() == ()
