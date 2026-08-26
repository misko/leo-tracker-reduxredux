from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pytest

from leo.analysis.standard import native_stateful
from leo.analysis.standard.native_analyzers import (
    PathStandardNativeEvidenceAnalyzer,
    production_standard_native_evidence_configuration,
    production_standard_native_evidence_registry,
)
from leo.analysis.standard.native_runner import run_standard_native_observability
from leo.analysis.standard.native_stateful import StandardNativeStatefulRunner
from leo.analysis.standard.native_waterfall import measure_standard_native_waterfall
from leo.analysis.waterfall import WaterfallConfig
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.radio import IqBlockMetadataV1
from leo.contracts.standard_native_stateful import StandardNativeStatefulPathV1
from leo.contracts.standard_pipeline import StandardPathInputBindV4
from leo.contracts.validity import ContinuitySegmentV1, ValidityInventoryV1
from leo.domain.iq import IqBlock
from leo.pipeline import AnalysisContext, ProductSpec, PublishedProduct, ScopeIdentityV1
from leo.pipeline.validity import (
    DeviceIqSpan,
    WindowClassification,
    WindowValidity,
)

_RATE = 2_500_000
_GAP_START = 100_000
_GAP_COUNT = 10_000


def _metadata(sample_start: int, sample_count: int) -> IqBlockMetadataV1:
    return IqBlockMetadataV1(
        radio_id="radio-0",
        receiver_ids=(0,),
        sample_count=sample_count,
        session_sample_start=sample_start,
        host_request_utc_ns={"lower_ns": 1, "upper_ns": 1},
        host_request_monotonic_ns={"lower_ns": 1, "upper_ns": 1},
    )


class _SegmentReader:
    def __init__(self, segment: ContinuitySegmentV1) -> None:
        self.segment = segment

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
        for start in range(0, self.sample_count, block_samples):
            count = min(block_samples, self.sample_count - start)
            yield IqBlock(
                samples=np.full((count, 1, 2), 7, dtype="<i2"),
                metadata=_metadata(start, count),
            )


class _Reader:
    def __init__(self, inventory: ValidityInventoryV1) -> None:
        self.validity_inventory = inventory

    sample_rate_hz = _RATE
    center_frequency_hz = 959_687_500
    sample_count = _RATE
    observed_sample_count = _RATE - _GAP_COUNT
    missing_sample_count = _GAP_COUNT
    receiver_ids = (0,)

    def segment_readers(self) -> tuple[_SegmentReader, ...]:
        return tuple(_SegmentReader(item) for item in self.validity_inventory.segments)

    def iter_valid_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]:
        for segment in self.validity_inventory.segments:
            for start in range(
                segment.device_sample_start,
                segment.device_sample_stop,
                block_samples,
            ):
                count = min(block_samples, segment.device_sample_stop - start)
                yield DeviceIqSpan(
                    samples=np.full((count, 1, 2), 7, dtype="<i2"),
                    valid_samples=np.ones(count, dtype=np.bool_),
                    continuity_segment_ids=np.full(count, segment.segment_index, dtype=np.int32),
                    device_sample_start=start,
                    receiver_ids=(0,),
                )

    def iter_masked_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]:
        for start in range(0, self.sample_count, block_samples):
            count = min(block_samples, self.sample_count - start)
            yield self.read_device_span(start, count)

    def read_device_span(self, device_sample_start: int, sample_count: int) -> DeviceIqSpan:
        values = np.full((sample_count, 1, 2), 7, dtype="<i2")
        valid = np.ones(sample_count, dtype=np.bool_)
        segment_ids = np.full(sample_count, 0, dtype=np.int32)
        indexes = np.arange(device_sample_start, device_sample_start + sample_count)
        gap = (indexes >= _GAP_START) & (indexes < _GAP_START + _GAP_COUNT)
        second = indexes >= _GAP_START + _GAP_COUNT
        values[gap] = 0
        valid[gap] = False
        segment_ids[gap] = -1
        segment_ids[second] = 1
        return DeviceIqSpan(
            samples=values,
            valid_samples=valid,
            continuity_segment_ids=segment_ids,
            device_sample_start=device_sample_start,
            receiver_ids=(0,),
        )

    def classify_window(self, device_sample_start: int, sample_count: int) -> WindowClassification:
        stop = device_sample_start + sample_count
        if device_sample_start < 0 or stop > self.sample_count:
            return WindowClassification(
                device_sample_start=device_sample_start,
                sample_count=sample_count,
                status=WindowValidity.OUTSIDE_SPAN,
            )
        overlap = max(
            0,
            min(stop, _GAP_START + _GAP_COUNT) - max(device_sample_start, _GAP_START),
        )
        if overlap:
            return WindowClassification(
                device_sample_start=device_sample_start,
                sample_count=sample_count,
                status=WindowValidity.GAP_OVERLAP,
                missing_sample_count=overlap,
                crossed_segment_indexes=(
                    (1,) if device_sample_start < _GAP_START + _GAP_COUNT < stop else ()
                ),
            )
        segment = 0 if stop <= _GAP_START else 1
        return WindowClassification(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            status=WindowValidity.VALID,
            continuity_segment_index=segment,
        )

    def close(self) -> None:
        pass


