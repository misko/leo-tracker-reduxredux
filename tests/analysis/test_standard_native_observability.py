from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pytest

from leo.analysis.standard import native_analyzers, native_stateful
from leo.analysis.standard.configuration import production_receiver_standard_config
from leo.analysis.standard.full_capture_glrt20ms import WindowResult
from leo.analysis.standard.native_analyzers import (
    PathStandardNativeEvidenceAnalyzer,
    production_standard_native_evidence_configuration,
    production_standard_native_evidence_registry,
)
from leo.analysis.standard.native_full_capture_glrt import (
    StandardNativeFullCaptureGlrtRunner,
)
from leo.analysis.standard.native_runner import run_standard_native_observability
from leo.analysis.standard.native_stateful import (
    StandardNativeStatefulRunner,
)
from leo.analysis.standard.native_waterfall import measure_standard_native_waterfall
from leo.analysis.standard.runner import ReceiverStandardConfig
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import PilotProbeDetection
from leo.analysis.starlink.trajectory_feedback import iter_pilot_probe_samples
from leo.analysis.waterfall import WaterfallConfig
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.pilot_doppler_segments import StandardPilotDopplerSegmentsV3
from leo.contracts.radio import IqBlockMetadataV1
from leo.contracts.standard_native import StandardNativeSourceV1
from leo.contracts.standard_native_glrt import StandardNativeFullCaptureGlrt20msV1
from leo.contracts.standard_native_path_report import StandardNativePathReportV3
from leo.contracts.standard_native_stateful_v2 import StandardNativeStatefulPathV2
from leo.contracts.standard_pipeline import StandardPathInputBindV4
from leo.contracts.validity import ContinuitySegmentV1, ValidityInventoryV1
from leo.domain.iq import IqBlock
from leo.pipeline import (
    AnalysisContext,
    ProductSpec,
    PublishedProduct,
    ScopeIdentityV1,
)
from leo.pipeline.validity import (
    DeviceIqSpan,
    WindowClassification,
    WindowValidity,
)

_RATE = 2_500_000
_GAP_START = 100_000
_GAP_COUNT = 10_000


def _no_result_scan(
    iq,
    config,
    *,
    edge,
    primary_qam_detection_observer=None,
    frequency_reference=None,
):
    del edge, frequency_reference
    detections = tuple(
        PilotProbeDetection(
            NumericalStatus.NO_RESULT,
            sample_start,
            sample_start / iq.sample_rate_hz,
            None,
            None,
            (),
            None,
            None,
            "test no-result probe",
        )
        for sample_start, _samples in iter_pilot_probe_samples(iq, config)
    )
    if primary_qam_detection_observer is not None:
        for detection in detections:
            primary_qam_detection_observer(detection, None)
    return detections


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
        rf_bandwidth_hz=_RATE,
        tuned_center_frequency_hz=959_687_500,
        logical_sample_count=_RATE,
        observed_sample_count=_RATE - _GAP_COUNT,
        missing_sample_count=_GAP_COUNT,
        starlink_channel=1,
        starlink_edge="lower",
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
        self.payloads: dict[tuple[str, int], bytes] = {}

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

    def publish_bytes(self, product: ProductSpec, payload: bytes) -> PublishedProduct:
        self.payloads[(product.kind, product.schema_version)] = payload
        return PublishedProduct(
            product=product,
            logical_uri=f"bulk://native/{product.kind}/v{product.schema_version}.png",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )


def _fast_glrt_runner(config: ReceiverStandardConfig) -> StandardNativeFullCaptureGlrtRunner:
    def no_result(index: int, start: int, samples: np.ndarray) -> WindowResult:
        start_s = start / _RATE
        end_s = (start + len(samples)) / _RATE
        return WindowResult(
            probe_index=index,
            sample_start=start,
            start_time_s=start_s,
            center_time_s=(start_s + end_s) / 2,
            end_time_s=end_s,
            acquisition_status="no_result",
            candidate_count=0,
            best_candidate_rank=None,
            epoch_sample=None,
            acquired_cfo_hz=None,
            residual_cfo_hz=None,
            tracking_cfo_hz=None,
            glrt_exact_score=None,
            glrt_control_score=None,
            glrt_margin=None,
            passed_margin_gate=False,
            lattice_frame_count=0,
            measured_frame_count=0,
            robust_line_available=False,
            robust_reference_time_s=None,
            robust_cfo_at_reference_hz=None,
            robust_slope_hz_s=None,
            robust_slope_sigma_hz_s=None,
            robust_residual_rms_hz=None,
            robust_median_absolute_residual_hz=None,
            robust_mad_scale_hz=None,
            robust_outlier_count=0,
            robust_converged=None,
            reason="bounded analyzer fixture",
        )

    def no_tracks(rows: tuple[WindowResult, ...]):
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

    return StandardNativeFullCaptureGlrtRunner(
        config,
        window_kernel=no_result,
        segment_kernel=no_tracks,
    )


