from __future__ import annotations

import ast
import hashlib
import inspect
from collections.abc import Iterable
from dataclasses import replace

import pytest

from leo.analysis.standard import native_stateful
from leo.analysis.standard.configuration import resolve_receiver_standard_sample_rate
from leo.analysis.standard.native_runner import build_standard_native_probe_schedule
from leo.analysis.standard.native_stateful import (
    NativeSegmentExecutionDisposition,
    StandardNativeStatefulRunner,
    _persist_stateful_segment,
    _persist_unavailable_stateful_segment,
    build_standard_native_stateful_path,
    build_standard_native_stateful_path_v2,
    build_unavailable_standard_native_stateful_path,
    build_unavailable_standard_native_stateful_path_v2,
)
from leo.analysis.standard.runner import ReceiverStandardConfig
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import PilotProbeDetection
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.standard_native_stateful import (
    NativeStatefulSegmentDispositionV1,
    NativeStatefulSegmentV1,
    StandardNativeStatefulPathV1,
)
from leo.contracts.standard_native_stateful_v2 import StandardNativeStatefulPathV2
from leo.contracts.standard_pipeline import StandardPathInputBindV4
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import ContinuitySegmentV1, ValidityInventoryV1
from leo.domain.iq import IqBlock
from leo.pipeline.validity import DeviceIqSpan, WindowClassification

_RATE = 3_000_000
_GAP = 10
_TERMINAL_GAP = 5

_V1_AST_DIGESTS = {
    NativeStatefulSegmentDispositionV1: (
        "4a02ab82040800915b701ffaa3169065d9b2ab15e6b3b4a64b3bbb299fdc3012"
    ),
    NativeStatefulSegmentV1: "a9453a14b82bf2e92f25c7d20825a7202a8b795834adf85dcd9265d6dab59426",
    StandardNativeStatefulPathV1: (
        "e8cbbcea550cf39a4a55321ad79e45a7e36bbc2fdbce4efb9ea2f391fc0c63ef"
    ),
    build_standard_native_stateful_path: (
        "442cb9795303b8ca0a1ea6f68b1538d75e3522688e73850552dd4b324edc4990"
    ),
    build_unavailable_standard_native_stateful_path: (
        "7441411fbee52159b82847ef026865e197fdf11700a6bad2f65f357045f740e6"
    ),
    _persist_stateful_segment: "5a6a9f20eb486a25722cb5851c2ae34571a37b44d79f71e139825571e4539385",
    _persist_unavailable_stateful_segment: (
        "95b274bc3a19583a901b127859eae2beda1a1e923bc5f6e955bbde7481bf5f7a"
    ),
}


def test_published_stateful_v1_ast_is_frozen() -> None:
    for symbol, expected_digest in _V1_AST_DIGESTS.items():
        node = ast.parse(inspect.getsource(symbol)).body[0]
        encoded = ast.dump(node, include_attributes=False).encode()
        assert hashlib.sha256(encoded).hexdigest() == expected_digest


