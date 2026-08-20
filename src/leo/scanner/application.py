"""Capture-first scanner orchestration."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

import numpy as np

from leo.scanner.detector import detect_first_glrt64
from leo.scanner.models import (
    ScanDecision,
    ScanEdgeResult,
    ScannerConfiguration,
    ScannerReport,
    ScanTarget,
)
from leo.scanner.ports import ScanRadioBlock, SequentialScanRadio


@dataclass(frozen=True, slots=True)
class _CapturedTarget:
    target: ScanTarget
    block: ScanRadioBlock | None
    error: str | None


def run_scan(
    radio: SequentialScanRadio,
    configuration: ScannerConfiguration,
    *,
    scan_id: str | None = None,
) -> ScannerReport:
    """Capture every tuning before spending any time on detection."""

    captured: list[_CapturedTarget] = []
    identity = radio.identity
    capture_started = time.perf_counter()
    try:
        identity = radio.open()
        radio.configure_once(configuration)
        for target in configuration.targets:
            try:
                block = radio.tune_and_read(target.if_center_hz, configuration.dwell_samples)
                captured.append(_CapturedTarget(target, block, None))
            except Exception as error:
                captured.append(_CapturedTarget(target, None, f"{type(error).__name__}: {error}"))
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"
        completed = {item.target for item in captured}
        captured.extend(
            _CapturedTarget(target, None, reason)
            for target in configuration.targets
            if target not in completed
        )
    finally:
        radio.close()
    capture_elapsed_ms = (time.perf_counter() - capture_started) * 1_000

    analysis_started = time.perf_counter()
    results = []
    for item in captured:
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
                configuration,
                edge=item.target.edge,
            )
            decision = (
                ScanDecision.ACTIVE
                if detection.first is not None
                else ScanDecision.NO_DETECTION
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
    return ScannerReport(
        scan_id=scan_id or f"scan-{uuid.uuid4().hex[:16]}",
        radio_id=identity.radio_id,
        radio_serial=identity.serial,
        configuration=configuration,
        capture_elapsed_ms=capture_elapsed_ms,
        analysis_elapsed_ms=analysis_elapsed_ms,
        results=tuple(results),
    )
