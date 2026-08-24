"""Capture-first scanner orchestration."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from typing import cast

import numpy as np

from leo.scanner.detector import detect_first_glrt64
from leo.scanner.models import (
    ScanDecision,
    ScanEdgeResult,
    ScannerCaptureReportLike,
    ScannerCloseFailureEvidenceV1,
    ScannerConfigurationLike,
    ScannerConfigurationV2,
    ScannerFrameContinuityEvidenceV1,
    ScannerReport,
    ScannerReportV2,
    ScannerReportV3,
    ScanTarget,
)
from leo.scanner.ports import (
    ScanRadioBlockLike,
    ScanRadioBlockV2,
    ScanRadioIdentity,
    SequentialScanRadio,
    SequentialScanRadioLike,
    SequentialScanRadioV2,
)


@dataclass(frozen=True, slots=True)
class CapturedScanTarget:
    target: ScanTarget
    block: ScanRadioBlockLike | None
    error: str | None


@dataclass(frozen=True, slots=True)
class CapturedScannerSweep:
    identity: ScanRadioIdentity
    configuration: ScannerConfigurationLike
    capture_elapsed_ms: float
    targets: tuple[CapturedScanTarget, ...]
    close_failure: ScannerCloseFailureEvidenceV1 | None = None

    def __post_init__(self) -> None:
        if tuple(item.target for item in self.targets) != self.configuration.targets:
            raise ValueError("captured scanner sweep does not cover its target plan")
        blocks = tuple(item.block for item in self.targets if item.block is not None)
        if isinstance(self.configuration, ScannerConfigurationV2):
            if any(not isinstance(block, ScanRadioBlockV2) for block in blocks):
                raise ValueError("scanner V2 sweep contains unattested target IQ")
            v2_blocks = cast(tuple[ScanRadioBlockV2, ...], blocks)
            generations = tuple(block.stream_generation for block in v2_blocks)
            if len(generations) != len(set(generations)):
                raise ValueError("scanner sweep reuses a stream generation across reset episodes")
            episodes = tuple(block.reset_episode for block in v2_blocks)
            if episodes != tuple(sorted(set(episodes))):
                raise ValueError("scanner sweep reset episodes must be unique and ordered")
        elif any(isinstance(block, ScanRadioBlockV2) for block in blocks):
            raise ValueError("scanner V1 sweep cannot contain V2 continuity evidence")


def run_scan(
    radio: SequentialScanRadioLike,
    configuration: ScannerConfigurationLike,
    *,
    scan_id: str | None = None,
) -> ScannerCaptureReportLike:
    """Capture every tuning before spending any time on detection."""

    return analyze_scan_sweep(
        capture_scan_sweep(radio, configuration),
        scan_id=scan_id,
    )


def capture_scan_sweep(
    radio: SequentialScanRadioLike,
    configuration: ScannerConfigurationLike,
) -> CapturedScannerSweep:
    """Capture and close every tuning without performing detector work."""

    captured: list[CapturedScanTarget] = []
    close_failure: ScannerCloseFailureEvidenceV1 | None = None
    identity = radio.identity
    capture_started = time.perf_counter()
    try:
        identity = radio.open()
        if isinstance(configuration, ScannerConfigurationV2):
            cast(SequentialScanRadioV2, radio).configure_once(configuration)
        else:
            cast(SequentialScanRadio, radio).configure_once(configuration)
        for target in configuration.targets:
            try:
                block = radio.tune_and_read(target.if_center_hz, configuration.dwell_samples)
                captured.append(CapturedScanTarget(target, block, None))
            except Exception as error:
                captured.append(
                    CapturedScanTarget(target, None, f"{type(error).__name__}: {error}")
                )
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"
        completed = {item.target for item in captured}
        captured.extend(
            CapturedScanTarget(target, None, reason)
            for target in configuration.targets
            if target not in completed
        )
    finally:
        try:
            radio.close()
        except Exception as error:
            close_failure = ScannerCloseFailureEvidenceV1(
                exception_type=type(error).__name__,
                message=(str(error) or "radio close failed without an exception message")[:2048],
            )
    capture_elapsed_ms = (time.perf_counter() - capture_started) * 1_000
    return CapturedScannerSweep(
        identity=identity,
        configuration=configuration,
        capture_elapsed_ms=capture_elapsed_ms,
        targets=tuple(captured),
        close_failure=close_failure,
    )


def analyze_scan_sweep(
    captured: CapturedScannerSweep,
    *,
    scan_id: str | None = None,
) -> ScannerCaptureReportLike:
    """Analyze an already-closed sweep without owning a radio lease."""

    analysis_started = time.perf_counter()
    results = []
    for item in captured.targets:
        if item.block is None:
            results.append(
                ScanEdgeResult(
                    target=item.target,
                    decision=ScanDecision.INCONCLUSIVE,
                    requested_if_center_hz=item.target.if_center_hz,
                    actual_if_center_hz=None,
                    tune_ms=None,
                    listen_ms=None,
                    iq_sha256=None,
                    reason=item.error or "capture failed",
                )
            )
            continue
        samples = np.ascontiguousarray(item.block.samples)
        digest = hashlib.sha256(samples.view(np.uint8)).hexdigest()
        try:
            detection = detect_first_glrt64(
                samples,
                captured.configuration,
                edge=item.target.edge,
            )
            decision = (
                ScanDecision.ACTIVE if detection.first is not None else ScanDecision.NO_DETECTION
            )
            results.append(
                ScanEdgeResult(
                    target=item.target,
                    decision=decision,
                    requested_if_center_hz=item.block.requested_if_center_hz,
                    actual_if_center_hz=item.block.actual_if_center_hz,
                    tune_ms=item.block.tune_ms,
                    listen_ms=item.block.listen_ms,
                    iq_sha256=digest,
                    first_detection=detection.first,
                    best_margin=detection.best_margin,
                    reason=detection.reason,
                )
            )
        except Exception as error:
            results.append(
                ScanEdgeResult(
                    target=item.target,
                    decision=ScanDecision.INCONCLUSIVE,
                    requested_if_center_hz=item.block.requested_if_center_hz,
                    actual_if_center_hz=item.block.actual_if_center_hz,
                    tune_ms=item.block.tune_ms,
                    listen_ms=item.block.listen_ms,
                    iq_sha256=digest,
                    reason=f"{type(error).__name__}: {error}",
                )
            )
    analysis_elapsed_ms = (time.perf_counter() - analysis_started) * 1_000
    report_id = scan_id or f"scan-{uuid.uuid4().hex[:16]}"
    if isinstance(captured.configuration, ScannerConfigurationV2):
        continuity_evidence = _continuity_evidence(captured)
        continuity_observable = any(item.status == "attested" for item in continuity_evidence)
        if captured.close_failure is not None or not continuity_observable:
            return ScannerReportV3(
                scan_id=report_id,
                radio_id=captured.identity.radio_id,
                radio_serial=captured.identity.serial,
                configuration=captured.configuration,
                capture_elapsed_ms=captured.capture_elapsed_ms,
                analysis_elapsed_ms=analysis_elapsed_ms,
                results=tuple(results),
                continuity_evidence=continuity_evidence,
                continuity_observable=continuity_observable,
                close_failure=captured.close_failure,
            )
        return ScannerReportV2(
            scan_id=report_id,
            radio_id=captured.identity.radio_id,
            radio_serial=captured.identity.serial,
            configuration=captured.configuration,
            capture_elapsed_ms=captured.capture_elapsed_ms,
            analysis_elapsed_ms=analysis_elapsed_ms,
            results=tuple(results),
            continuity_evidence=continuity_evidence,
        )
    return ScannerReport(
        scan_id=report_id,
        radio_id=captured.identity.radio_id,
        radio_serial=captured.identity.serial,
        configuration=captured.configuration,
        capture_elapsed_ms=captured.capture_elapsed_ms,
        analysis_elapsed_ms=analysis_elapsed_ms,
        results=tuple(results),
    )


def _continuity_evidence(
    captured: CapturedScannerSweep,
) -> tuple[ScannerFrameContinuityEvidenceV1, ...]:
    evidence: list[ScannerFrameContinuityEvidenceV1] = []
    for target_index, item in enumerate(captured.targets):
        block = item.block
        if block is None:
            evidence.append(
                ScannerFrameContinuityEvidenceV1(
                    status="capture_failed",
                    target_index=target_index,
                    continuity_observable=False,
                    within_frame_continuity="unavailable_capture_failed",
                    reason=item.error or "capture failed",
                )
            )
            continue
        if not isinstance(block, ScanRadioBlockV2):
            raise ValueError("scanner V2 report requires metadata-attested target frames")
        evidence.append(
            ScannerFrameContinuityEvidenceV1(
                status="attested",
                target_index=target_index,
                metadata_abi_version=block.metadata_abi_version,
                stream_id=block.stream_id,
                stream_generation=block.stream_generation,
                buffer_sequence=block.buffer_sequence,
                source_sequence=block.source_sequence,
                first_sample_sequence=block.first_sample_sequence,
                last_sample_sequence_exclusive=block.last_sample_sequence_exclusive,
                device_sample_counter=block.device_sample_counter,
                device_sample_counter_end_exclusive=(block.device_sample_counter_end_exclusive),
                metadata_flags=block.metadata_flags,
                sample_time_realtime_start_ns=block.sample_time_realtime_ns[0],
                sample_time_realtime_end_ns=block.sample_time_realtime_ns[1],
                sample_time_monotonic_start_ns=block.sample_time_monotonic_ns[0],
                sample_time_monotonic_end_ns=block.sample_time_monotonic_ns[1],
                sample_time_uncertainty_ns=block.sample_time_uncertainty_ns,
                kernel_buffers_requested=block.kernel_buffers_requested,
                kernel_buffers_readback=block.kernel_buffers_readback,
                reset_episode=block.reset_episode,
                missing_samples_before=block.missing_samples_before,
                overflow_observed=block.overflow_observed,
                continuity_observable=True,
                within_frame_continuity="proven_within_returned_buffer",
                reason="FPGA metadata proves continuity inside this reset-bounded frame",
            )
        )
    return tuple(evidence)
