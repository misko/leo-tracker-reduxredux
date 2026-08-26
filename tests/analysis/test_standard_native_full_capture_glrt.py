from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from leo.analysis.standard.full_capture_glrt20ms import WindowResult
from leo.analysis.standard.native_full_capture_glrt import (
    StandardNativeFullCaptureGlrtRunner,
)
from leo.analysis.standard.runner import ReceiverStandardConfig
from leo.contracts.digests import canonical_digest
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.contracts.standard_native import NativeWindowDisposition
from leo.contracts.standard_native_glrt import StandardNativeFullCaptureGlrt20msV1
from leo.contracts.standard_pipeline import StandardPathInputBindV4
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import (
    ContinuityBoundaryReason,
    ContinuitySegmentV1,
    DeviceAxisContentKind,
    ValidityInventoryV1,
    ValidityRunV1,
)
from leo.domain.iq import IqBlock
from leo.pipeline.validity import WindowClassification, WindowValidity

_DIGEST = canonical_digest({"fixture": "native-full-capture-glrt"})


def _metadata(*, local_start: int, count: int, global_start: int) -> IqBlockMetadataV1:
    return IqBlockMetadataV1(
        radio_id="radio-0",
        receiver_ids=(0,),
        sample_count=count,
        session_sample_start=local_start,
        host_request_utc_ns=NanosecondIntervalV1(lower_ns=1, upper_ns=1),
        host_request_monotonic_ns=NanosecondIntervalV1(lower_ns=1, upper_ns=1),
        device_sample_counter=10_000 + global_start,
    )


class _SegmentReader:
    def __init__(
        self,
        owner: _Reader,
        segment: ContinuitySegmentV1,
    ) -> None:
        self._owner = owner
        self.segment = segment

    @property
    def continuity_segment_index(self) -> int:
        return self.segment.segment_index

    @property
    def global_device_sample_start(self) -> int:
        return self.segment.device_sample_start

    @property
    def sample_rate_hz(self) -> int:
        return self._owner.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        return self._owner.center_frequency_hz

    @property
    def sample_count(self) -> int:
        return self.segment.observed_sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return (0,)

    def to_global_device_sample(self, local_sample: int) -> int:
        return self.segment.device_sample_start + local_sample

    def iter_blocks(self, *, block_samples: int) -> Iterable[IqBlock]:
        chunk = min(block_samples, self._owner.source_chunk_samples)
        self._owner.segment_passes[self.segment.segment_index] += 1
        value = self._owner.segment_values[self.segment.segment_index]
        for local_start in range(0, self.sample_count, chunk):
            count = min(chunk, self.sample_count - local_start)
            samples = np.zeros((count, 1, 2), dtype="<i2")
            samples[:, 0, 0] = value
            yield IqBlock(
                samples=samples,
                metadata=_metadata(
                    local_start=local_start,
                    count=count,
                    global_start=self.global_device_sample_start + local_start,
                ),
            )


