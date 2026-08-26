from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pytest

from leo.analysis.standard.native_windows import (
    NativeWindowDecision,
    NativeWindowPurpose,
    NativeWindowRequest,
    StandardNativeWindowAdapter,
    native_opportunity_accounting,
    native_window_evidence,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.contracts.standard_native import (
    NativeProbeWindowV3,
    NativeWindowDisposition,
    NativeWindowEvidenceV1,
    StandardNativeSourceV1,
    StandardProbeScheduleV3,
)
from leo.contracts.standard_pipeline import ProbeWindowV2
from leo.contracts.validity import (
    ContinuitySegmentV1,
    DeviceAxisContentKind,
    ValidityInventoryV1,
    ValidityRunV1,
)
from leo.domain.iq import IqBlock
from leo.pipeline.validity import WindowClassification, WindowValidity

_DIGEST_A = f"sha256:{'a' * 64}"
_DIGEST_B = f"sha256:{'b' * 64}"
_DIGEST_C = f"sha256:{'c' * 64}"


def _metadata(
    *,
    local_start: int,
    sample_count: int,
    global_start: int,
) -> IqBlockMetadataV1:
    return IqBlockMetadataV1(
        radio_id="radio-0",
        receiver_ids=(0,),
        sample_count=sample_count,
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
        if not 0 <= local_sample <= self.sample_count:
            raise ValueError("local test sample lies outside its segment")
        return self.global_device_sample_start + local_sample

    def iter_blocks(self, *, block_samples: int) -> Iterable[IqBlock]:
        self._owner.segment_passes[self.segment.segment_index] += 1
        value = self._owner.segment_values[self.segment.segment_index]
        for local_start in range(0, self.sample_count, block_samples):
            count = min(block_samples, self.sample_count - local_start)
            yield IqBlock(
                samples=np.full((count, 1, 2), value, dtype="<i2"),
                metadata=_metadata(
                    local_start=local_start,
                    sample_count=count,
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
        sample_rate_hz: int = 1_000,
        segment_values: tuple[int, ...] | None = None,
    ) -> None:
        self.validity_inventory = inventory
        self.sample_rate_hz = sample_rate_hz
        self.sample_count = inventory.logical_sample_count
        self.observed_sample_count = inventory.observed_sample_count
        self.missing_sample_count = inventory.missing_sample_count
        self.segment_values = segment_values or tuple(
            11 * (index + 1) for index in range(len(inventory.segments))
        )
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
            segment
            for segment in self.validity_inventory.segments
            if segment.device_sample_start <= device_sample_start
            and device_sample_stop <= segment.device_sample_stop
        )
        return WindowClassification(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            status=WindowValidity.VALID,
            continuity_segment_index=segment.segment_index,
        )

    def read_device_span(self, device_sample_start: int, sample_count: int):
        del device_sample_start, sample_count
        raise AssertionError("kernel adapter must not expose mask-blind logical zeros")

    def iter_valid_blocks(self, *, block_samples: int):
        del block_samples
        raise AssertionError("window extraction must use segment-local authority")

    def iter_masked_blocks(self, *, block_samples: int):
        del block_samples
        raise AssertionError("window extraction must not materialize zero fill")

    def close(self) -> None:
        return


def _three_segment_inventory() -> ValidityInventoryV1:
    segments = (
        ContinuitySegmentV1(
            segment_index=0,
            device_sample_start=0,
            device_sample_stop=8,
            stored_sample_start=0,
            stored_sample_stop=8,
        ),
        ContinuitySegmentV1(
            segment_index=1,
            device_sample_start=10,
            device_sample_stop=16,
            stored_sample_start=8,
            stored_sample_stop=14,
            preceding_missing_sample_count=2,
            preceding_boundary_reason="counter_gap",
            preceding_boundary_header_sha256=_DIGEST_C,
        ),
        ContinuitySegmentV1(
            segment_index=2,
            device_sample_start=16,
            device_sample_stop=24,
            stored_sample_start=14,
            stored_sample_stop=22,
            preceding_missing_sample_count=0,
            preceding_boundary_reason="overflow_flag",
            preceding_boundary_header_sha256=_DIGEST_C,
        ),
    )
    runs = (
        ValidityRunV1(
            run_index=0,
            device_sample_start=0,
            sample_count=8,
            content_kind=DeviceAxisContentKind.OBSERVED,
            stored_sample_start=0,
            continuity_segment_index=0,
        ),
        ValidityRunV1(
            run_index=1,
            device_sample_start=8,
            sample_count=2,
            content_kind=DeviceAxisContentKind.ZERO_FILL,
        ),
        ValidityRunV1(
            run_index=2,
            device_sample_start=10,
            sample_count=6,
            content_kind=DeviceAxisContentKind.OBSERVED,
            stored_sample_start=8,
            continuity_segment_index=1,
        ),
        ValidityRunV1(
            run_index=3,
            device_sample_start=16,
            sample_count=8,
            content_kind=DeviceAxisContentKind.OBSERVED,
            stored_sample_start=14,
            continuity_segment_index=2,
        ),
    )
    return ValidityInventoryV1(
        stream_id="stream-0",
        timeline_sha256=_DIGEST_A,
        gap_map_content_digest=_DIGEST_B,
        first_device_sample_counter=10_000,
        logical_sample_count=24,
        observed_sample_count=22,
        missing_sample_count=2,
        continuity_boundary_count=2,
        runs=runs,
        segments=segments,
    )


def _one_gap_inventory(
    *,
    logical_count: int,
    gap_start: int,
    gap_count: int = 1,
) -> ValidityInventoryV1:
    second_start = gap_start + gap_count
    segments = (
        ContinuitySegmentV1(
            segment_index=0,
            device_sample_start=0,
            device_sample_stop=gap_start,
            stored_sample_start=0,
            stored_sample_stop=gap_start,
        ),
        ContinuitySegmentV1(
            segment_index=1,
            device_sample_start=second_start,
            device_sample_stop=logical_count,
            stored_sample_start=gap_start,
            stored_sample_stop=logical_count - gap_count,
            preceding_missing_sample_count=gap_count,
            preceding_boundary_reason="counter_gap",
            preceding_boundary_header_sha256=_DIGEST_C,
        ),
    )
    runs = (
        ValidityRunV1(
            run_index=0,
            device_sample_start=0,
            sample_count=gap_start,
            content_kind=DeviceAxisContentKind.OBSERVED,
            stored_sample_start=0,
            continuity_segment_index=0,
        ),
        ValidityRunV1(
            run_index=1,
            device_sample_start=gap_start,
            sample_count=gap_count,
            content_kind=DeviceAxisContentKind.ZERO_FILL,
        ),
        ValidityRunV1(
            run_index=2,
            device_sample_start=second_start,
            sample_count=logical_count - second_start,
            content_kind=DeviceAxisContentKind.OBSERVED,
            stored_sample_start=gap_start,
            continuity_segment_index=1,
        ),
    )
    return ValidityInventoryV1(
        stream_id="stream-0",
        timeline_sha256=_DIGEST_A,
        gap_map_content_digest=_DIGEST_B,
        first_device_sample_counter=10_000,
        logical_sample_count=logical_count,
        observed_sample_count=logical_count - gap_count,
        missing_sample_count=gap_count,
        continuity_boundary_count=1,
        runs=runs,
        segments=segments,
    )


def _values(reader) -> np.ndarray:
    return np.concatenate([block.samples for block in reader.iter_blocks(block_samples=3)])


def test_window_gate_partitions_support_and_never_dispatches_boundary_poison() -> None:
    reader = _Reader(
        _three_segment_inventory(),
        segment_values=(11, 22, -32_768),
    )
    adapter = StandardNativeWindowAdapter(reader)
    requests = tuple(
        NativeWindowRequest(index, NativeWindowPurpose.FRAME_QAM, start, count)
        for index, (start, count) in enumerate(
            ((-1, 1), (0, 4), (2, 4), (6, 4), (10, 4), (14, 4), (16, 4))
        )
    )
    decisions = adapter.decide(requests)
    assert [item.classification.status for item in decisions] == [
        WindowValidity.OUTSIDE_SPAN,
        WindowValidity.VALID,
        WindowValidity.VALID,
        WindowValidity.GAP_OVERLAP,
        WindowValidity.VALID,
        WindowValidity.CONTINUITY_BOUNDARY,
        WindowValidity.VALID,
    ]
    accounting = native_opportunity_accounting(decisions, analyzed_count=4)
    assert (
        accounting.scheduled_count,
        accounting.valid_count,
        accounting.gap_excluded_count,
        accounting.continuity_boundary_excluded_count,
        accounting.outside_span_count,
    ) == (7, 4, 1, 1, 1)

    dispatched = tuple(adapter.iter_valid_windows(decisions, block_samples=3))
    assert [item.request.device_sample_start for item, _iq in dispatched] == [0, 2, 10, 16]
    assert [iq.continuity_segment_index for _item, iq in dispatched] == [0, 0, 1, 2]
    # A stateful numerical kernel sees one constant segment at a time.  The
    # excluded [14, 18) opportunity would mix 22 with the -32768 poison.
    assert [np.unique(_values(iq)).tolist() for _item, iq in dispatched] == [
        [11],
        [11],
        [22],
        [-32_768],
    ]
    assert reader.segment_passes == {0: 1, 1: 1, 2: 1}
    for decision, iq in dispatched:
        assert iq.to_global_device_sample(0) == decision.request.device_sample_start
        assert iq.to_global_device_sample(iq.sample_count) == decision.request.device_sample_stop


def test_fft_windows_reset_at_gap_and_overflow_only_boundaries() -> None:
    reader = _Reader(
        _three_segment_inventory(),
        segment_values=(101, 202, 303),
    )
    windows = tuple(
        StandardNativeWindowAdapter(reader).iter_fft_windows(
            fft_samples=4,
            hop_samples=2,
            block_samples=3,
        )
    )
    assert [decision.request.device_sample_start for decision, _iq in windows] == [
        0,
        2,
        4,
        10,
        12,
        16,
        18,
        20,
    ]
    assert [iq.continuity_segment_index for _decision, iq in windows] == [
        0,
        0,
        0,
        1,
        1,
        2,
        2,
        2,
    ]
    assert all(len(np.unique(_values(iq))) == 1 for _decision, iq in windows)
    assert reader.segment_passes == {0: 1, 1: 1, 2: 1}


def test_global_20ms_glrt_schedule_excludes_every_gap_overlap_once() -> None:
    reader = _Reader(_one_gap_inventory(logical_count=40, gap_start=20))
    decisions = StandardNativeWindowAdapter(reader).full_capture_glrt20ms_schedule()
    assert [item.request.device_sample_start for item in decisions] == [0, 10, 20]
    assert [item.classification.status for item in decisions] == [
        WindowValidity.VALID,
        WindowValidity.GAP_OVERLAP,
        WindowValidity.GAP_OVERLAP,
    ]
    accounting = native_opportunity_accounting(decisions, analyzed_count=1)
    assert accounting.scheduled_count == 3
    assert accounting.valid_count == 1
    assert accounting.gap_excluded_count == 2
    dispatched = tuple(StandardNativeWindowAdapter(reader).iter_valid_windows(decisions))
    assert [(item.request.device_sample_start, iq.sample_count) for item, iq in dispatched] == [
        (0, 20)
    ]


@pytest.mark.parametrize("gap_count", [1, 3, 16])
def test_no_valid_fixed_window_can_cross_any_positive_gap(gap_count: int) -> None:
    gap_start = 23
    reader = _Reader(
        _one_gap_inventory(
            logical_count=80,
            gap_start=gap_start,
            gap_count=gap_count,
        )
    )
    adapter = StandardNativeWindowAdapter(reader)
    decisions = adapter.fixed_stride_schedule(
        purpose=NativeWindowPurpose.FULL_CAPTURE_GLRT20MS,
        window_samples=9,
        stride_samples=2,
    )
    expected_gap_overlaps = 0
    for decision in decisions:
        start = decision.request.device_sample_start
        stop = decision.request.device_sample_stop
        overlap = max(0, min(stop, gap_start + gap_count) - max(start, gap_start))
        if overlap:
            expected_gap_overlaps += 1
            assert decision.classification.status is WindowValidity.GAP_OVERLAP
            assert decision.classification.missing_sample_count == overlap
        if decision.eligible:
            assert stop <= gap_start or start >= gap_start + gap_count
    accounting = native_opportunity_accounting(
        decisions,
        analyzed_count=sum(item.eligible for item in decisions),
    )
    assert accounting.gap_excluded_count == expected_gap_overlaps
    assert len(tuple(adapter.iter_valid_windows(decisions, block_samples=7))) == (
        accounting.valid_count
    )


def test_persisted_probe_schedule_binds_to_live_validity_before_iq_dispatch() -> None:
    reader = _Reader(_three_segment_inventory(), sample_rate_hz=2_500_000)
    adapter = StandardNativeWindowAdapter(reader)
    requests = (
        NativeWindowRequest(0, NativeWindowPurpose.PROBE_20MS, 0, 4),
        NativeWindowRequest(1, NativeWindowPurpose.PROBE_20MS, 6, 4),
    )
    decisions = adapter.decide(requests)
    opportunities = tuple(
        NativeProbeWindowV3(
            probe=ProbeWindowV2(
                probe_id=(f"sha256:{index + 1:064x}"),
                coarse_window_index=0,
                subwindow_index=index,
                probe_offset_ms=0,
                sample_start=decision.request.device_sample_start,
                sample_count=decision.request.sample_count,
                time_s=decision.request.device_sample_start / reader.sample_rate_hz,
            ),
            validity=native_window_evidence(decision.classification),
        )
        for index, decision in enumerate(decisions)
    )
    source = StandardNativeSourceV1(
        session_id="session-0",
        stream_id="stream-0",
        radio_id="radio-0",
        receiver_id=0,
        manifest_digest=_DIGEST_B,
        synchronization_inventory_digest=_DIGEST_C,
        path_input_binding_digest=_DIGEST_A,
        validity_inventory_digest=reader.validity_inventory.inventory_digest,
        tuned_center_frequency_hz=reader.center_frequency_hz,
        sample_rate_hz=reader.sample_rate_hz,
        logical_sample_count=reader.sample_count,
        observed_sample_count=reader.observed_sample_count,
        missing_sample_count=reader.missing_sample_count,
        timing={
            "schema_version": 1,
            "first_estimate_utc_ns": 1_000_000_000,
            "first_earliest_utc_ns": 999_999_900,
            "first_latest_utc_ns": 1_000_000_100,
            "last_estimate_utc_ns": 1_000_004_000,
            "last_earliest_utc_ns": 1_000_003_900,
            "last_latest_utc_ns": 1_000_004_100,
        },
        continuity_segments=reader.validity_inventory.segments,
    )
    schedule = _probe_schedule(source, opportunities)
    dispatched = tuple(adapter.iter_valid_probe_windows(schedule, block_samples=3))
    assert [(item.probe.sample_start, iq.sample_count) for item, iq in dispatched] == [(0, 4)]

    forged = list(opportunities)
    forged[0] = forged[0].model_copy(
        update={
            "validity": NativeWindowEvidenceV1(
                device_sample_start=0,
                sample_count=4,
                disposition=NativeWindowDisposition.OUTSIDE_SPAN,
            )
        }
    )
    forged_schedule = _probe_schedule(source, tuple(forged))
    with pytest.raises(ValueError, match="validity disagrees"):
        tuple(adapter.iter_valid_probe_windows(forged_schedule))


def _probe_schedule(
    source: StandardNativeSourceV1,
    opportunities: tuple[NativeProbeWindowV3, ...],
) -> StandardProbeScheduleV3:
    decisions = tuple(
        NativeWindowDecision(
            request=NativeWindowRequest(
                opportunity_index=index,
                purpose=NativeWindowPurpose.PROBE_20MS,
                device_sample_start=item.probe.sample_start,
                sample_count=item.probe.sample_count,
            ),
            classification=WindowClassification(
                device_sample_start=item.validity.device_sample_start,
                sample_count=item.validity.sample_count,
                status=WindowValidity(item.validity.disposition.value),
                missing_sample_count=item.validity.missing_sample_count,
                continuity_segment_index=item.validity.continuity_segment_index,
                crossed_segment_indexes=item.validity.crossed_segment_indexes,
            ),
        )
        for index, item in enumerate(opportunities)
    )
    accounting = native_opportunity_accounting(decisions, analyzed_count=0)
    values = {
        "source": source.model_dump(mode="json"),
        "coarse_window_ms": 1_000,
        "subwindow_ms": 50,
        "probe_ms": 20,
        "probe_offsets_ms": (0,),
        "maximum_coarse_windows": 1,
        "source_probe_count": len(opportunities),
        "returned_probe_count": len(opportunities),
        "truncated_probe_count": 0,
        "opportunities": [item.model_dump(mode="json") for item in opportunities],
        "accounting": accounting.model_dump(mode="json"),
    }
    return StandardProbeScheduleV3.model_validate(
        {
            **values,
            "schedule_digest": canonical_digest(
                {
                    "schema_version": 3,
                    "algorithm_version": "standard-native-probe-schedule-v3",
                    **values,
                }
            ),
        }
    )