def _rate_config(
    sample_rate_hz: int = _RATE,
    config: ReceiverStandardConfig | None = None,
) -> ReceiverStandardConfig:
    return resolve_receiver_standard_sample_rate(
        config or ReceiverStandardConfig(),
        sample_rate_hz=sample_rate_hz,
    )


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

    def empty_scan(iq, config, *, edge, primary_qam_detection_observer=None):
        del primary_qam_detection_observer
        assert edge is StarlinkEdge.LOWER
        assert config.maximum_outer_windows == 1
        seen.append(iq)
        return ()

    monkeypatch.setattr(native_stateful, "scan_pilot_detections", empty_scan)

    result = StandardNativeStatefulRunner(_rate_config()).run(
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


def test_stateful_execution_and_publication_reject_unresolved_rate_config() -> None:
    inventory = _inventory()
    binding = _binding(inventory)
    unresolved = ReceiverStandardConfig()

    with pytest.raises(ValueError, match="not resolved"):
        StandardNativeStatefulRunner(unresolved).run(
            _Reader(inventory),
            binding,
            edge=StarlinkEdge.LOWER,
        )
    with pytest.raises(ValueError, match="not resolved"):
        build_unavailable_standard_native_stateful_path_v2(
            binding,
            unresolved,
            edge=StarlinkEdge.LOWER,
        )


def test_outer_window_budget_is_global_not_restarted_per_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = _inventory()
    reader = _Reader(inventory)
    seen: list[int] = []

    def empty_scan(iq, config, *, edge, primary_qam_detection_observer=None):
        del primary_qam_detection_observer
        del edge
        seen.append(iq.continuity_segment_index)
        assert config.maximum_outer_windows == 1
        return ()

    monkeypatch.setattr(native_stateful, "scan_pilot_detections", empty_scan)
    base = _rate_config()
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

    runner = StandardNativeStatefulRunner(
        _rate_config(),
        segment_executor=abort_second,
    )
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

    config = _rate_config()
    shifted_local_result = StandardNativeStatefulRunner(config).run(
        _Reader(inventory),
        binding,
        edge=StarlinkEdge.LOWER,
    )
    with pytest.raises(ValueError, match="not publishable"):
        build_standard_native_stateful_path(
            shifted_local_result,
            binding,
            config,
            edge=StarlinkEdge.LOWER,
        )
    with pytest.raises(ValueError, match="global schedule proof"):
        build_standard_native_stateful_path_v2(
            shifted_local_result,
            binding,
            config,
            edge=StarlinkEdge.LOWER,
        )

    product = build_unavailable_standard_native_stateful_path(
        binding,
        config,
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


def test_gapped_stateful_uses_exact_global_probes_and_resets_fits_per_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.analysis.test_standard_native_observability import (
        _binding as gap_binding,
    )
    from tests.analysis.test_standard_native_observability import (
        _inventory as gap_inventory,
    )
    from tests.analysis.test_standard_native_observability import (
        _Reader as GapReader,
    )

    inventory = gap_inventory()
    binding = gap_binding(inventory)
    reader = GapReader(inventory)
    config = _rate_config(reader.sample_rate_hz)
    schedule = build_standard_native_probe_schedule(
        reader,
        binding,
        subwindow_ms=config.feedback.subwindow_ms,
        probe_ms=config.feedback.probe_ms,
        probe_offsets_ms=config.feedback.probe_offsets_ms,
        maximum_coarse_windows=config.feedback.maximum_outer_windows,
    )
    detected_mappings: list[tuple[int, int, int, int]] = []

    def no_result_probe(item, feedback, edge):
        assert edge is StarlinkEdge.LOWER
        assert feedback.probe_ms == 20
        detected_mappings.append(
            (
                item.continuity_segment_index,
                item.global_device_sample_start,
                item.segment_local_sample_start,
                item.iq.global_device_sample_start,
            )
        )
        return PilotProbeDetection(
            NumericalStatus.NO_RESULT,
            item.segment_local_sample_start,
            item.segment_local_sample_start / item.iq.sample_rate_hz,
            None,
            None,
            (),
            None,
            None,
            "test explicit global probe",
        )

    fit_calls: list[tuple[int, ...]] = []
    original_fit = native_stateful.fit_residual_hough_pilot_trajectories

    def recording_fit(detections, feedback, segmentation):
        fit_calls.append(tuple(item.sample_start for item in detections))
        return original_fit(detections, feedback, segmentation)

    monkeypatch.setattr(
        native_stateful,
        "fit_residual_hough_pilot_trajectories",
        recording_fit,
    )
    result = StandardNativeStatefulRunner(
        config,
        probe_detector=no_result_probe,
    ).run_global_probe_schedule(
        reader,
        binding,
        schedule,
        edge=StarlinkEdge.LOWER,
    )
    product = build_standard_native_stateful_path_v2(
        result,
        binding,
        config,
        edge=StarlinkEdge.LOWER,
        schedule=schedule,
    )

    valid = tuple(item for item in schedule.opportunities if item.validity.disposition == "valid")
    segments = {item.segment_index: item for item in inventory.segments}
    expected = tuple(
        (
            item.validity.continuity_segment_index,
            item.probe.sample_start,
            item.probe.sample_start
            - segments[item.validity.continuity_segment_index].device_sample_start,
            item.probe.sample_start,
        )
        for item in valid
        if item.validity.continuity_segment_index is not None
    )
    expected_by_segment = tuple(
        tuple(
            local
            for segment_index, _global, local, _reader_global in expected
            if segment_index == i
        )
        for i in range(len(inventory.segments))
    )

    assert schedule.accounting.valid_count == 39
    assert schedule.accounting.gap_excluded_count == 1
    assert tuple(sorted(detected_mappings)) == tuple(sorted(expected))
    assert expected_by_segment[0] == (0,)
    assert expected_by_segment[1][0] == 15_000
    assert fit_calls == [expected_by_segment[0], expected_by_segment[1]]
    assert all(start < inventory.segments[0].observed_sample_count for start in fit_calls[0])
    assert all(start < inventory.segments[1].observed_sample_count for start in fit_calls[1])
    assert product.stateful_science_status == "partial_coverage"
    assert StandardNativeStatefulPathV2.model_validate(product.model_dump(mode="json")) == product
    assert product.analyzed_outer_window_count == 2
    assert tuple(item.disposition.value for item in product.segments) == (
        "analyzed",
        "analyzed",
    )
    assert tuple(item.local_science is not None for item in product.segments) == (True, True)
    assert product.segments[1].local_science is not None
    assert product.segments[1].local_science.detections[0].sample_start == 15_000
    assert (
        product.segments[1].global_device_sample_start
        + product.segments[1].local_science.detections[0].sample_start
        == 125_000
    )


@pytest.mark.parametrize("sample_rate_hz", (2_500_000, 3_000_000, 5_000_000))
def test_global_probe_geometry_marks_short_segment_without_valid_opportunity(
    sample_rate_hz: int,
) -> None:
    from tests.analysis.test_standard_native_rate_equivalence import (
        _binding as rate_binding,
    )
    from tests.analysis.test_standard_native_rate_equivalence import (
        _inventory as rate_inventory,
    )
    from tests.analysis.test_standard_native_rate_equivalence import (
        _ToneSegmentReader,
    )

    gap_start = sample_rate_hz // 100
    gap_count = sample_rate_hz // 1_000
    second_start = gap_start + gap_count
    terminal_gap_count = 1
    second_stop = sample_rate_hz - terminal_gap_count
    observed_sample_count = sample_rate_hz - gap_count - terminal_gap_count
    lossless_inventory = rate_inventory(sample_rate_hz)
    inventory = ValidityInventoryV1.model_validate(
        {
            "stream_id": "stream-0",
            "timeline_sha256": canonical_digest({"timeline": "gapped", "rate": sample_rate_hz}),
            "gap_map_content_digest": canonical_digest(
                {"gap-map": "gapped", "rate": sample_rate_hz}
            ),
            "first_device_sample_counter": 100,
            "logical_sample_count": sample_rate_hz,
            "observed_sample_count": observed_sample_count,
            "missing_sample_count": gap_count + terminal_gap_count,
            "continuity_boundary_count": 2,
            "runs": (
                {
                    "run_index": 0,
                    "device_sample_start": 0,
                    "sample_count": gap_start,
                    "content_kind": "observed",
                    "stored_sample_start": 0,
                    "continuity_segment_index": 0,
                },
                {
                    "run_index": 1,
                    "device_sample_start": gap_start,
                    "sample_count": gap_count,
                    "content_kind": "zero_fill",
                },
                {
                    "run_index": 2,
                    "device_sample_start": second_start,
                    "sample_count": second_stop - second_start,
                    "content_kind": "observed",
                    "stored_sample_start": gap_start,
                    "continuity_segment_index": 1,
                },
                {
                    "run_index": 3,
                    "device_sample_start": second_stop,
                    "sample_count": terminal_gap_count,
                    "content_kind": "zero_fill",
                },
            ),
            "segments": (
                {
                    "segment_index": 0,
                    "device_sample_start": 0,
                    "device_sample_stop": gap_start,
                    "stored_sample_start": 0,
                    "stored_sample_stop": gap_start,
                },
                {
                    "segment_index": 1,
                    "device_sample_start": second_start,
                    "device_sample_stop": second_stop,
                    "stored_sample_start": gap_start,
                    "stored_sample_stop": observed_sample_count,
                    "preceding_missing_sample_count": gap_count,
                    "preceding_boundary_reason": "counter_gap",
                    "preceding_boundary_header_sha256": canonical_digest(
                        {"header": sample_rate_hz}
                    ),
                },
                {
                    "segment_index": 2,
                    "device_sample_start": sample_rate_hz,
                    "device_sample_stop": sample_rate_hz,
                    "stored_sample_start": observed_sample_count,
                    "stored_sample_stop": observed_sample_count,
                    "preceding_missing_sample_count": terminal_gap_count,
                    "preceding_boundary_reason": "terminal_counter_gap",
                    "preceding_boundary_header_sha256": canonical_digest(
                        {"terminal-header": sample_rate_hz}
                    ),
                },
            ),
        }
    )
    base = rate_binding(sample_rate_hz, lossless_inventory)
    values = base.model_dump(mode="json", exclude={"binding_digest"})
    values.update(
        {
            "observed_sample_count": inventory.observed_sample_count,
            "missing_sample_count": inventory.missing_sample_count,
            "observed_iq_digest": canonical_digest({"observed-iq": sample_rate_hz}),
            "logical_iq_digest": canonical_digest({"logical-iq": sample_rate_hz}),
            "timeline_sha256": inventory.timeline_sha256,
            "gap_map_sha256": canonical_digest({"gap-map-file": sample_rate_hz}),
            "gap_map_content_digest": inventory.gap_map_content_digest,
            "validity_inventory_sha256": inventory.inventory_digest,
            "validity_inventory": inventory.model_dump(mode="json"),
        }
    )
    binding = StandardPathInputBindV4.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )

    class _GappedToneReader:
        center_frequency_hz = 959_687_500
        receiver_ids = (0,)

        def __init__(self) -> None:
            self.sample_rate_hz = sample_rate_hz
            self.sample_count = inventory.logical_sample_count
            self.observed_sample_count = inventory.observed_sample_count
            self.missing_sample_count = inventory.missing_sample_count
            self.validity_inventory = inventory

        def segment_readers(self):
            return tuple(
                _ToneSegmentReader(sample_rate_hz, segment)
                for segment in inventory.segments
                if segment.observed_sample_count
            )

        def classify_window(self, device_sample_start: int, sample_count: int):
            from leo.pipeline.validity import WindowClassification, WindowValidity

            stop = device_sample_start + sample_count
            if device_sample_start < 0 or stop > sample_rate_hz:
                return WindowClassification(
                    device_sample_start=device_sample_start,
                    sample_count=sample_count,
                    status=WindowValidity.OUTSIDE_SPAN,
                )
            overlap = max(
                0,
                min(stop, second_start) - max(device_sample_start, gap_start),
            )
            if overlap:
                return WindowClassification(
                    device_sample_start=device_sample_start,
                    sample_count=sample_count,
                    status=WindowValidity.GAP_OVERLAP,
                    missing_sample_count=overlap,
                    crossed_segment_indexes=(
                        (1,) if device_sample_start < second_start < stop else ()
                    ),
                )
            return WindowClassification(
                device_sample_start=device_sample_start,
                sample_count=sample_count,
                status=WindowValidity.VALID,
                continuity_segment_index=(0 if stop <= gap_start else 1),
            )

    reader = _GappedToneReader()
    config = _rate_config(sample_rate_hz)
    schedule = build_standard_native_probe_schedule(
        reader,  # type: ignore[arg-type]
        binding,
        subwindow_ms=config.feedback.subwindow_ms,
        probe_ms=config.feedback.probe_ms,
        probe_offsets_ms=config.feedback.probe_offsets_ms,
        maximum_coarse_windows=config.feedback.maximum_outer_windows,
    )

    def no_result_probe(item, feedback, edge):
        del feedback, edge
        return PilotProbeDetection(
            NumericalStatus.NO_RESULT,
            item.segment_local_sample_start,
            item.segment_local_sample_start / sample_rate_hz,
            None,
            None,
            (),
            None,
            None,
            "test rate-native explicit global probe",
        )

    result = StandardNativeStatefulRunner(
        config,
        probe_detector=no_result_probe,
    ).run_global_probe_schedule(
        reader,  # type: ignore[arg-type]
        binding,
        schedule,
        edge=StarlinkEdge.LOWER,
    )
    product = build_standard_native_stateful_path_v2(
        result,
        binding,
        config,
        edge=StarlinkEdge.LOWER,
        schedule=schedule,
    )

    assert schedule.accounting.gap_excluded_count == 1
    assert tuple(item.disposition.value for item in product.segments) == (
        "no_valid_global_probe",
        "analyzed",
        "empty_terminal",
    )
    assert product.segments[0].local_science is None
    assert product.segments[1].local_science is not None
    assert product.segments[1].local_science.detections[0].sample_start == (
        sample_rate_hz * 14 // 1_000
    )
    assert product.segments[2].local_science is None
    assert product.segments[2].global_device_sample_stop == sample_rate_hz
    assert product.source.sample_rate_hz == sample_rate_hz


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
    config = _rate_config(sample_rate_hz)

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
    assert (
        sha256_digest(canonical_json_bytes(product.model_dump(mode="json")))
        == {
            2_500_000: "sha256:150c6b64bf3a0f5853eb51b581020ba11950aee791b72292b8776c598b1d4a2e",
            3_000_000: "sha256:be54fc7349bfd85f44632abb828feeb7719c30a3826af53679a03ca5d858cc08",
            5_000_000: "sha256:fdc5a90199b3ccc43fc410cc5f2b6d436eb744f359e0d40441fa14cbef274c32",
        }[sample_rate_hz]
    )
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