class _Reader:
    center_frequency_hz = 959_687_500
    receiver_ids = (0,)

    def __init__(
        self,
        inventory: ValidityInventoryV1,
        *,
        sample_rate_hz: int,
        segment_values: tuple[int, ...] | None = None,
        source_chunk_samples: int = 262_144,
    ) -> None:
        self.validity_inventory = inventory
        self.sample_rate_hz = sample_rate_hz
        self.sample_count = inventory.logical_sample_count
        self.observed_sample_count = inventory.observed_sample_count
        self.missing_sample_count = inventory.missing_sample_count
        self.segment_values = segment_values or tuple(
            100 * (index + 1) for index in range(len(inventory.segments))
        )
        self.source_chunk_samples = source_chunk_samples
        self.segment_passes = {segment.segment_index: 0 for segment in inventory.segments}

    def segment_readers(self) -> tuple[_SegmentReader, ...]:
        return tuple(
            _SegmentReader(self, segment)
            for segment in self.validity_inventory.segments
            if segment.observed_sample_count
        )

    def classify_window(self, device_sample_start: int, sample_count: int) -> WindowClassification:
        device_sample_stop = device_sample_start + sample_count
        if device_sample_start < 0 or device_sample_stop > self.sample_count:
            return WindowClassification(
                device_sample_start=device_sample_start,
                sample_count=sample_count,
                status=WindowValidity.OUTSIDE_SPAN,
            )
        missing = sum(
            max(
                0,
                min(device_sample_stop, run.device_sample_stop)
                - max(device_sample_start, run.device_sample_start),
            )
            for run in self.validity_inventory.runs
            if run.content_kind is DeviceAxisContentKind.ZERO_FILL
        )
        crossed = tuple(
            segment.segment_index
            for segment in self.validity_inventory.segments[1:]
            if device_sample_start < segment.device_sample_start < device_sample_stop
        )
        if missing:
            return WindowClassification(
                device_sample_start=device_sample_start,
                sample_count=sample_count,
                status=WindowValidity.GAP_OVERLAP,
                missing_sample_count=missing,
                crossed_segment_indexes=crossed,
            )
        if crossed:
            return WindowClassification(
                device_sample_start=device_sample_start,
                sample_count=sample_count,
                status=WindowValidity.CONTINUITY_BOUNDARY,
                crossed_segment_indexes=crossed,
            )
        segment = next(
            item
            for item in self.validity_inventory.segments
            if item.device_sample_start <= device_sample_start
            and device_sample_stop <= item.device_sample_stop
        )
        return WindowClassification(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            status=WindowValidity.VALID,
            continuity_segment_index=segment.segment_index,
        )

    def read_device_span(self, device_sample_start: int, sample_count: int):
        del device_sample_start, sample_count
        raise AssertionError("native GLRT must not materialize logical zero fill")

    def iter_valid_blocks(self, *, block_samples: int):
        del block_samples
        raise AssertionError("native GLRT must use segment-local readers")

    def iter_masked_blocks(self, *, block_samples: int):
        del block_samples
        raise AssertionError("native GLRT must not send a validity mask to the legacy kernel")

    def close(self) -> None:
        return


def _inventory(
    spans: tuple[tuple[int, int, ContinuityBoundaryReason | None], ...],
) -> ValidityInventoryV1:
    segments: list[ContinuitySegmentV1] = []
    runs: list[ValidityRunV1] = []
    device_cursor = 0
    stored_cursor = 0
    missing = 0
    for index, (start, stop, reason) in enumerate(spans):
        gap = start - device_cursor
        if gap:
            runs.append(
                ValidityRunV1(
                    run_index=len(runs),
                    device_sample_start=device_cursor,
                    sample_count=gap,
                    content_kind=DeviceAxisContentKind.ZERO_FILL,
                )
            )
            missing += gap
        count = stop - start
        segment = ContinuitySegmentV1(
            segment_index=index,
            device_sample_start=start,
            device_sample_stop=stop,
            stored_sample_start=stored_cursor,
            stored_sample_stop=stored_cursor + count,
            preceding_missing_sample_count=gap,
            preceding_boundary_reason=reason,
            preceding_boundary_header_sha256=None if index == 0 else _DIGEST,
        )
        segments.append(segment)
        if count:
            runs.append(
                ValidityRunV1(
                    run_index=len(runs),
                    device_sample_start=start,
                    sample_count=count,
                    content_kind=DeviceAxisContentKind.OBSERVED,
                    stored_sample_start=stored_cursor,
                    continuity_segment_index=index,
                )
            )
        stored_cursor += count
        device_cursor = stop
    return ValidityInventoryV1(
        stream_id="stream-0",
        timeline_sha256=_DIGEST,
        gap_map_content_digest=_DIGEST,
        first_device_sample_counter=10_000,
        logical_sample_count=device_cursor,
        observed_sample_count=stored_cursor,
        missing_sample_count=missing,
        continuity_boundary_count=len(segments) - 1,
        runs=tuple(runs),
        segments=tuple(segments),
    )


