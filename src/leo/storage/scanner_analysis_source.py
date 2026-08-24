"""Read-only segmented scanner analysis adapters for live and replay bundles."""

from __future__ import annotations

import numpy as np

from leo.scanner.analysis_models import ScannerFrameContinuityEvidenceV1
from leo.scanner.models import ScannerConfigurationV2, ScannerIqFrameV2
from leo.scanner.ports import ScanRadioIdentity
from leo.scanner.standard_analysis import ScannerAnalysisFrameInput, SegmentedScannerSource
from leo.storage.scanner import PublishedScannerIqBundle, ScannerIqStore
from leo.storage.scanner_replay import PublishedScannerReplaySweep, ScannerReplayStore


def live_scanner_analysis_source(
    store: ScannerIqStore,
    bundle: PublishedScannerIqBundle,
    *,
    capture_elapsed_ms: float = 0.0,
) -> SegmentedScannerSource:
    values = store.read_ci16(bundle, verify=True)
    manifest = bundle.manifest
    frames_by_target = {item.target_index: item for item in manifest.frames}
    failures_by_target = {item.target_index: item for item in manifest.failures}
    frames: list[ScannerAnalysisFrameInput] = []
    for target_index, target in enumerate(manifest.configuration.targets):
        frame = frames_by_target.get(target_index)
        if frame is None:
            failure = failures_by_target[target_index]
            continuity = (
                ScannerFrameContinuityEvidenceV1(
                    status="capture_failed",
                    target_index=target_index,
                    continuity_observable=False,
                    within_frame_continuity="unavailable_capture_failed",
                    reason=failure.reason,
                )
                if isinstance(manifest.configuration, ScannerConfigurationV2)
                else None
            )
            frames.append(
                ScannerAnalysisFrameInput(
                    target_index=target_index,
                    target=target,
                    source_sample_start=0,
                    requested_if_center_hz=target.if_center_hz,
                    actual_if_center_hz=None,
                    tune_ms=None,
                    listen_ms=None,
                    samples=None,
                    error=failure.reason,
                    continuity=continuity,
                )
            )
            continue
        selected = np.ascontiguousarray(
            values[frame.sample_start : frame.sample_start + frame.sample_count]
        )
        continuity = None
        if isinstance(manifest.configuration, ScannerConfigurationV2):
            if not isinstance(frame, ScannerIqFrameV2):
                raise ValueError("scanner V2 manifest contains a non-V2 frame")
            continuity = ScannerFrameContinuityEvidenceV1(
                status="attested",
                target_index=target_index,
                metadata_abi_version=frame.metadata_abi_version,
                stream_id=frame.stream_id,
                stream_generation=frame.stream_generation,
                buffer_sequence=frame.buffer_sequence,
                source_sequence=frame.source_sequence,
                first_sample_sequence=frame.first_sample_sequence,
                last_sample_sequence_exclusive=frame.last_sample_sequence_exclusive,
                device_sample_counter=frame.device_sample_counter,
                device_sample_counter_end_exclusive=(frame.device_sample_counter_end_exclusive),
                metadata_flags=frame.metadata_flags,
                sample_time_realtime_start_ns=frame.sample_time_realtime_start_ns,
                sample_time_realtime_end_ns=frame.sample_time_realtime_end_ns,
                sample_time_monotonic_start_ns=frame.sample_time_monotonic_start_ns,
                sample_time_monotonic_end_ns=frame.sample_time_monotonic_end_ns,
                sample_time_uncertainty_ns=frame.sample_time_uncertainty_ns,
                kernel_buffers_requested=frame.kernel_buffers_requested,
                kernel_buffers_readback=frame.kernel_buffers_readback,
                reset_episode=frame.reset_episode,
                missing_samples_before=frame.missing_samples_before,
                overflow_observed=frame.overflow_observed,
                continuity_observable=frame.continuity_observable,
                within_frame_continuity=frame.within_frame_continuity,
                reason="FPGA metadata proves continuity inside this reset-bounded frame",
            )
        frames.append(
            ScannerAnalysisFrameInput(
                target_index=target_index,
                target=target,
                source_sample_start=frame.sample_start,
                requested_if_center_hz=frame.requested_if_center_hz,
                actual_if_center_hz=frame.actual_if_center_hz,
                tune_ms=frame.tune_ms,
                listen_ms=frame.listen_ms,
                samples=selected,
                continuity=continuity,
            )
        )
    return SegmentedScannerSource(
        scan_id=manifest.scan_id,
        input_uri=bundle.uri,
        input_manifest_sha256=bundle.manifest_sha256,
        identity=ScanRadioIdentity(
            radio_id=manifest.radio_id,
            serial=manifest.radio_serial,
            uri=manifest.radio_uri,
        ),
        configuration=manifest.configuration,
        frames=tuple(frames),
        capture_elapsed_ms=capture_elapsed_ms,
    )


def replay_scanner_analysis_source(
    store: ScannerReplayStore,
    sweep: PublishedScannerReplaySweep,
) -> SegmentedScannerSource:
    values = store.read_ci16(sweep, verify=True)
    manifest = sweep.manifest
    frames = tuple(
        ScannerAnalysisFrameInput(
            target_index=frame.target_index,
            target=frame.target,
            source_sample_start=frame.sample_start,
            requested_if_center_hz=frame.source.requested_settings.center_frequency_hz,
            actual_if_center_hz=frame.source.applied_settings.center_frequency_hz,
            tune_ms=0.0,
            listen_ms=float(manifest.configuration.dwell_ms),
            samples=np.ascontiguousarray(
                values[frame.sample_start : frame.sample_start + frame.sample_count]
            ),
        )
        for frame in manifest.frames
    )
    return SegmentedScannerSource(
        scan_id=f"replay-{manifest.dataset_id}-{manifest.sweep_id}",
        input_uri=sweep.uri,
        input_manifest_sha256=sweep.manifest_sha256,
        identity=ScanRadioIdentity(
            radio_id="scanner-replay",
            serial=manifest.dataset_id,
            uri=sweep.uri,
        ),
        configuration=manifest.configuration,
        frames=frames,
    )
