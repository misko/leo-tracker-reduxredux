from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

import pytest

from leo.analysis.standard import native_stateful
from leo.analysis.standard.native_stateful import (
    NativeSegmentExecutionDisposition,
    StandardNativeStatefulRunner,
    build_standard_native_stateful_path,
    build_unavailable_standard_native_stateful_path,
)
from leo.analysis.standard.runner import ReceiverStandardConfig
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native_stateful import StandardNativeStatefulPathV1
from leo.contracts.standard_pipeline import StandardPathInputBindV4
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import ContinuitySegmentV1, ValidityInventoryV1
from leo.domain.iq import IqBlock
from leo.pipeline.validity import DeviceIqSpan, WindowClassification

_RATE = 3_000_000
_GAP = 10
_TERMINAL_GAP = 5


class _SegmentReader:
    def __init__(self, segment: ContinuitySegmentV1) -> None:
        self.segment = segment
        self.read_attempted = False

    @property
    def continuity_segment_index(self) -> int:
        return self.segment.segment_index

    @property
    def global_device_sample_start(self) -> int:
        return self.segment.device_sample_start

    @property
    def sample_rate_hz(self) -> int:
        return _RATE

    @property
    def center_frequency_hz(self) -> int:
        return 959_687_500

    @property
    def sample_count(self) -> int:
        return self.segment.observed_sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return (0,)

    def to_global_device_sample(self, local_sample: int) -> int:
        return self.segment.device_sample_start + local_sample

    def iter_blocks(self, *, block_samples: int) -> Iterable[IqBlock]:
        del block_samples
        self.read_attempted = True
        raise AssertionError("empty stateful products must not reread IQ")
        yield


class _Reader:
    def __init__(self, inventory: ValidityInventoryV1) -> None:
        self.validity_inventory = inventory
        self.sample_rate_hz = _RATE
        self.center_frequency_hz = 959_687_500
        self.sample_count = inventory.logical_sample_count
        self.observed_sample_count = inventory.observed_sample_count
        self.missing_sample_count = inventory.missing_sample_count
        self.receiver_ids = (0,)
        self.readers = tuple(
            _SegmentReader(segment)
            for segment in inventory.segments
            if segment.observed_sample_count
        )

    def segment_readers(self) -> tuple[_SegmentReader, ...]:
        return self.readers

    def read_device_span(self, device_sample_start: int, sample_count: int) -> DeviceIqSpan:
        del device_sample_start, sample_count
        raise AssertionError("stateful orchestration must use segment readers")

    def iter_masked_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]:
        del block_samples
        raise AssertionError("stateful orchestration must use segment readers")
        yield

    def iter_valid_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]:
        del block_samples
        raise AssertionError("stateful orchestration must use segment readers")
        yield

    def classify_window(self, device_sample_start: int, sample_count: int) -> WindowClassification:
        del device_sample_start, sample_count
        raise AssertionError("stateful orchestration must use segment readers")

    def close(self) -> None:
        pass


def _inventory() -> ValidityInventoryV1:
    first_stop = _RATE
    second_start = first_stop + _GAP
    second_stop = second_start + _RATE
    terminal_stop = second_stop + _TERMINAL_GAP
    header_a = canonical_digest({"header": "a"})
    header_b = canonical_digest({"header": "b"})
    return ValidityInventoryV1.model_validate(
        {
            "stream_id": "stream-0",
            "timeline_sha256": canonical_digest({"timeline": 1}),
            "gap_map_content_digest": canonical_digest({"gap-map": 1}),
            "first_device_sample_counter": 100,
            "logical_sample_count": terminal_stop,
            "observed_sample_count": 2 * _RATE,
            "missing_sample_count": _GAP + _TERMINAL_GAP,
            "continuity_boundary_count": 2,
            "runs": (
                {
                    "run_index": 0,
                    "device_sample_start": 0,
                    "sample_count": _RATE,
                    "content_kind": "observed",
                    "stored_sample_start": 0,
                    "continuity_segment_index": 0,
                },
                {
                    "run_index": 1,
                    "device_sample_start": first_stop,
                    "sample_count": _GAP,
                    "content_kind": "zero_fill",
                },
                {
                    "run_index": 2,
                    "device_sample_start": second_start,
                    "sample_count": _RATE,
                    "content_kind": "observed",
                    "stored_sample_start": _RATE,
                    "continuity_segment_index": 1,
                },
                {
                    "run_index": 3,
                    "device_sample_start": second_stop,
                    "sample_count": _TERMINAL_GAP,
                    "content_kind": "zero_fill",
                },
            ),
            "segments": (
                {
                    "segment_index": 0,
                    "device_sample_start": 0,
                    "device_sample_stop": first_stop,
                    "stored_sample_start": 0,
                    "stored_sample_stop": _RATE,
                },
                {
                    "segment_index": 1,
                    "device_sample_start": second_start,
                    "device_sample_stop": second_stop,
                    "stored_sample_start": _RATE,
                    "stored_sample_stop": 2 * _RATE,
                    "preceding_missing_sample_count": _GAP,
                    "preceding_boundary_reason": "counter_gap",
                    "preceding_boundary_header_sha256": header_a,
                },
                {
                    "segment_index": 2,
                    "device_sample_start": terminal_stop,
                    "device_sample_stop": terminal_stop,
                    "stored_sample_start": 2 * _RATE,
                    "stored_sample_stop": 2 * _RATE,
                    "preceding_missing_sample_count": _TERMINAL_GAP,
                    "preceding_boundary_reason": "terminal_counter_gap",
                    "preceding_boundary_header_sha256": header_b,
                },
            ),
        }
    )