def _binding(inventory: ValidityInventoryV1, *, rate: int) -> StandardPathInputBindV4:
    return StandardPathInputBindV4.model_construct(
        session_id="session-0",
        stream_id="stream-0",
        radio_id="radio-0",
        receiver_id=0,
        manifest_digest=_DIGEST,
        synchronization_inventory_digest=_DIGEST,
        binding_digest=_DIGEST,
        tuned_center_frequency_hz=_Reader.center_frequency_hz,
        sample_rate_hz=rate,
        logical_sample_count=inventory.logical_sample_count,
        observed_sample_count=inventory.observed_sample_count,
        missing_sample_count=inventory.missing_sample_count,
        starlink_edge=StarlinkEdge.LOWER,
        timing={
            "schema_version": 1,
            "first_estimate_utc_ns": 1_000_000_000,
            "first_earliest_utc_ns": 999_999_900,
            "first_latest_utc_ns": 1_000_000_100,
            "last_estimate_utc_ns": 2_000_000_000,
            "last_earliest_utc_ns": 1_999_999_900,
            "last_latest_utc_ns": 2_000_000_100,
        },
        validity_inventory=inventory,
    )


def _config() -> ReceiverStandardConfig:
    base = ReceiverStandardConfig()
    return replace(
        base,
        full_capture_glrt20ms=replace(
            base.full_capture_glrt20ms,
            maximum_workers=1,
        ),
    )


def _window_result(
    index: int,
    start: int,
    samples: np.ndarray,
    *,
    rate: int,
    passing: bool = False,
    robust: bool = False,
) -> WindowResult:
    start_s = start / rate
    end_s = (start + len(samples)) / rate
    value = float(np.real(samples[0]))
    return WindowResult(
        probe_index=index,
        sample_start=start,
        start_time_s=start_s,
        center_time_s=(start_s + end_s) / 2,
        end_time_s=end_s,
        acquisition_status="complete" if passing else "no_result",
        candidate_count=1 if passing else 0,
        best_candidate_rank=1 if passing else None,
        epoch_sample=5 if passing else None,
        acquired_cfo_hz=value if passing else None,
        residual_cfo_hz=value if passing else None,
        tracking_cfo_hz=value if passing else None,
        glrt_exact_score=1.0 if passing else None,
        glrt_control_score=0.5 if passing else None,
        glrt_margin=0.5 if passing else None,
        passed_margin_gate=passing,
        lattice_frame_count=0,
        measured_frame_count=0,
        robust_line_available=robust,
        robust_reference_time_s=(start_s + 0.01 if robust else None),
        robust_cfo_at_reference_hz=(value if robust else None),
        robust_slope_hz_s=(100.0 if robust else None),
        robust_slope_sigma_hz_s=(1.0 if robust else None),
        robust_residual_rms_hz=(2.0 if robust else None),
        robust_median_absolute_residual_hz=(1.0 if robust else None),
        robust_mad_scale_hz=(1.0 if robust else None),
        robust_outlier_count=0,
        robust_converged=(True if robust else None),
        reason="deterministic test window",
    )


def _empty_segment_fit(rows: tuple[WindowResult, ...]):
    return (
        {
            "input_observation_count": sum(item.passed_margin_gate for item in rows),
            "raw_hough_track_count": 0,
            "truncated_hough_track_count": 0,
            "published_track_count": 0,
            "returned_observation_count": 0,
            "tracks": [],
        },
        None,
    )


