"""Read-only segmented scanner analysis adapters for live and replay bundles."""

from __future__ import annotations

import numpy as np

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
                )
            )
            continue
        selected = np.ascontiguousarray(
            values[frame.sample_start : frame.sample_start + frame.sample_count]
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
