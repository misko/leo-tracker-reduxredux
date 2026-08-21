"""Segment-aware Standard scanner numerical analysis."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from leo.analysis.standard.observability import numerical_waterfall_document
from leo.analysis.waterfall import WaterfallConfig, bounded_waterfall
from leo.contracts.digests import sha256_digest
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.contracts.standard_pipeline import StandardNumericalWaterfallV2
from leo.domain.iq import IqBlock
from leo.scanner.analysis_models import (
    ScannerAnalysisMetricsV1,
    ScannerFrameAnalysisV1,
    ScannerGlrt64CandidateMetricsV1,
    ScannerGlrt64ProbeMetricsV1,
)
from leo.scanner.detector import analyze_glrt64_dwell
from leo.scanner.models import (
    ScanDecision,
    ScanEdgeResult,
    ScannerConfiguration,
    ScannerReport,
    ScanTarget,
)
from leo.scanner.ports import ScanRadioIdentity


@dataclass(frozen=True, slots=True)
class ScannerAnalysisFrameInput:
    target_index: int
    target: ScanTarget
    source_sample_start: int
    requested_if_center_hz: int
    actual_if_center_hz: int | None
    tune_ms: float | None
    listen_ms: float | None
    samples: npt.NDArray[np.int16] | None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.samples is None:
            if not self.error:
                raise ValueError("failed scanner frame requires an error")
            return
        values = np.asarray(self.samples)
        if values.dtype != np.dtype("<i2") or values.ndim != 3 or values.shape[2] != 2:
            raise ValueError("scanner analysis frame must be sample/receiver/IQ CI16")
        if not values.flags.c_contiguous:
            raise ValueError("scanner analysis frame must be contiguous")
        if self.actual_if_center_hz is None or self.error is not None:
            raise ValueError("complete scanner frame settings are inconsistent")
        values.setflags(write=False)
        object.__setattr__(self, "samples", values)


@dataclass(frozen=True, slots=True)
class SegmentedScannerSource:
    scan_id: str
    input_uri: str
    input_manifest_sha256: str
    identity: ScanRadioIdentity
    configuration: ScannerConfiguration
    frames: tuple[ScannerAnalysisFrameInput, ...]

    def __post_init__(self) -> None:
        if tuple(item.target_index for item in self.frames) != tuple(
            range(len(self.configuration.targets))
        ):
            raise ValueError("segmented scanner source must cover the ordered scan plan")
        if tuple(item.target for item in self.frames) != self.configuration.targets:
            raise ValueError("segmented scanner source targets disagree with configuration")
        expected = (self.configuration.dwell_samples, len(self.configuration.receiver_ids), 2)
        for frame in self.frames:
            if frame.samples is not None and frame.samples.shape != expected:
                raise ValueError(
                    f"scanner analysis frame has shape {frame.samples.shape}, expected {expected}"
                )


@dataclass(frozen=True, slots=True)
class StandardScannerAnalysisConfig:
    waterfall: WaterfallConfig = WaterfallConfig(maximum_time_bins=80)


@dataclass(frozen=True, slots=True)
class StandardScannerAnalysisResult:
    metrics: ScannerAnalysisMetricsV1
    report: ScannerReport


class _FrameReceiverReader:
    def __init__(
        self,
        frame: ScannerAnalysisFrameInput,
        configuration: ScannerConfiguration,
        receiver_id: int,
        radio_id: str,
    ) -> None:
        assert frame.samples is not None
        self._frame = frame
        self._configuration = configuration
        self._receiver_id = receiver_id
        self._receiver_index = configuration.receiver_ids.index(receiver_id)
        self._radio_id = radio_id

    @property
    def sample_rate_hz(self) -> int:
        return self._configuration.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        assert self._frame.actual_if_center_hz is not None
        return self._frame.actual_if_center_hz

    @property
    def sample_count(self) -> int:
        assert self._frame.samples is not None
        return len(self._frame.samples)

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return (self._receiver_id,)

    def iter_blocks(self, *, block_samples: int):
        assert self._frame.samples is not None
        for start in range(0, len(self._frame.samples), block_samples):
            selected = np.ascontiguousarray(
                self._frame.samples[
                    start : start + block_samples,
                    self._receiver_index : self._receiver_index + 1,
                    :,
                ]
            )
            yield IqBlock(
                samples=selected,
                metadata=IqBlockMetadataV1(
                    radio_id=self._radio_id,
                    receiver_ids=(self._receiver_id,),
                    sample_count=len(selected),
                    session_sample_start=start,
                    host_request_utc_ns=NanosecondIntervalV1(lower_ns=0, upper_ns=0),
                    host_request_monotonic_ns=NanosecondIntervalV1(lower_ns=0, upper_ns=0),
                ),
            )


def analyze_standard_scanner(
    source: SegmentedScannerSource,
    *,
    config: StandardScannerAnalysisConfig | None = None,
) -> StandardScannerAnalysisResult:
    """Analyze every retuned frame independently and aggregate one scan result."""

    resolved = config or StandardScannerAnalysisConfig()
    analysis_started = time.perf_counter()
    metrics_frames: list[ScannerFrameAnalysisV1] = []
    report_results: list[ScanEdgeResult] = []
    for frame in source.frames:
        if frame.samples is None:
            reason = frame.error or "capture failed"
            metrics_frames.append(
                ScannerFrameAnalysisV1(
                    status="failed",
                    target_index=frame.target_index,
                    target=frame.target,
                    source_sample_start=frame.source_sample_start,
                    sample_count=0,
                    requested_if_center_hz=frame.requested_if_center_hz,
                    actual_if_center_hz=None,
                    iq_sha256=None,
                    decision=ScanDecision.INCONCLUSIVE,
                    decision_best_margin=None,
                    full_best_margin=None,
                    first_detection=None,
                    reason=reason,
                    probes=(),
                    waterfalls=(),
                )
            )
            report_results.append(
                ScanEdgeResult(
                    target=frame.target,
                    decision=ScanDecision.INCONCLUSIVE,
                    requested_if_center_hz=frame.requested_if_center_hz,
                    actual_if_center_hz=None,
                    tune_ms=None,
                    listen_ms=None,
                    iq_sha256=None,
                    reason=reason,
                )
            )
            continue
        complex_samples = _complex_frame(frame.samples)
        detection = analyze_glrt64_dwell(
            complex_samples,
            source.configuration,
            edge=frame.target.edge,
        )
        decision = ScanDecision.ACTIVE if detection.first is not None else ScanDecision.NO_DETECTION
        waterfalls = tuple(
            StandardNumericalWaterfallV2.model_validate(
                numerical_waterfall_document(
                    bounded_waterfall(
                        _FrameReceiverReader(
                            frame,
                            source.configuration,
                            receiver_id,
                            source.identity.radio_id,
                        ),
                        resolved.waterfall,
                    ),
                    resolved.waterfall,
                )
            )
            for receiver_id in source.configuration.receiver_ids
        )
        probes = tuple(
            ScannerGlrt64ProbeMetricsV1(
                receiver_id=probe.receiver_id,
                probe_index=probe.probe_index,
                probe_start_ms=probe.probe_start_ms,
                candidates=tuple(
                    ScannerGlrt64CandidateMetricsV1(
                        candidate_rank=item.candidate_rank,
                        epoch_sample=item.epoch_sample,
                        acquired_cfo_hz=item.acquired_cfo_hz,
                        residual_cfo_hz=item.residual_cfo_hz,
                        tracking_cfo_hz=item.tracking_cfo_hz,
                        exact_score=item.exact_score,
                        control_score=item.control_score,
                        margin=item.margin,
                        passed_margin_gate=item.passed_margin_gate,
                    )
                    for item in probe.candidates
                ),
            )
            for probe in detection.probes
        )
        ci16_digest = sha256_digest(frame.samples.tobytes(order="C"))
        metrics_frames.append(
            ScannerFrameAnalysisV1(
                status="complete",
                target_index=frame.target_index,
                target=frame.target,
                source_sample_start=frame.source_sample_start,
                sample_count=len(frame.samples),
                requested_if_center_hz=frame.requested_if_center_hz,
                actual_if_center_hz=frame.actual_if_center_hz,
                iq_sha256=ci16_digest,
                decision=decision,
                decision_best_margin=detection.decision_best_margin,
                full_best_margin=detection.full_best_margin,
                first_detection=detection.first,
                reason=detection.reason,
                probes=probes,
                waterfalls=waterfalls,
            )
        )
        report_results.append(
            ScanEdgeResult(
                target=frame.target,
                decision=decision,
                requested_if_center_hz=frame.requested_if_center_hz,
                actual_if_center_hz=frame.actual_if_center_hz,
                tune_ms=frame.tune_ms,
                listen_ms=frame.listen_ms,
                iq_sha256=hashlib.sha256(complex_samples.view(np.uint8)).hexdigest(),
                first_detection=detection.first,
                best_margin=detection.decision_best_margin,
                reason=detection.reason,
            )
        )
    metrics = ScannerAnalysisMetricsV1(
        scan_id=source.scan_id,
        input_uri=source.input_uri,
        input_manifest_sha256=source.input_manifest_sha256,
        configuration=source.configuration,
        frames=tuple(metrics_frames),
    )
    report = ScannerReport(
        scan_id=source.scan_id,
        radio_id=source.identity.radio_id,
        radio_serial=source.identity.serial,
        configuration=source.configuration,
        capture_elapsed_ms=0.0,
        analysis_elapsed_ms=(time.perf_counter() - analysis_started) * 1_000,
        results=tuple(report_results),
    )
    return StandardScannerAnalysisResult(metrics=metrics, report=report)


def _complex_frame(values: npt.NDArray[np.int16]) -> npt.NDArray[np.complex64]:
    output = np.empty(values.shape[:2], dtype=np.complex64)
    output.real = values[:, :, 0]
    output.imag = values[:, :, 1]
    output.setflags(write=False)
    return output