@pytest.mark.parametrize("rate", [2_500_000, 3_000_000, 5_000_000])
def test_global_20ms_geometry_is_exact_at_every_native_rate(rate: int) -> None:
    logical = rate * 40 // 1_000
    inventory = _inventory(((0, logical, None),))
    reader = _Reader(inventory, sample_rate_hz=rate)
    seen: list[tuple[int, int]] = []

    def kernel(index: int, start: int, samples: np.ndarray) -> WindowResult:
        seen.append((start, len(samples)))
        return _window_result(index, start, samples, rate=rate)

    result = StandardNativeFullCaptureGlrtRunner(
        _config(), window_kernel=kernel, segment_kernel=_empty_segment_fit
    ).run(reader, _binding(inventory, rate=rate), edge=StarlinkEdge.LOWER)

    window = rate * 20 // 1_000
    stride = rate * 10 // 1_000
    assert (result.window_samples, result.stride_samples) == (window, stride)
    assert seen == [(0, window), (stride, window), (2 * stride, window)]
    assert result.accounting.scheduled_count == result.accounting.valid_count == 3
    assert reader.segment_passes == {0: 1}


@pytest.mark.parametrize(
    ("spans", "expected_disposition", "boundary_start"),
    [
        (
            ((0, 75_001, None), (75_002, 150_001, "counter_gap")),
            NativeWindowDisposition.GAP_OVERLAP,
            75_002,
        ),
        (
            ((0, 262_144, None), (262_208, 400_000, "counter_gap")),
            NativeWindowDisposition.GAP_OVERLAP,
            262_208,
        ),
        (
            ((0, 100_001, None), (125_000, 125_000, "terminal_counter_gap")),
            NativeWindowDisposition.GAP_OVERLAP,
            125_000,
        ),
        (
            ((0, 75_001, None), (75_001, 150_000, "overflow_flag")),
            NativeWindowDisposition.CONTINUITY_BOUNDARY,
            75_001,
        ),
    ],
    ids=("one-sample-gap", "refill-gap", "terminal-gap", "overflow-only"),
)
def test_gap_and_boundary_windows_are_retained_but_never_dispatched(
    spans: tuple[tuple[int, int, ContinuityBoundaryReason | None], ...],
    expected_disposition: NativeWindowDisposition,
    boundary_start: int,
) -> None:
    rate = 2_500_000
    inventory = _inventory(spans)
    reader = _Reader(inventory, sample_rate_hz=rate)
    analyzed_starts: list[int] = []

    def kernel(index: int, start: int, samples: np.ndarray) -> WindowResult:
        analyzed_starts.append(start)
        assert not (start < boundary_start < start + len(samples))
        return _window_result(index, start, samples, rate=rate)

    result = StandardNativeFullCaptureGlrtRunner(
        _config(), window_kernel=kernel, segment_kernel=_empty_segment_fit
    ).run(reader, _binding(inventory, rate=rate), edge=StarlinkEdge.LOWER)

    excluded = tuple(
        item
        for item in result.opportunities
        if item.validity.disposition is not NativeWindowDisposition.VALID
    )
    assert excluded
    assert expected_disposition in tuple(item.validity.disposition for item in excluded)
    assert len(analyzed_starts) == result.accounting.analyzed_count
    assert len(result.opportunities) == result.accounting.scheduled_count
    assert tuple(item.continuity_segment for item in result.segments) == inventory.segments


def test_opposite_segment_sentinels_are_never_sent_to_one_fit() -> None:
    rate = 2_500_000
    inventory = _inventory(((0, 100_000, None), (100_001, 200_001, "counter_gap")))
    reader = _Reader(
        inventory,
        sample_rate_hz=rate,
        segment_values=(-1_000, 1_000),
    )
    fit_inputs: list[tuple[float, ...]] = []

    def window_kernel(index: int, start: int, samples: np.ndarray) -> WindowResult:
        return _window_result(index, start, samples, rate=rate, passing=True)

    def segment_kernel(rows: tuple[WindowResult, ...]):
        values = tuple(item.tracking_cfo_hz for item in rows)
        assert all(item is not None for item in values)
        fit_inputs.append(tuple(float(item) for item in values if item is not None))
        return _empty_segment_fit(rows)

    result = StandardNativeFullCaptureGlrtRunner(
        _config(), window_kernel=window_kernel, segment_kernel=segment_kernel
    ).run(reader, _binding(inventory, rate=rate), edge=StarlinkEdge.LOWER)

    assert len(fit_inputs) == 2
    assert all(all(value < 0 for value in fit_inputs[0]) for _ in (0,))
    assert all(value > 0 for value in fit_inputs[1])
    assert all(not ({-1, 1} <= {int(np.sign(value)) for value in group}) for group in fit_inputs)
    assert tuple(item.continuity_segment.segment_index for item in result.segments) == (0, 1)