def _binding(inventory: ValidityInventoryV1) -> StandardPathInputBindV4:
    return StandardPathInputBindV4.model_construct(
        session_id="session-0",
        stream_id="stream-0",
        radio_id="radio-0",
        receiver_id=0,
        manifest_digest=canonical_digest({"manifest": 1}),
        synchronization_inventory_digest=canonical_digest({"sync": 1}),
        sample_rate_hz=_RATE,
        tuned_center_frequency_hz=959_687_500,
        logical_sample_count=inventory.logical_sample_count,
        observed_sample_count=inventory.observed_sample_count,
        missing_sample_count=inventory.missing_sample_count,
        starlink_edge=StarlinkEdge.LOWER,
        timing={
            "schema_version": 1,
            "first_estimate_utc_ns": 1_000_000_000,
            "first_earliest_utc_ns": 999_999_900,
            "first_latest_utc_ns": 1_000_000_100,
            "last_estimate_utc_ns": 3_000_000_000,
            "last_earliest_utc_ns": 2_999_999_900,
            "last_latest_utc_ns": 3_000_000_100,
        },
        validity_inventory=inventory,
        binding_digest=canonical_digest({"binding": 1}),
    )


def test_stateful_chain_resets_at_every_segment_and_retains_global_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = _inventory()
    reader = _Reader(inventory)
    seen: list[_SegmentReader] = []

    def empty_scan(iq, config, *, edge):
        assert edge is StarlinkEdge.LOWER
        assert config.maximum_outer_windows == 1
        seen.append(iq)
        return ()

    monkeypatch.setattr(native_stateful, "scan_pilot_detections", empty_scan)

    result = StandardNativeStatefulRunner().run(
        reader,
        _binding(inventory),
        edge=StarlinkEdge.LOWER,
    )

    assert seen == list(reader.readers)
    assert seen[0] is not seen[1]
    assert [item.sample_count for item in seen] == [_RATE, _RATE]
    assert result.analyzed_outer_window_count == 2
    assert tuple(item.segment for item in result.segments) == inventory.segments
    assert tuple(item.disposition for item in result.segments) == (
        NativeSegmentExecutionDisposition.ANALYZED,
        NativeSegmentExecutionDisposition.ANALYZED,
        NativeSegmentExecutionDisposition.EMPTY_TERMINAL,
    )
    assert result.segments[1].device_sample_start == _RATE + _GAP
    assert result.segments[1].to_global_device_sample(25) == _RATE + _GAP + 25
    assert result.segments[1].to_global_time_s(0.25, sample_rate_hz=_RATE) == pytest.approx(
        (_RATE + _GAP) / _RATE + 0.25
    )
    assert result.segments[2].device_sample_stop == inventory.logical_sample_count
    assert result.segments[2].local_science is None
    assert not any(item.read_attempted for item in reader.readers)
    for segment_result in result.segments[:2]:
        science = segment_result.local_science
        assert science is not None
        assert science.detections == ()
        assert science.residual_hough_representatives == ()
        assert science.conditioned_hough_replay == ()
        assert science.cfo_alias_map.status == "no_result"
        assert science.dealiased_trajectory_bank.status == "no_result"
        assert science.final_trajectory_bank.status == "no_result"
        assert science.kalman_tracking.status == "no_result"
        assert science.pilot_doppler_segments.status == "no_result"


def test_outer_window_budget_is_global_not_restarted_per_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = _inventory()
    reader = _Reader(inventory)
    seen: list[int] = []

    def empty_scan(iq, config, *, edge):
        del edge
        seen.append(iq.continuity_segment_index)
        assert config.maximum_outer_windows == 1
        return ()

    monkeypatch.setattr(native_stateful, "scan_pilot_detections", empty_scan)
    base = ReceiverStandardConfig()
    config = replace(base, feedback=replace(base.feedback, maximum_outer_windows=1))

    result = StandardNativeStatefulRunner(config).run(
        reader,
        _binding(inventory),
        edge=StarlinkEdge.LOWER,
    )

    assert seen == [0]
    assert result.analyzed_outer_window_count == 1
    assert result.segments[1].disposition is (
        NativeSegmentExecutionDisposition.OUTER_WINDOW_BUDGET_EXHAUSTED
    )
    assert result.segments[1].local_science is None


