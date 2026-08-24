"""Composition boundary for the development Starlink scanner."""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from pathlib import Path

from leo.presentation.scanner_analysis import (
    render_scanner_glrt64_response_png,
    render_scanner_pilot_carrier_tracking_png,
    render_scanner_pilot_doppler_png,
    render_scanner_pilot_segment_rates_png,
    render_scanner_waterfall_png,
)
from leo.radio import PlutoSequentialScanRadio
from leo.scanner import (
    ScannerBurstReportV1,
    ScannerBurstReportV2,
    ScannerBurstReportV3,
    ScannerCaptureBurstReportLike,
    ScannerCaptureReportLike,
    ScannerConfigurationV2,
    ScannerReportLike,
    ScannerReportV2,
    ScannerReportV3,
    SequentialScanRadioLike,
    analyze_scan_sweep,
    analyze_standard_scanner,
    capture_scan_sweep,
    current_low_band_targets,
)
from leo.scanner.detector import STANDARD_SCANNER_RETAINED_CANDIDATE_COUNT
from leo.storage import (
    PublishedScannerIqBundle,
    ScannerAnalysisStore,
    ScannerIqStore,
    live_scanner_analysis_source,
)
from leo.storage.errors import BundleNotFoundError

logger = logging.getLogger(__name__)

STANDARD_SCANNER_ANALYSIS_ID = "standard-scan-analysis-pilot-plots-v1"
CONTINUITY_STANDARD_SCANNER_ANALYSIS_ID = "standard-scan-analysis-continuity-v2"
LEGACY_STANDARD_SCANNER_ANALYSIS_IDS = (
    "standard-scan-analysis-pilot-v1",
    "standard-scan-analysis-stitched-v2",
)
SCANNER_BURST_SIZE = 4


@dataclass(frozen=True, slots=True)
class ScannerAnalysisReconciliation:
    discovered: int
    already_analyzed: int
    analyzed: tuple[str, ...]
    failed: tuple[str, ...]


def run_scanner_command(
    *,
    host: str,
    serial: str,
    radio_id: str,
    gain_db: float,
    margin_gate: float,
    dwell_ms: int,
    output_path: Path | None,
    radio: SequentialScanRadioLike | None = None,
    capture_lease: AbstractContextManager[object] | None = None,
    iq_store: ScannerIqStore | None = None,
    analysis_store: ScannerAnalysisStore | None = None,
) -> ScannerCaptureBurstReportLike:
    if iq_store is not None and analysis_store is not None:
        reconcile_published_standard_scanner_analyses(iq_store, analysis_store)
    configuration = ScannerConfigurationV2(
        gain_db=gain_db,
        glrt64_margin_gate=margin_gate,
        dwell_ms=dwell_ms,
        maximum_acquisition_candidates=STANDARD_SCANNER_RETAINED_CANDIDATE_COUNT,
        targets=current_low_band_targets(),
    )
    scanner_radio = radio or PlutoSequentialScanRadio(
        host,
        expected_serial=serial,
        radio_id=radio_id,
    )
    burst_id = f"scan-burst-{uuid.uuid4().hex[:16]}"
    scan_ids = tuple(f"{burst_id}-{index + 1:02d}" for index in range(SCANNER_BURST_SIZE))
    with capture_lease or nullcontext():
        captured_sweeps = tuple(
            capture_scan_sweep(scanner_radio, configuration) for _ in range(SCANNER_BURST_SIZE)
        )
    reports: list[ScannerReportV2 | ScannerReportV3] = []
    for scan_id, captured in zip(scan_ids, captured_sweeps, strict=True):
        published = iq_store.publish(scan_id, captured) if iq_store is not None else None
        report = (
            run_published_standard_scanner_analysis(
                iq_store,
                analysis_store,
                published,
                capture_elapsed_ms=captured.capture_elapsed_ms,
            )
            if (
                iq_store is not None
                and analysis_store is not None
                and published is not None
                and captured.close_failure is None
            )
            else analyze_scan_sweep(captured, scan_id=scan_id)
        )
        if not isinstance(report, (ScannerReportV2, ScannerReportV3)):
            raise TypeError("scanner V2 capture produced a legacy report")
        reports.append(report)
    burst: ScannerCaptureBurstReportLike
    if any(isinstance(report, ScannerReportV3) for report in reports):
        burst = ScannerBurstReportV3(burst_id=burst_id, reports=tuple(reports))
    else:
        burst = ScannerBurstReportV2.model_validate(
            {"burst_id": burst_id, "reports": tuple(reports)}
        )
    if output_path is not None:
        write_scanner_burst_report(output_path, burst)
    return burst