def test_hough_and_rate_results_retain_global_segment_coordinates() -> None:
    rate = 3_000_000
    inventory = _inventory(((0, 120_000, None),))

    def window_kernel(index: int, start: int, samples: np.ndarray) -> WindowResult:
        return _window_result(
            index,
            start,
            samples,
            rate=rate,
            passing=True,
            robust=True,
        )

    def segment_kernel(rows: tuple[WindowResult, ...]):
        first = rows[0]
        last = rows[-1]
        return (
            {
                "input_observation_count": len(rows),
                "raw_hough_track_count": 1,
                "truncated_hough_track_count": 0,
                "published_track_count": 1,
                "returned_observation_count": len(rows),
                "tracks": [
                    {
                        "track_label": "H1",
                        "start_s": first.start_time_s,
                        "end_s": last.start_time_s,
                        "reference_time_s": first.start_time_s,
                        "slope_hz_s": 100.0,
                        "cfo_at_reference_hz": first.tracking_cfo_hz,
                        "observation_count": len(rows),
                        "observations": [
                            {
                                "time_s": item.start_time_s,
                                "raw_cfo_hz": item.tracking_cfo_hz,
                                "alias_index": 0,
                            }
                            for item in rows
                        ],
                    }
                ],
            },
            {
                "input_filter": (
                    "margin passes; within-window line RMS is at or below the display reference; "
                    "Doppler rate lies inside +/-10 kHz/s"
                ),
                "point_count": len(rows),
                "start_s": first.center_time_s,
                "end_s": last.center_time_s,
                "constant_doppler_rate_hz_s": 100.0,
                "median_absolute_deviation_hz_s": 0.0,
            },
        )

    result = StandardNativeFullCaptureGlrtRunner(
        _config(), window_kernel=window_kernel, segment_kernel=segment_kernel
    ).run(
        _Reader(inventory, sample_rate_hz=rate),
        _binding(inventory, rate=rate),
        edge=StarlinkEdge.LOWER,
    )

    segment = result.segments[0]
    track = segment.hough.tracks[0]
    assert tuple(item.global_device_sample for item in track.observations) == (
        0,
        30_000,
        60_000,
    )
    assert track.global_reference_device_sample == 0
    assert segment.constant_rate is not None
    assert segment.constant_rate.supporting_opportunity_indexes == (0, 1, 2)
    assert segment.constant_rate.global_center_sample_start == 30_000
    assert segment.constant_rate.global_center_sample_end == 90_000


def test_default_numerical_kernel_accepts_one_wholly_valid_zero_window() -> None:
    rate = 2_500_000
    inventory = _inventory(((0, 50_000, None),))

    result = StandardNativeFullCaptureGlrtRunner(_config()).run(
        _Reader(inventory, sample_rate_hz=rate),
        _binding(inventory, rate=rate),
        edge=StarlinkEdge.LOWER,
    )

    assert result.accounting.scheduled_count == result.accounting.analyzed_count == 1
    assert len(result.segments[0].windows) == 1
    assert not result.segments[0].windows[0].passed_margin_gate


def test_runner_rejects_edge_that_differs_from_v4_binding() -> None:
    rate = 2_500_000
    inventory = _inventory(((0, 50_000, None),))

    runner = StandardNativeFullCaptureGlrtRunner(_config())
    with pytest.raises(ValueError, match="edge differs"):
        runner.run(
            _Reader(inventory, sample_rate_hz=rate),
            _binding(inventory, rate=rate),
            edge=StarlinkEdge.UPPER,
        )
    assert runner.poisoned


