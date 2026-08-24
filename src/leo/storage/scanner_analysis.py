"""Atomic local publication for Standard scanner analysis products."""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.analysis_models import (
    ScannerAnalysisBundleManifestLike,
    ScannerAnalysisBundleManifestV1,
    ScannerAnalysisBundleManifestV2,
    ScannerAnalysisBundleManifestV3,
    ScannerAnalysisBundleManifestV4,
    ScannerAnalysisHistoryItemV1,
    ScannerAnalysisHistoryItemV2,
    ScannerAnalysisHistoryItemV3,
    ScannerAnalysisHistoryPageV1,
    ScannerAnalysisHistoryPageV2,
    ScannerAnalysisHistoryPageV3,
    ScannerAnalysisMetricsLike,
    ScannerAnalysisMetricsV1,
    ScannerAnalysisMetricsV2,
    ScannerPilotDopplerSegmentsV1,
)
from leo.scanner.models import ScannerReport, ScannerReportLike, ScannerReportV2
from leo.storage.errors import BundleCorruptionError, BundleNotFoundError
from leo.storage.uri import BulkUriResolver, confined_path
from leo.storage.writer import _fsync_directory

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_JSON_BYTES = 64 * 1024 * 1024
_MAX_PNG_BYTES = 64 * 1024 * 1024


class ScannerCaptureTimeReader(Protocol):
    def captured_at(self, scan_id: str) -> datetime: ...


@dataclass(frozen=True, slots=True)
class PublishedScannerAnalysisBundle:
    analysis_id: str
    scan_id: str
    path: Path
    uri: str
    manifest: ScannerAnalysisBundleManifestLike
    manifest_sha256: str
    report: ScannerReportLike
    metrics: ScannerAnalysisMetricsLike
    pilot_doppler: ScannerPilotDopplerSegmentsV1 | None = None