def test_native_evidence_analyzer_executes_only_truthful_products(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.contracts.test_standard_path_input_bind_v4 import _values

    def no_result_probe(item, config, edge):
        del config, edge
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
    analyzer = PathStandardNativeEvidenceAnalyzer(
        stateful_runner_factory=lambda config: StandardNativeStatefulRunner(
            config,
            probe_detector=no_result_probe,
        ),
        full_capture_glrt_runner_factory=_fast_glrt_runner,
    )
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
    assert len(result.products) == 8
    assert set(outputs.documents) == {
        ("quality.summary", 2),
        ("standard.power-timeline", 3),
        ("standard.numerical-waterfall", 3),
        ("standard.probe-schedule", 3),
        ("standard.native-stateful-path", 2),
        ("standard.pilot-doppler-segments", 3),
        ("standard.full-capture-glrt20ms", 1),
        ("standard.path-report", 3),
    }
    assert result.summary["native_evidence_only"] is True
    stateful = StandardNativeStatefulPathV2.model_validate(
        outputs.documents[("standard.native-stateful-path", 2)]
    )
    pilot_v3 = StandardPilotDopplerSegmentsV3.model_validate(
        outputs.documents[("standard.pilot-doppler-segments", 3)]
    )
    assert pilot_v3.source == StandardNativeSourceV1.from_path_binding(binding)
    assert pilot_v3.stateful_path_product_digest == canonical_digest(
        stateful.model_dump(mode="json")
    )
    assert pilot_v3.stateful_path_digest == stateful.stateful_path_digest
    assert pilot_v3.phase_config_digest == pilot_v3.phase_config.digest
    assert pilot_v3.source_v2_locklet_count == 0
    assert pilot_v3.corrected_phase_trackability_count == 0
    assert pilot_v3.segments == ()
    assert stateful.stateful_science_status == "partial_coverage"
    assert stateful.analyzed_outer_window_count == 2
    assert tuple(item.continuity_segment for item in stateful.segments) == inventory.segments
    assert tuple(item.disposition.value for item in stateful.segments) == (
        "analyzed",
        "analyzed",
    )
    assert stateful.segments[0].local_science is not None
    assert stateful.segments[1].local_science is not None
    assert tuple(item.sample_start for item in stateful.segments[0].local_science.detections) == (
        0,
    )
    assert stateful.segments[1].local_science.detections[0].sample_start == 15_000
    glrt = StandardNativeFullCaptureGlrt20msV1.model_validate(
        outputs.documents[("standard.full-capture-glrt20ms", 1)]
    )
    assert glrt.source == StandardNativeSourceV1.from_path_binding(binding)
    assert (
        glrt.science_configuration_digest
        == context.stage_config["full_capture_glrt_configuration_digest"]
    )
    assert glrt.accounting.scheduled_count == 99
    assert glrt.accounting.valid_count == 97
    path_report = StandardNativePathReportV3.model_validate(
        outputs.documents[("standard.path-report", 3)]
    )
    assert path_report.schedule_execution.accounting.valid_count == 39
    assert path_report.schedule_execution.accounting.analyzed_count == 39
    assert path_report.schedule_execution.accounting.gap_excluded_count == 1
    assert path_report.qam_statistics.qam_result_count == 0
    assert path_report.scientific_disposition.value == "no_candidate"
    assert glrt.accounting.gap_excluded_count == 2
    assert glrt.accounting.analyzed_count == 97
    assert result.summary["full_capture_glrt_excluded_window_count"] == 2

    tampered_config = dict(context.stage_config)
    tampered_config["full_capture_glrt_configuration_digest"] = canonical_digest(
        {"unexpected": "GLRT configuration"}
    )
    tampered_outputs = _OutputSink()
    with pytest.raises(ValueError, match="GLRT configuration digest"):
        analyzer.analyze(  # type: ignore[arg-type]
            context.model_copy(update={"stage_config": tampered_config}),
            _Reader(binding.validity_inventory),
            _SubjectProducts(binding),
            tampered_outputs,
        )
    assert tampered_outputs.documents == {}

    tampered_phase_config = dict(context.stage_config)
    tampered_phase_config["pilot_phase_locklet_configuration_digest"] = canonical_digest(
        {"unexpected": "phase-locklet configuration"}
    )
    with pytest.raises(ValueError, match="phase-locklet policy digest"):
        analyzer.analyze(  # type: ignore[arg-type]
            context.model_copy(update={"stage_config": tampered_phase_config}),
            _Reader(binding.validity_inventory),
            _SubjectProducts(binding),
            _OutputSink(),
        )


class _ObservabilityPolicyCaptured(Exception):
    pass


@pytest.mark.parametrize("sample_rate_hz", (2_500_000, 3_000_000, 5_000_000, 10_000_000))
def test_native_evidence_analyzer_uses_the_resolved_production_feedback_policy(
    monkeypatch: pytest.MonkeyPatch,
    sample_rate_hz: int,
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
    captured: dict[str, object] = {}

    def capture_policy(*args: object, **kwargs: object) -> None:
        del args
        captured.update(kwargs)
        raise _ObservabilityPolicyCaptured

    monkeypatch.setattr(
        native_analyzers,
        "run_standard_native_observability",
        capture_policy,
    )
    stage_config = production_standard_native_evidence_configuration()["path-standard-native"]
    context = AnalysisContext(
        session_id=binding.session_id,
        run_id=f"native-policy-{sample_rate_hz}",
        pipeline_release="1" * 40,
        scope_key="path",
        scope=ScopeIdentityV1.receiver_path(
            session_id=binding.session_id,
            stream_id=binding.stream_id,
            receiver_id=binding.receiver_id,
        ),
        stage_config=stage_config,
    )

    with pytest.raises(_ObservabilityPolicyCaptured):
        PathStandardNativeEvidenceAnalyzer().analyze(  # type: ignore[arg-type]
            context,
            _ToneReader(sample_rate_hz, inventory),
            _SubjectProducts(binding),
            _OutputSink(),
        )

    feedback = production_receiver_standard_config(sample_rate_hz=sample_rate_hz).feedback
    assert "probes" not in stage_config
    assert captured["subwindow_ms"] == feedback.subwindow_ms
    assert captured["probe_ms"] == feedback.probe_ms
    assert captured["probe_offsets_ms"] == feedback.probe_offsets_ms
    assert captured["maximum_coarse_windows"] == feedback.maximum_outer_windows
    assert feedback == production_receiver_standard_config().feedback


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
    monkeypatch.setattr(native_stateful, "scan_pilot_detections", _no_result_scan)
    stateful_config = production_receiver_standard_config(sample_rate_hz=_RATE)
    legacy_result = StandardNativeStatefulRunner(stateful_config).run(
        _LosslessReader(inventory),
        binding,
        edge=binding.starlink_edge,
    )
    expected_stateful = native_stateful.build_standard_native_stateful_path_v2(
        legacy_result,
        binding,
        stateful_config,
        edge=binding.starlink_edge,
    )
    outputs = _OutputSink()
    analyzer = PathStandardNativeEvidenceAnalyzer(
        full_capture_glrt_runner_factory=_fast_glrt_runner
    )
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
    assert len(result.products) == 8
    assert result.summary["coverage_fraction"] == 1.0
    stateful = StandardNativeStatefulPathV2.model_validate(
        outputs.documents[("standard.native-stateful-path", 2)]
    )
    assert stateful.stateful_science_status == "complete"
    assert stateful.analyzed_outer_window_count == 1
    assert stateful.segments[0].global_device_sample_start == 0
    assert canonical_json_bytes(stateful.model_dump(mode="json")) == canonical_json_bytes(
        expected_stateful.model_dump(mode="json")
    )
    glrt = StandardNativeFullCaptureGlrt20msV1.model_validate(
        outputs.documents[("standard.full-capture-glrt20ms", 1)]
    )
    assert glrt.source == StandardNativeSourceV1.from_path_binding(binding)
    assert glrt.accounting.scheduled_count == glrt.accounting.valid_count == 99
    assert result.summary["full_capture_glrt_passing_window_count"] == 0
    path_report = StandardNativePathReportV3.model_validate(
        outputs.documents[("standard.path-report", 3)]
    )
    assert path_report.schedule_execution.accounting.valid_count == 40
    assert path_report.schedule_execution.accounting.analyzed_count == 40
    assert path_report.scientific_disposition.value == "no_candidate"


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


class _GlrtCampaignAbort(BaseException):
    pass


def test_glrt_poison_publishes_no_partial_native_product_batch(
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
        run_id="native-glrt-poison-run",
        pipeline_release="1" * 40,
        scope_key="path",
        scope=ScopeIdentityV1.receiver_path(
            session_id=binding.session_id,
            stream_id=binding.stream_id,
            receiver_id=binding.receiver_id,
        ),
        stage_config=production_standard_native_evidence_configuration()["path-standard-native"],
    )
    monkeypatch.setattr(native_stateful, "scan_pilot_detections", _no_result_scan)

    def abort(index: int, start: int, samples: np.ndarray) -> WindowResult:
        del index, start, samples
        raise _GlrtCampaignAbort

    glrt_runner = StandardNativeFullCaptureGlrtRunner(
        production_receiver_standard_config(sample_rate_hz=_RATE),
        window_kernel=abort,
    )
    analyzer = PathStandardNativeEvidenceAnalyzer(
        full_capture_glrt_runner_factory=lambda _config: glrt_runner
    )
    with pytest.raises(_GlrtCampaignAbort):
        analyzer.analyze(  # type: ignore[arg-type]
            context,
            _ToneReader(_RATE, inventory),
            _SubjectProducts(binding),
            outputs,
        )
    assert glrt_runner.poisoned
    assert outputs.documents == {}

    with pytest.raises(RuntimeError, match="poisoned"):
        analyzer.analyze(  # type: ignore[arg-type]
            context,
            _ToneReader(_RATE, inventory),
            _SubjectProducts(binding),
            outputs,
        )
    assert outputs.documents == {}


class _PathReportCampaignAbort(BaseException):
    pass


def test_path_report_poison_publishes_no_partial_native_product_batch(
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
        run_id="native-path-report-poison-run",
        pipeline_release="1" * 40,
        scope_key="path",
        scope=ScopeIdentityV1.receiver_path(
            session_id=binding.session_id,
            stream_id=binding.stream_id,
            receiver_id=binding.receiver_id,
        ),
        stage_config=production_standard_native_evidence_configuration()["path-standard-native"],
    )
    monkeypatch.setattr(native_stateful, "scan_pilot_detections", _no_result_scan)

    def abort(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise _PathReportCampaignAbort

    monkeypatch.setattr(
        native_analyzers,
        "build_standard_native_path_report",
        abort,
    )
    analyzer = PathStandardNativeEvidenceAnalyzer(
        full_capture_glrt_runner_factory=_fast_glrt_runner
    )

    with pytest.raises(_PathReportCampaignAbort):
        analyzer.analyze(  # type: ignore[arg-type]
            context,
            _ToneReader(_RATE, inventory),
            _SubjectProducts(binding),
            outputs,
        )

    assert outputs.documents == {}


def test_native_path_projection_declares_exact_sealed_predecessor_inventory() -> None:
    registry = production_standard_native_evidence_registry()
    spec = registry.get("path-alternate-tracks-native").spec
    assert tuple(item.kind for item in spec.input_products) == (
        "standard.numerical-waterfall",
        "standard.native-stateful-path",
        "standard.pilot-doppler-segments",
        "standard.full-capture-glrt20ms",
        "standard.path-report",
    )
    assert all(item.producer_stage_key == "path-standard-native" for item in spec.input_products)
    assert len(spec.output_products) == 13