def run_published_standard_scanner_analysis(
    iq_store: ScannerIqStore,
    analysis_store: ScannerAnalysisStore,
    bundle: PublishedScannerIqBundle,
    *,
    capture_elapsed_ms: float,
) -> ScannerReportLike:
    """Analyze one immutable scanner bundle and publish its Standard products."""

    analysis_id = (
        CONTINUITY_STANDARD_SCANNER_ANALYSIS_ID
        if _is_continuity_bundle(bundle)
        else STANDARD_SCANNER_ANALYSIS_ID
    )
    try:
        existing = analysis_store.inspect(bundle.scan_id, analysis_id)
    except BundleNotFoundError:
        pass
    else:
        if (
            existing.metrics.input_uri != bundle.uri
            or existing.metrics.input_manifest_sha256 != bundle.manifest_sha256
        ):
            raise ValueError("existing Standard scanner analysis has different input evidence")
        return existing.report

    source = live_scanner_analysis_source(
        iq_store,
        bundle,
        capture_elapsed_ms=capture_elapsed_ms,
    )
    result = analyze_standard_scanner(source)
    analysis_store.publish(
        analysis_id,
        result.report,
        result.metrics,
        waterfall_png=render_scanner_waterfall_png(result.metrics),
        glrt64_png=render_scanner_glrt64_response_png(
            result.metrics,
            result.pilot_doppler,
        ),
        pilot_doppler=result.pilot_doppler,
        pilot_doppler_png=render_scanner_pilot_doppler_png(
            result.metrics,
            result.pilot_doppler,
        ),
        pilot_carrier_tracking_png=render_scanner_pilot_carrier_tracking_png(
            result.metrics,
            result.pilot_doppler,
        ),
        pilot_segment_rates_png=render_scanner_pilot_segment_rates_png(
            result.metrics,
            result.pilot_doppler,
        ),
    )
    return result.report


def reconcile_published_standard_scanner_analyses(
    iq_store: ScannerIqStore,
    analysis_store: ScannerAnalysisStore,
) -> ScannerAnalysisReconciliation:
    """Repair missing Standard products for durable live scanner recordings."""

    recording_ids = iq_store.recording_ids()
    already_analyzed = 0
    analyzed: list[str] = []
    failed: list[str] = []
    for scan_id in recording_ids:
        bundle = None
        try:
            bundle = iq_store.inspect(scan_id)
        except Exception:
            failed.append(scan_id)
            logger.exception("scanner_analysis_reconciliation_failed scan_id=%s", scan_id)
            continue
        analysis_id = (
            CONTINUITY_STANDARD_SCANNER_ANALYSIS_ID
            if _is_continuity_bundle(bundle)
            else STANDARD_SCANNER_ANALYSIS_ID
        )
        try:
            analysis_store.inspect(scan_id, analysis_id)
        except BundleNotFoundError:
            legacy = None
            for analysis_id in LEGACY_STANDARD_SCANNER_ANALYSIS_IDS:
                try:
                    legacy = analysis_store.inspect(scan_id, analysis_id)
                except BundleNotFoundError:
                    continue
                else:
                    break
            if legacy is not None:
                try:
                    if (
                        legacy.metrics.input_uri != bundle.uri
                        or legacy.metrics.input_manifest_sha256 != bundle.manifest_sha256
                    ):
                        raise ValueError(
                            "legacy Standard scanner analysis has different input evidence"
                        )
                except Exception:
                    failed.append(scan_id)
                    logger.exception(
                        "scanner_analysis_reconciliation_failed scan_id=%s",
                        scan_id,
                    )
                else:
                    already_analyzed += 1
                continue
            try:
                run_published_standard_scanner_analysis(
                    iq_store,
                    analysis_store,
                    bundle,
                    capture_elapsed_ms=_persisted_capture_elapsed_ms(bundle),
                )
            except Exception:
                failed.append(scan_id)
                logger.exception("scanner_analysis_reconciliation_failed scan_id=%s", scan_id)
            else:
                analyzed.append(scan_id)
        except Exception:
            failed.append(scan_id)
            logger.exception("scanner_analysis_reconciliation_failed scan_id=%s", scan_id)
        else:
            already_analyzed += 1
    return ScannerAnalysisReconciliation(
        discovered=len(recording_ids),
        already_analyzed=already_analyzed,
        analyzed=tuple(analyzed),
        failed=tuple(failed),
    )


def _persisted_capture_elapsed_ms(bundle: PublishedScannerIqBundle) -> float:
    frames = bundle.manifest.frames
    lower = min(frame.host_request_monotonic_ns_lower for frame in frames)
    upper = max(frame.host_request_monotonic_ns_upper for frame in frames)
    return max(0.0, (upper - lower) / 1_000_000)


def _is_continuity_bundle(bundle: PublishedScannerIqBundle) -> bool:
    return isinstance(getattr(bundle.manifest, "configuration", None), ScannerConfigurationV2)


def write_scanner_report(path: Path, report: ScannerCaptureReportLike) -> None:
    _write_scanner_json(path, report.model_dump_json(indent=2))


def write_scanner_burst_report(
    path: Path,
    report: ScannerBurstReportV1 | ScannerBurstReportV2 | ScannerBurstReportV3,
) -> None:
    _write_scanner_json(path, report.model_dump_json(indent=2))


def _write_scanner_json(path: Path, payload: str) -> None:
    destination = path.resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write((payload + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        directory = os.open(destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()