class _CampaignAbort(BaseException):
    pass


def test_base_exception_poison_discards_partial_segment_campaign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = _inventory()
    reader = _Reader(inventory)
    calls: list[int] = []
    monkeypatch.setattr(native_stateful, "scan_pilot_detections", lambda *args, **kwargs: ())

    def abort_second(segment, binding, config, edge, outer_window_limit):
        calls.append(segment.continuity_segment_index)
        if segment.continuity_segment_index == 1:
            raise _CampaignAbort
        return native_stateful._run_segment_local_science(
            segment,
            binding,
            config,
            edge,
            outer_window_limit,
        )

    runner = StandardNativeStatefulRunner(segment_executor=abort_second)
    with pytest.raises(_CampaignAbort):
        runner.run(reader, _binding(inventory), edge=StarlinkEdge.LOWER)

    assert calls == [0, 1]
    assert runner.poisoned
    with pytest.raises(RuntimeError, match="poisoned"):
        runner.run(reader, _binding(inventory), edge=StarlinkEdge.LOWER)
    assert calls == [0, 1]


def test_gapped_stateful_product_closes_segments_without_false_local_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = _inventory()
    binding = _binding(inventory)
    monkeypatch.setattr(native_stateful, "scan_pilot_detections", lambda *args, **kwargs: ())

    shifted_local_result = StandardNativeStatefulRunner().run(
        _Reader(inventory),
        binding,
        edge=StarlinkEdge.LOWER,
    )
    with pytest.raises(ValueError, match="not publishable"):
        build_standard_native_stateful_path(
            shifted_local_result,
            binding,
            ReceiverStandardConfig(),
            edge=StarlinkEdge.LOWER,
        )

    product = build_unavailable_standard_native_stateful_path(
        binding,
        ReceiverStandardConfig(),
        edge=StarlinkEdge.LOWER,
    )

    assert product.stateful_science_status == "unavailable_global_schedule"
    assert product.analyzed_outer_window_count == 0
    assert tuple(item.continuity_segment for item in product.segments) == inventory.segments
    assert tuple(item.disposition.value for item in product.segments) == (
        "global_schedule_unavailable",
        "global_schedule_unavailable",
        "empty_terminal",
    )
    assert all(item.local_science is None for item in product.segments)
    assert product.segments[1].global_device_sample_start == _RATE + _GAP
    assert product.segments[-1].global_device_sample_stop == inventory.logical_sample_count


@pytest.mark.parametrize("sample_rate_hz", (2_500_000, 3_000_000, 5_000_000))
def test_lossless_stateful_product_is_typed_and_rate_native(
    sample_rate_hz: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.analysis.test_standard_native_rate_equivalence import (
        _binding as rate_binding,
    )
    from tests.analysis.test_standard_native_rate_equivalence import (
        _inventory as rate_inventory,
    )
    from tests.analysis.test_standard_native_rate_equivalence import (
        _ToneReader,
    )

    inventory = rate_inventory(sample_rate_hz)
    binding = rate_binding(sample_rate_hz, inventory)
    monkeypatch.setattr(native_stateful, "scan_pilot_detections", lambda *args, **kwargs: ())
    config = ReceiverStandardConfig()

    result = StandardNativeStatefulRunner(config).run(
        _ToneReader(sample_rate_hz, inventory),
        binding,
        edge=binding.starlink_edge,
    )
    product = build_standard_native_stateful_path(
        result,
        binding,
        config,
        edge=binding.starlink_edge,
    )
    round_tripped = StandardNativeStatefulPathV1.model_validate(product.model_dump(mode="json"))

    assert round_tripped == product
    assert product.source.sample_rate_hz == sample_rate_hz
    assert product.stateful_science_status == "complete"
    assert product.analyzed_outer_window_count == 1
    assert len(product.segments) == 1
    segment = product.segments[0]
    assert segment.global_device_sample_start == 0
    assert segment.global_device_sample_stop == sample_rate_hz
    assert segment.disposition.value == "analyzed"
    science = segment.local_science
    assert science is not None
    assert science.coordinate_basis == "segment-local-device-axis-v1"
    assert science.detections == ()
    assert science.cfo_alias_map.status == "no_result"
    assert science.final_trajectory_bank.status == "no_result"
    assert science.kalman_tracking.status == "no_result"
    assert science.pilot_doppler_segments.status == "no_result"