def _inventory() -> ValidityInventoryV1:
    header = canonical_digest({"header": 1})
    timeline = canonical_digest({"timeline": 1})
    gap_map = canonical_digest({"gap-map": 1})
    return ValidityInventoryV1(
        stream_id="stream-0",
        timeline_sha256=timeline,
        gap_map_content_digest=gap_map,
        first_device_sample_counter=100,
        logical_sample_count=_RATE,
        observed_sample_count=_RATE - _GAP_COUNT,
        missing_sample_count=_GAP_COUNT,
        continuity_boundary_count=1,
        runs=(
            {
                "run_index": 0,
                "device_sample_start": 0,
                "sample_count": _GAP_START,
                "content_kind": "observed",
                "stored_sample_start": 0,
                "continuity_segment_index": 0,
            },
            {
                "run_index": 1,
                "device_sample_start": _GAP_START,
                "sample_count": _GAP_COUNT,
                "content_kind": "zero_fill",
            },
            {
                "run_index": 2,
                "device_sample_start": _GAP_START + _GAP_COUNT,
                "sample_count": _RATE - _GAP_START - _GAP_COUNT,
                "content_kind": "observed",
                "stored_sample_start": _GAP_START,
                "continuity_segment_index": 1,
            },
        ),
        segments=(
            {
                "segment_index": 0,
                "device_sample_start": 0,
                "device_sample_stop": _GAP_START,
                "stored_sample_start": 0,
                "stored_sample_stop": _GAP_START,
            },
            {
                "segment_index": 1,
                "device_sample_start": _GAP_START + _GAP_COUNT,
                "device_sample_stop": _RATE,
                "stored_sample_start": _GAP_START,
                "stored_sample_stop": _RATE - _GAP_COUNT,
                "preceding_missing_sample_count": _GAP_COUNT,
                "preceding_boundary_reason": "counter_gap",
                "preceding_boundary_header_sha256": header,
            },
        ),
    )


def _binding(inventory: ValidityInventoryV1) -> StandardPathInputBindV4:
    return StandardPathInputBindV4.model_construct(
        session_id="session-1",
        stream_id="stream-0",
        radio_id="radio-0",
        receiver_id=0,
        manifest_digest=canonical_digest({"manifest": 1}),
        synchronization_inventory_digest=canonical_digest({"sync": 1}),
        sample_rate_hz=_RATE,
        tuned_center_frequency_hz=959_687_500,
        logical_sample_count=_RATE,
        observed_sample_count=_RATE - _GAP_COUNT,
        missing_sample_count=_GAP_COUNT,
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
        binding_digest=canonical_digest({"binding": 1}),
    )