def test_runner_poison_discards_failed_partial_execution() -> None:
    rate = 2_500_000
    inventory = _inventory(((0, 100_000, None),))
    reader = _Reader(inventory, sample_rate_hz=rate)
    fit_called = False

    def window_kernel(index: int, start: int, samples: np.ndarray) -> WindowResult:
        if index == 1:
            raise KeyboardInterrupt("injected kernel abort")
        return _window_result(index, start, samples, rate=rate)

    def segment_kernel(rows: tuple[WindowResult, ...]):
        nonlocal fit_called
        fit_called = True
        return _empty_segment_fit(rows)

    runner = StandardNativeFullCaptureGlrtRunner(
        _config(), window_kernel=window_kernel, segment_kernel=segment_kernel
    )
    with pytest.raises(KeyboardInterrupt, match="injected kernel abort"):
        runner.run(reader, _binding(inventory, rate=rate), edge=StarlinkEdge.LOWER)
    assert runner.poisoned
    assert not fit_called
    with pytest.raises(RuntimeError, match="poisoned"):
        runner.run(reader, _binding(inventory, rate=rate), edge=StarlinkEdge.LOWER)


def test_result_is_invariant_to_source_and_kernel_chunking() -> None:
    rate = 3_000_000
    inventory = _inventory(((0, 90_001, None), (90_008, 180_008, "counter_gap")))
    binding = _binding(inventory, rate=rate)

    def kernel(index: int, start: int, samples: np.ndarray) -> WindowResult:
        return _window_result(index, start, samples, rate=rate, passing=True)

    first = StandardNativeFullCaptureGlrtRunner(
        _config(),
        block_samples=7_919,
        window_kernel=kernel,
        segment_kernel=_empty_segment_fit,
    ).run(
        _Reader(inventory, sample_rate_hz=rate, source_chunk_samples=8_191),
        binding,
        edge=StarlinkEdge.LOWER,
    )
    second = StandardNativeFullCaptureGlrtRunner(
        _config(),
        block_samples=31_337,
        window_kernel=kernel,
        segment_kernel=_empty_segment_fit,
    ).run(
        _Reader(inventory, sample_rate_hz=rate, source_chunk_samples=65_537),
        binding,
        edge=StarlinkEdge.LOWER,
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_contract_rejects_cross_segment_window_even_with_rewritten_digests() -> None:
    rate = 2_500_000
    inventory = _inventory(((0, 100_000, None), (100_001, 200_001, "counter_gap")))
    result = StandardNativeFullCaptureGlrtRunner(
        _config(),
        window_kernel=lambda index, start, samples: _window_result(
            index, start, samples, rate=rate
        ),
        segment_kernel=_empty_segment_fit,
    ).run(
        _Reader(inventory, sample_rate_hz=rate),
        _binding(inventory, rate=rate),
        edge=StarlinkEdge.LOWER,
    )
    document: dict[str, Any] = result.model_dump(mode="json")
    segments = document["segments"]
    assert isinstance(segments, list)
    first_windows = segments[0]["windows"]
    second_windows = segments[1]["windows"]
    assert first_windows and second_windows
    moved = first_windows.pop()
    second_windows.insert(0, moved)
    for segment in segments:
        segment["valid_opportunity_indexes"] = [
            item["opportunity_index"] for item in segment["windows"]
        ]
        segment["segment_digest"] = canonical_digest(
            {key: value for key, value in segment.items() if key != "segment_digest"}
        )
    document["segment_results_digest"] = canonical_digest(segments)
    document["result_digest"] = canonical_digest(
        {key: value for key, value in document.items() if key != "result_digest"}
    )

    with pytest.raises(ValidationError, match="escaped its valid opportunity"):
        StandardNativeFullCaptureGlrt20msV1.model_validate(document)