class ScannerAnalysisStore:
    def __init__(
        self,
        root: Path,
        *,
        capture_times: ScannerCaptureTimeReader | None = None,
    ) -> None:
        if root == Path("/mnt/qnap01") or str(root).startswith("/mnt/qnap01/"):
            raise ValueError("scanner analysis cannot be written beneath QNAP")
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        self.spool_root = self.root / "spool"
        self.analysis_root = self.root / "scanner-analysis"
        self.spool_root.mkdir(exist_ok=True)
        self.analysis_root.mkdir(exist_ok=True)
        if os.stat(self.spool_root).st_dev != os.stat(self.analysis_root).st_dev:
            raise ValueError("scanner analysis spool and destination must share a filesystem")
        self.resolver = BulkUriResolver(self.root, allowed_namespaces=("scanner-analysis",))
        self._capture_times = capture_times

    def publish(
        self,
        analysis_id: str,
        report: ScannerReportLike,
        metrics: ScannerAnalysisMetricsLike,
        *,
        waterfall_png: bytes,
        glrt64_png: bytes,
        pilot_doppler: ScannerPilotDopplerSegmentsV1 | None = None,
        pilot_doppler_png: bytes | None = None,
        pilot_carrier_tracking_png: bytes | None = None,
        pilot_segment_rates_png: bytes | None = None,
    ) -> PublishedScannerAnalysisBundle:
        for label, value in (("analysis", analysis_id), ("scan", report.scan_id)):
            if not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} ID is not one safe persisted identifier")
        if report.scan_id != metrics.scan_id:
            raise ValueError("scanner report and metrics scan IDs disagree")
        v2 = isinstance(report, ScannerReportV2) or isinstance(metrics, ScannerAnalysisMetricsV2)
        if v2 and not (
            isinstance(report, ScannerReportV2) and isinstance(metrics, ScannerAnalysisMetricsV2)
        ):
            raise ValueError("scanner report and metrics continuity versions disagree")
        if (
            isinstance(report, ScannerReportV2)
            and isinstance(metrics, ScannerAnalysisMetricsV2)
            and (
                report.configuration != metrics.configuration
                or report.continuity_evidence != metrics.continuity_evidence
            )
        ):
            raise ValueError("scanner report and metrics continuity evidence disagree")
        if (pilot_doppler is None) != (pilot_doppler_png is None):
            raise ValueError("scanner pilot product and PNG must be published together")
        focused_pngs = (pilot_carrier_tracking_png, pilot_segment_rates_png)
        if any(item is not None for item in focused_pngs) and (
            pilot_doppler is None or any(item is None for item in focused_pngs)
        ):
            raise ValueError("scanner focused pilot PNGs require the complete pilot product pair")
        if pilot_doppler is not None and (
            pilot_doppler.scan_id != report.scan_id
            or pilot_doppler.input_uri != metrics.input_uri
            or pilot_doppler.input_manifest_sha256 != metrics.input_manifest_sha256
            or pilot_doppler.scanner_metrics_sha256
            != sha256_digest(canonical_json_bytes(metrics.model_dump(mode="json")))
        ):
            raise ValueError("scanner pilot product disagrees with its source evidence")
        pngs = [("waterfall", waterfall_png), ("GLRT64", glrt64_png)]
        if pilot_doppler_png is not None:
            pngs.append(("pilot Doppler", pilot_doppler_png))
        if pilot_carrier_tracking_png is not None:
            pngs.append(("pilot carrier tracking", pilot_carrier_tracking_png))
        if pilot_segment_rates_png is not None:
            pngs.append(("pilot segment rates", pilot_segment_rates_png))
        for label, payload in pngs:
            if not payload.startswith(b"\x89PNG\r\n\x1a\n") or len(payload) > _MAX_PNG_BYTES:
                raise ValueError(f"scanner {label} artifact is not one bounded PNG")
        destination_parent = self.analysis_root / report.scan_id
        destination_parent.mkdir(parents=True, exist_ok=True)
        destination_parent = confined_path(self.analysis_root, destination_parent, must_exist=True)
        if not destination_parent.is_dir() or destination_parent.is_symlink():
            raise ValueError("scanner analysis destination parent is not a real directory")
        destination = destination_parent / analysis_id
        if destination.exists():
            raise FileExistsError(f"scanner analysis already exists: {destination}")
        spool = self.spool_root / f"{report.scan_id}.{analysis_id}.{os.getpid()}.partial"
        spool.mkdir(exist_ok=False)
        spool.chmod(0o755)
        try:
            presentation = spool / "presentation"
            presentation.mkdir()
            presentation.chmod(0o755)
            report_payload = canonical_json_bytes(report.model_dump(mode="json"))
            metrics_payload = canonical_json_bytes(metrics.model_dump(mode="json"))
            report_name = "scanner-report.v2.json" if v2 else "scanner-report.v1.json"
            metrics_name = "scanner-metrics.v2.json" if v2 else "scanner-metrics.v1.json"
            (spool / report_name).write_bytes(report_payload)
            (spool / metrics_name).write_bytes(metrics_payload)
            (presentation / "scanner-waterfall.v1.png").write_bytes(waterfall_png)
            (presentation / "scanner-glrt64-response.v1.png").write_bytes(glrt64_png)
            if pilot_doppler is None:
                if v2:
                    raise ValueError("scanner V2 analysis requires pilot and focused PNG products")
                manifest: ScannerAnalysisBundleManifestLike = ScannerAnalysisBundleManifestV1(
                    analysis_id=analysis_id,
                    scan_id=report.scan_id,
                    input_uri=metrics.input_uri,
                    input_manifest_sha256=metrics.input_manifest_sha256,
                    report_sha256=sha256_digest(report_payload),
                    metrics_sha256=sha256_digest(metrics_payload),
                    waterfall_png_sha256=sha256_digest(waterfall_png),
                    glrt64_png_sha256=sha256_digest(glrt64_png),
                )
            else:
                assert pilot_doppler_png is not None
                pilot_payload = canonical_json_bytes(pilot_doppler.model_dump(mode="json"))
                (spool / "scanner-pilot-doppler-segments.v1.json").write_bytes(pilot_payload)
                (presentation / "scanner-pilot-doppler-segments.v1.png").write_bytes(
                    pilot_doppler_png
                )
                common = {
                    "analysis_id": analysis_id,
                    "scan_id": report.scan_id,
                    "input_uri": metrics.input_uri,
                    "input_manifest_sha256": metrics.input_manifest_sha256,
                    "report_sha256": sha256_digest(report_payload),
                    "metrics_sha256": sha256_digest(metrics_payload),
                    "pilot_doppler_sha256": sha256_digest(pilot_payload),
                    "waterfall_png_sha256": sha256_digest(waterfall_png),
                    "glrt64_png_sha256": sha256_digest(glrt64_png),
                    "pilot_doppler_png_sha256": sha256_digest(pilot_doppler_png),
                }
                if v2:
                    if pilot_carrier_tracking_png is None or pilot_segment_rates_png is None:
                        raise ValueError("scanner V2 analysis requires focused pilot PNGs")
                    (presentation / "scanner-pilot-carrier-tracking.v1.png").write_bytes(
                        pilot_carrier_tracking_png
                    )
                    (presentation / "scanner-pilot-segment-rates.v1.png").write_bytes(
                        pilot_segment_rates_png
                    )
                    manifest = ScannerAnalysisBundleManifestV4.model_validate(
                        {
                            **common,
                            "pilot_carrier_tracking_png_sha256": sha256_digest(
                                pilot_carrier_tracking_png
                            ),
                            "pilot_segment_rates_png_sha256": sha256_digest(
                                pilot_segment_rates_png
                            ),
                        }
                    )
                elif pilot_carrier_tracking_png is None:
                    manifest = ScannerAnalysisBundleManifestV2.model_validate(common)
                else:
                    assert pilot_segment_rates_png is not None
                    (presentation / "scanner-pilot-carrier-tracking.v1.png").write_bytes(
                        pilot_carrier_tracking_png
                    )
                    (presentation / "scanner-pilot-segment-rates.v1.png").write_bytes(
                        pilot_segment_rates_png
                    )
                    manifest = ScannerAnalysisBundleManifestV3.model_validate(
                        {
                            **common,
                            "pilot_carrier_tracking_png_sha256": sha256_digest(
                                pilot_carrier_tracking_png
                            ),
                            "pilot_segment_rates_png_sha256": sha256_digest(
                                pilot_segment_rates_png
                            ),
                        }
                    )
            manifest_payload = canonical_json_bytes(manifest.model_dump(mode="json"))
            (spool / "manifest.json").write_bytes(manifest_payload)
            for path in tuple(spool.rglob("*")):
                if path.is_file():
                    path.chmod(0o644)
                    with path.open("rb") as stream:
                        os.fsync(stream.fileno())
            _fsync_directory(presentation)
            _fsync_directory(spool)
            os.rename(spool, destination)
            _fsync_directory(destination_parent)
            return PublishedScannerAnalysisBundle(
                analysis_id=analysis_id,
                scan_id=report.scan_id,
                path=destination,
                uri=self.resolver.uri_for(destination),
                manifest=manifest,
                manifest_sha256=sha256_digest(manifest_payload),
                report=report,
                metrics=metrics,
                pilot_doppler=pilot_doppler,
            )
        except Exception:
            if spool.exists():
                for path in sorted(spool.rglob("*"), reverse=True):
                    path.unlink() if path.is_file() else path.rmdir()
                spool.rmdir()
            raise

    def inspect(self, scan_id: str, analysis_id: str) -> PublishedScannerAnalysisBundle:
        if not _IDENTIFIER.fullmatch(scan_id) or not _IDENTIFIER.fullmatch(analysis_id):
            raise ValueError("scanner analysis identity is invalid")
        candidate = self.analysis_root / scan_id / analysis_id
        if not candidate.exists():
            raise BundleNotFoundError("scanner analysis does not exist")
        path = confined_path(self.analysis_root, candidate, must_exist=True)
        manifest_payload, manifest = self._manifest(path, scan_id, analysis_id)
        report_payload = self._verified(path, manifest.report_relative_path, manifest.report_sha256)
        metrics_payload = self._verified(
            path, manifest.metrics_relative_path, manifest.metrics_sha256
        )
        self._verified(path, manifest.waterfall_png_relative_path, manifest.waterfall_png_sha256)
        self._verified(path, manifest.glrt64_png_relative_path, manifest.glrt64_png_sha256)
        pilot_doppler: ScannerPilotDopplerSegmentsV1 | None = None
        if isinstance(
            manifest,
            (
                ScannerAnalysisBundleManifestV2,
                ScannerAnalysisBundleManifestV3,
                ScannerAnalysisBundleManifestV4,
            ),
        ):
            pilot_payload = self._verified(
                path,
                manifest.pilot_doppler_relative_path,
                manifest.pilot_doppler_sha256,
            )
            self._verified(
                path,
                manifest.pilot_doppler_png_relative_path,
                manifest.pilot_doppler_png_sha256,
            )
        if isinstance(manifest, (ScannerAnalysisBundleManifestV3, ScannerAnalysisBundleManifestV4)):
            self._verified(
                path,
                manifest.pilot_carrier_tracking_png_relative_path,
                manifest.pilot_carrier_tracking_png_sha256,
            )
            self._verified(
                path,
                manifest.pilot_segment_rates_png_relative_path,
                manifest.pilot_segment_rates_png_sha256,
            )
        try:
            if isinstance(manifest, ScannerAnalysisBundleManifestV4):
                report: ScannerReportLike = ScannerReportV2.model_validate_json(report_payload)
                metrics: ScannerAnalysisMetricsLike = ScannerAnalysisMetricsV2.model_validate_json(
                    metrics_payload
                )
            else:
                report = ScannerReport.model_validate_json(report_payload)
                metrics = ScannerAnalysisMetricsV1.model_validate_json(metrics_payload)
            if isinstance(
                manifest,
                (
                    ScannerAnalysisBundleManifestV2,
                    ScannerAnalysisBundleManifestV3,
                    ScannerAnalysisBundleManifestV4,
                ),
            ):
                pilot_doppler = ScannerPilotDopplerSegmentsV1.model_validate_json(pilot_payload)
        except Exception as error:
            raise BundleCorruptionError(f"invalid scanner analysis product: {error}") from error
        if report.scan_id != scan_id or metrics.scan_id != scan_id:
            raise BundleCorruptionError("scanner analysis products disagree with scan ID")
        return PublishedScannerAnalysisBundle(
            analysis_id=analysis_id,
            scan_id=scan_id,
            path=path,
            uri=self.resolver.uri_for(path),
            manifest=manifest,
            manifest_sha256=sha256_digest(manifest_payload),
            report=report,
            metrics=metrics,
            pilot_doppler=pilot_doppler,
        )

    def page(self, *, cursor: int, limit: int) -> ScannerAnalysisHistoryPageV1:
        """Return one bounded page with the newest analysis variant per scan."""

        if cursor < 0 or not 1 <= limit <= 100:
            raise ValueError("scanner analysis page is outside its bounded range")
        bundles = [
            item
            for item in self._ordered_latest_bundles()
            if not isinstance(
                self._manifest(item[3], item[1], item[2])[1],
                ScannerAnalysisBundleManifestV4,
            )
        ]
        selected = bundles[cursor : cursor + limit]
        items: list[ScannerAnalysisHistoryItemV1] = []
        for modified_ns, scan_id, analysis_id, path in selected:
            _, manifest = self._manifest(path, scan_id, analysis_id)
            report_payload = self._verified(
                path, manifest.report_relative_path, manifest.report_sha256
            )
            try:
                report = ScannerReport.model_validate_json(report_payload)
            except Exception as error:
                raise BundleCorruptionError(f"invalid scanner analysis report: {error}") from error
            if report.scan_id != scan_id:
                raise BundleCorruptionError("scanner analysis report disagrees with scan ID")
            items.append(
                ScannerAnalysisHistoryItemV1(
                    published_at=datetime.fromtimestamp(modified_ns / 1_000_000_000, tz=UTC),
                    scan_id=scan_id,
                    analysis_id=analysis_id,
                    report=report,
                )
            )
        next_cursor = cursor + len(items) if cursor + len(items) < len(bundles) else None
        return ScannerAnalysisHistoryPageV1(
            cursor=cursor,
            limit=limit,
            total=len(bundles),
            next_cursor=next_cursor,
            items=tuple(items),
        )

    def page_v2(self, *, cursor: int, limit: int) -> ScannerAnalysisHistoryPageV2:
        """Return analyses ordered and labeled by immutable RF capture start."""

        if cursor < 0 or not 1 <= limit <= 100:
            raise ValueError("scanner analysis page is outside its bounded range")
        if self._capture_times is None:
            raise ValueError("scanner capture-time authority is unavailable")
        timed: list[tuple[datetime, int, str, str, Path]] = []
        for modified_ns, scan_id, analysis_id, path in self._ordered_latest_bundles():
            if isinstance(
                self._manifest(path, scan_id, analysis_id)[1],
                ScannerAnalysisBundleManifestV4,
            ):
                continue
            try:
                captured_at = self._capture_times.captured_at(scan_id)
            except BundleNotFoundError:
                # Historical analysis-only/replay products have no truthful RF
                # capture clock and therefore do not belong in the live scan table.
                continue
            timed.append((captured_at, modified_ns, scan_id, analysis_id, path))
        timed.sort(key=lambda item: (item[0], item[2], item[3]), reverse=True)
        selected = timed[cursor : cursor + limit]
        items: list[ScannerAnalysisHistoryItemV2] = []
        for captured_at, modified_ns, scan_id, analysis_id, path in selected:
            _, manifest = self._manifest(path, scan_id, analysis_id)
            report_payload = self._verified(
                path, manifest.report_relative_path, manifest.report_sha256
            )
            try:
                report = ScannerReport.model_validate_json(report_payload)
            except Exception as error:
                raise BundleCorruptionError(f"invalid scanner analysis report: {error}") from error
            if report.scan_id != scan_id:
                raise BundleCorruptionError("scanner analysis report disagrees with scan ID")
            items.append(
                ScannerAnalysisHistoryItemV2(
                    captured_at=captured_at,
                    published_at=datetime.fromtimestamp(modified_ns / 1_000_000_000, tz=UTC),
                    scan_id=scan_id,
                    analysis_id=analysis_id,
                    report=report,
                )
            )
        next_cursor = cursor + len(items) if cursor + len(items) < len(timed) else None
        return ScannerAnalysisHistoryPageV2(
            cursor=cursor,
            limit=limit,
            total=len(timed),
            next_cursor=next_cursor,
            items=tuple(items),
        )

    def page_v3(self, *, cursor: int, limit: int) -> ScannerAnalysisHistoryPageV3:
        """Return capture-time history supporting legacy and continuity reports."""

        if cursor < 0 or not 1 <= limit <= 100:
            raise ValueError("scanner analysis page is outside its bounded range")
        if self._capture_times is None:
            raise ValueError("scanner capture-time authority is unavailable")
        timed: list[tuple[datetime, int, str, str, Path]] = []
        for modified_ns, scan_id, analysis_id, path in self._ordered_latest_bundles():
            try:
                captured_at = self._capture_times.captured_at(scan_id)
            except BundleNotFoundError:
                continue
            timed.append((captured_at, modified_ns, scan_id, analysis_id, path))
        timed.sort(key=lambda item: (item[0], item[2], item[3]), reverse=True)
        selected = timed[cursor : cursor + limit]
        items: list[ScannerAnalysisHistoryItemV3] = []
        for captured_at, modified_ns, scan_id, analysis_id, path in selected:
            _, manifest = self._manifest(path, scan_id, analysis_id)
            report_payload = self._verified(
                path, manifest.report_relative_path, manifest.report_sha256
            )
            try:
                report: ScannerReportLike = (
                    ScannerReportV2.model_validate_json(report_payload)
                    if isinstance(manifest, ScannerAnalysisBundleManifestV4)
                    else ScannerReport.model_validate_json(report_payload)
                )
            except Exception as error:
                raise BundleCorruptionError(f"invalid scanner analysis report: {error}") from error
            if report.scan_id != scan_id:
                raise BundleCorruptionError("scanner analysis report disagrees with scan ID")
            items.append(
                ScannerAnalysisHistoryItemV3(
                    captured_at=captured_at,
                    published_at=datetime.fromtimestamp(modified_ns / 1_000_000_000, tz=UTC),
                    scan_id=scan_id,
                    analysis_id=analysis_id,
                    report=report,
                )
            )
        next_cursor = cursor + len(items) if cursor + len(items) < len(timed) else None
        return ScannerAnalysisHistoryPageV3(
            cursor=cursor,
            limit=limit,
            total=len(timed),
            next_cursor=next_cursor,
            items=tuple(items),
        )

    def artifact(
        self,
        scan_id: str,
        analysis_id: str,
        artifact: Literal[
            "waterfall",
            "glrt64",
            "pilot-doppler",
            "pilot-carrier-tracking",
            "pilot-segment-rates",
        ],
    ) -> bytes | None:
        """Read one digest-verified, already-published scanner PNG."""

        if not _IDENTIFIER.fullmatch(scan_id) or not _IDENTIFIER.fullmatch(analysis_id):
            raise ValueError("scanner analysis identity is invalid")
        candidate = self.analysis_root / scan_id / analysis_id
        if not candidate.exists():
            return None
        path = confined_path(self.analysis_root, candidate, must_exist=True)
        _, manifest = self._manifest(path, scan_id, analysis_id)
        relative: str
        digest: str
        if artifact == "waterfall":
            relative, digest = (
                manifest.waterfall_png_relative_path,
                manifest.waterfall_png_sha256,
            )
        elif artifact == "glrt64":
            relative, digest = (
                manifest.glrt64_png_relative_path,
                manifest.glrt64_png_sha256,
            )
        elif artifact == "pilot-carrier-tracking" and isinstance(
            manifest, (ScannerAnalysisBundleManifestV3, ScannerAnalysisBundleManifestV4)
        ):
            relative, digest = (
                manifest.pilot_carrier_tracking_png_relative_path,
                manifest.pilot_carrier_tracking_png_sha256,
            )
        elif artifact == "pilot-segment-rates" and isinstance(
            manifest, (ScannerAnalysisBundleManifestV3, ScannerAnalysisBundleManifestV4)
        ):
            relative, digest = (
                manifest.pilot_segment_rates_png_relative_path,
                manifest.pilot_segment_rates_png_sha256,
            )
        elif artifact == "pilot-doppler" and isinstance(
            manifest,
            (
                ScannerAnalysisBundleManifestV2,
                ScannerAnalysisBundleManifestV3,
                ScannerAnalysisBundleManifestV4,
            ),
        ):
            relative, digest = (
                manifest.pilot_doppler_png_relative_path,
                manifest.pilot_doppler_png_sha256,
            )
        else:
            return None
        payload = self._verified(path, relative, digest)
        if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
            raise BundleCorruptionError("scanner analysis artifact is not a PNG")
        return payload

    def _ordered_latest_bundles(self) -> list[tuple[int, str, str, Path]]:
        latest: list[tuple[int, str, str, Path]] = []
        for scan_path in self.analysis_root.iterdir():
            if not _IDENTIFIER.fullmatch(scan_path.name) or not self._real_directory(scan_path):
                continue
            analyses = [
                (path.stat(follow_symlinks=False).st_mtime_ns, path.name, path)
                for path in scan_path.iterdir()
                if _IDENTIFIER.fullmatch(path.name) and self._real_directory(path)
            ]
            if analyses:
                modified_ns, analysis_id, path = max(analyses)
                latest.append((modified_ns, scan_path.name, analysis_id, path))
        return sorted(latest, reverse=True)

    def _manifest(
        self, path: Path, scan_id: str, analysis_id: str
    ) -> tuple[bytes, ScannerAnalysisBundleManifestLike]:
        manifest_payload = self._read(path / "manifest.json", _MAX_JSON_BYTES)
        manifest: ScannerAnalysisBundleManifestLike
        try:
            schema_version = json.loads(manifest_payload)["schema_version"]
            if schema_version == 1:
                manifest = ScannerAnalysisBundleManifestV1.model_validate_json(manifest_payload)
            elif schema_version == 2:
                manifest = ScannerAnalysisBundleManifestV2.model_validate_json(manifest_payload)
            elif schema_version == 3:
                manifest = ScannerAnalysisBundleManifestV3.model_validate_json(manifest_payload)
            elif schema_version == 4:
                manifest = ScannerAnalysisBundleManifestV4.model_validate_json(manifest_payload)
            else:
                raise ValueError("unsupported scanner analysis manifest schema")
        except Exception as error:
            raise BundleCorruptionError(f"invalid scanner analysis manifest: {error}") from error
        if manifest.scan_id != scan_id or manifest.analysis_id != analysis_id:
            raise BundleCorruptionError("scanner analysis identity disagrees with path")
        return manifest_payload, manifest

    @staticmethod
    def _real_directory(path: Path) -> bool:
        metadata = path.stat(follow_symlinks=False)
        return stat.S_ISDIR(metadata.st_mode) and not path.is_symlink()

    def _verified(self, root: Path, relative: str, digest: str) -> bytes:
        path = confined_path(root, root / relative, must_exist=True)
        payload = self._read(path, _MAX_PNG_BYTES if relative.endswith(".png") else _MAX_JSON_BYTES)
        if sha256_digest(payload) != digest:
            raise BundleCorruptionError(f"scanner analysis product digest mismatch: {relative}")
        return payload

    @staticmethod
    def _read(path: Path, maximum_bytes: int) -> bytes:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_size <= 0
                or metadata.st_size > maximum_bytes
            ):
                raise BundleCorruptionError("scanner analysis member is not bounded regular data")
            chunks: list[bytes] = []
            remaining = metadata.st_size + 1
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            if len(payload) != metadata.st_size:
                raise BundleCorruptionError("scanner analysis member size changed")
            after = os.fstat(descriptor)
            if (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
                metadata.st_mtime_ns,
            ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise BundleCorruptionError("scanner analysis member changed while reading")
            return payload
        finally:
            os.close(descriptor)