def test_native_observability_excludes_gap_zeros_and_preserves_global_axis() -> None:
    inventory = _inventory()
    result = run_standard_native_observability(_Reader(inventory), _binding(inventory))

    assert result.schedule.accounting.scheduled_count == 40
    assert result.schedule.accounting.valid_count == 39
    assert result.schedule.accounting.gap_excluded_count == 1
    assert result.schedule.accounting.analyzed_count == 0
    excluded = tuple(
        item for item in result.schedule.opportunities if item.validity.disposition == "gap_overlap"
    )
    assert len(excluded) == 1
    assert excluded[0].probe.sample_start == 62_500
    assert excluded[0].validity.missing_sample_count == _GAP_COUNT
    assert excluded[0].validity.crossed_segment_indexes == (1,)

    quality = result.quality.receivers[0]
    assert quality.valid_sample_count == _RATE - _GAP_COUNT
    assert quality.energy_sum_ci16_squared == (_RATE - _GAP_COUNT) * 98
    assert (quality.minimum_i, quality.maximum_i, quality.minimum_q, quality.maximum_q) == (
        7,
        7,
        7,
        7,
    )
    assert result.quality.uncovered_region_count == 1

    power = result.power.timeline
    assert power.expected_sample_count == _RATE
    assert power.observed_sample_count == _RATE - _GAP_COUNT
    assert power.missing_sample_count == _GAP_COUNT
    assert power.timeline[0].observed_sample_count == _RATE - _GAP_COUNT
    assert power.timeline[0].mean_power_full_scale_squared == 98 / 32_768**2
    assert result.waterfall.waterfall.coverage.transformed_samples == (
        (_GAP_START // 1024) * 1024 + ((_RATE - _GAP_START - _GAP_COUNT) // 1024) * 1024
    )


class _BoundaryReader(_Reader):
    sample_count = 1_200
    observed_sample_count = 1_200
    missing_sample_count = 0


class _LosslessReader(_Reader):
    observed_sample_count = _RATE
    missing_sample_count = 0

    def classify_window(
        self,
        device_sample_start: int,
        sample_count: int,
    ) -> WindowClassification:
        return WindowClassification(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            status=WindowValidity.VALID,
            continuity_segment_index=0,
        )


def test_native_waterfall_resets_fft_carry_at_zero_length_continuity_boundary() -> None:
    header = canonical_digest({"overflow-header": 1})
    inventory = ValidityInventoryV1(
        stream_id="stream-0",
        timeline_sha256=canonical_digest({"timeline": "overflow"}),
        gap_map_content_digest=canonical_digest({"gap-map": "overflow"}),
        first_device_sample_counter=100,
        logical_sample_count=1_200,
        observed_sample_count=1_200,
        missing_sample_count=0,
        continuity_boundary_count=1,
        runs=(
            {
                "run_index": 0,
                "device_sample_start": 0,
                "sample_count": 600,
                "content_kind": "observed",
                "stored_sample_start": 0,
                "continuity_segment_index": 0,
            },
            {
                "run_index": 1,
                "device_sample_start": 600,
                "sample_count": 600,
                "content_kind": "observed",
                "stored_sample_start": 600,
                "continuity_segment_index": 1,
            },
        ),
        segments=(
            {
                "segment_index": 0,
                "device_sample_start": 0,
                "device_sample_stop": 600,
                "stored_sample_start": 0,
                "stored_sample_stop": 600,
            },
            {
                "segment_index": 1,
                "device_sample_start": 600,
                "device_sample_stop": 1_200,
                "stored_sample_start": 600,
                "stored_sample_stop": 1_200,
                "preceding_missing_sample_count": 0,
                "preceding_boundary_reason": "overflow_flag",
                "preceding_boundary_header_sha256": header,
            },
        ),
    )
    binding = StandardPathInputBindV4.model_construct(
        session_id="session-1",
        stream_id="stream-0",
        radio_id="radio-0",
        receiver_id=0,
        manifest_digest=canonical_digest({"manifest": "overflow"}),
        synchronization_inventory_digest=canonical_digest({"sync": "overflow"}),
        sample_rate_hz=_RATE,
        tuned_center_frequency_hz=959_687_500,
        logical_sample_count=1_200,
        observed_sample_count=1_200,
        missing_sample_count=0,
        timing={
            "schema_version": 1,
            "first_estimate_utc_ns": 1_000_000_000,
            "first_earliest_utc_ns": 999_999_900,
            "first_latest_utc_ns": 1_000_000_100,
            "last_estimate_utc_ns": 1_000_480_000,
            "last_earliest_utc_ns": 1_000_479_900,
            "last_latest_utc_ns": 1_000_480_100,
        },
        validity_inventory=inventory,
        binding_digest=canonical_digest({"binding": "overflow"}),
    )

    result = measure_standard_native_waterfall(
        _BoundaryReader(inventory),
        binding,
        WaterfallConfig(
            fft_samples=1024,
            frequency_bins=16,
            maximum_time_bins=4,
            block_samples=1024,
        ),
    )

    assert result.waterfall.coverage.observed_samples == 1_200
    assert result.waterfall.coverage.transformed_samples == 0
    assert result.waterfall.coverage.gap_count == 1


class _SubjectProducts:
    def __init__(self, binding: StandardPathInputBindV4) -> None:
        self._binding = binding

    def read_subject_binding(self) -> dict[str, Any]:
        return self._binding.model_dump(mode="json")


class _OutputSink:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, int], dict[str, Any]] = {}

    def publish_json(
        self,
        product: ProductSpec,
        document: dict[str, Any],
    ) -> PublishedProduct:
        payload = canonical_json_bytes(document)
        self.documents[(product.kind, product.schema_version)] = document
        return PublishedProduct(
            product=product,
            logical_uri=f"bulk://native/{product.kind}/v{product.schema_version}.json",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )


def test_native_evidence_analyzer_executes_only_truthful_products() -> None:
    from tests.contracts.test_standard_path_input_bind_v4 import _values

    inventory = _inventory()
    values = _values(_RATE)
    values.update(
        observed_sample_count=_RATE - _GAP_COUNT,
        missing_sample_count=_GAP_COUNT,
        timeline_sha256=inventory.timeline_sha256,
        gap_map_content_digest=inventory.gap_map_content_digest,
        validity_inventory_sha256=inventory.inventory_digest,
        validity_inventory=inventory.model_dump(mode="json"),
    )
    binding = StandardPathInputBindV4.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )
    reader = _Reader(binding.validity_inventory)
    outputs = _OutputSink()
    analyzer = production_standard_native_evidence_registry().get("path-standard-native")
    context = AnalysisContext(
        session_id=binding.session_id,
        run_id="native-evidence-run",
        pipeline_release="1" * 40,
        scope_key="path",
        scope=ScopeIdentityV1.receiver_path(
            session_id=binding.session_id,
            stream_id=binding.stream_id,
            receiver_id=binding.receiver_id,
        ),
        stage_config=production_standard_native_evidence_configuration()["path-standard-native"],
    )

    result = analyzer.analyze(context, reader, _SubjectProducts(binding), outputs)  # type: ignore[arg-type]

    assert result.outcome.value == "partial_coverage"
    assert len(result.products) == 5
    assert set(outputs.documents) == {
        ("quality.summary", 2),
        ("standard.power-timeline", 3),
        ("standard.numerical-waterfall", 3),
        ("standard.probe-schedule", 3),
        ("standard.native-stateful-path", 1),
    }
    assert result.summary["native_evidence_only"] is True
    stateful = StandardNativeStatefulPathV1.model_validate(
        outputs.documents[("standard.native-stateful-path", 1)]
    )
    assert stateful.stateful_science_status == "unavailable_global_schedule"
    assert tuple(item.continuity_segment for item in stateful.segments) == inventory.segments


def test_native_evidence_analyzer_reports_complete_for_one_lossless_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.contracts.test_standard_path_input_bind_v4 import _values

    inventory = ValidityInventoryV1(
        stream_id="stream-0",
        timeline_sha256=canonical_digest({"timeline": "lossless"}),
        gap_map_content_digest=canonical_digest({"gap-map": "lossless"}),
        first_device_sample_counter=100,
        logical_sample_count=_RATE,
        observed_sample_count=_RATE,
        missing_sample_count=0,
        continuity_boundary_count=0,
        runs=(
            {
                "run_index": 0,
                "device_sample_start": 0,
                "sample_count": _RATE,
                "content_kind": "observed",
                "stored_sample_start": 0,
                "continuity_segment_index": 0,
            },
        ),
        segments=(
            {
                "segment_index": 0,
                "device_sample_start": 0,
                "device_sample_stop": _RATE,
                "stored_sample_start": 0,
                "stored_sample_stop": _RATE,
            },
        ),
    )
    values = _values(_RATE)
    values.update(
        observed_sample_count=_RATE,
        missing_sample_count=0,
        timeline_sha256=inventory.timeline_sha256,
        gap_map_content_digest=inventory.gap_map_content_digest,
        validity_inventory_sha256=inventory.inventory_digest,
        validity_inventory=inventory.model_dump(mode="json"),
    )
    binding = StandardPathInputBindV4.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )
    outputs = _OutputSink()
    monkeypatch.setattr(native_stateful, "scan_pilot_detections", lambda *args, **kwargs: ())
    analyzer = production_standard_native_evidence_registry().get("path-standard-native")
    context = AnalysisContext(
        session_id=binding.session_id,
        run_id="native-lossless-run",
        pipeline_release="1" * 40,
        scope_key="path",
        scope=ScopeIdentityV1.receiver_path(
            session_id=binding.session_id,
            stream_id=binding.stream_id,
            receiver_id=binding.receiver_id,
        ),
        stage_config=production_standard_native_evidence_configuration()["path-standard-native"],
    )

    result = analyzer.analyze(  # type: ignore[arg-type]
        context,
        _LosslessReader(inventory),
        _SubjectProducts(binding),
        outputs,
    )

    assert result.outcome.value == "complete"
    assert len(result.products) == 5
    assert result.summary["coverage_fraction"] == 1.0
    stateful = StandardNativeStatefulPathV1.model_validate(
        outputs.documents[("standard.native-stateful-path", 1)]
    )
    assert stateful.stateful_science_status == "complete"
    assert stateful.analyzed_outer_window_count == 1
    assert stateful.segments[0].global_device_sample_start == 0


class _StatefulCampaignAbort(BaseException):
    pass


def test_stateful_poison_publishes_no_partial_native_product_batch(
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

    inventory = rate_inventory(_RATE)
    binding = rate_binding(_RATE, inventory)
    outputs = _OutputSink()
    context = AnalysisContext(
        session_id=binding.session_id,
        run_id="native-poison-run",
        pipeline_release="1" * 40,
        scope_key="path",
        scope=ScopeIdentityV1.receiver_path(
            session_id=binding.session_id,
            stream_id=binding.stream_id,
            receiver_id=binding.receiver_id,
        ),
        stage_config=production_standard_native_evidence_configuration()["path-standard-native"],
    )

    def abort(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise _StatefulCampaignAbort

    monkeypatch.setattr(StandardNativeStatefulRunner, "run", abort)
    with pytest.raises(_StatefulCampaignAbort):
        PathStandardNativeEvidenceAnalyzer().analyze(  # type: ignore[arg-type]
            context,
            _ToneReader(_RATE, inventory),
            _SubjectProducts(binding),
            outputs,
        )

    assert outputs.documents == {}


def test_unavailable_native_stages_terminate_explicitly_without_products() -> None:
    registry = production_standard_native_evidence_registry()

    result = registry.get("path-alternate-tracks-native").analyze(  # type: ignore[arg-type]
        AnalysisContext(
            session_id="native-session",
            run_id="native-evidence-run",
            pipeline_release="1" * 40,
        ),
        object(),
        object(),
        object(),
    )
    assert result.outcome.value == "insufficient_data"
    assert result.products == ()
    assert result.summary["native_stage_available"] is False
