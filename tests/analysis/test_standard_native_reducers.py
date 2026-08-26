from __future__ import annotations

from typing import Any

from leo.analysis.standard.native_products import (
    NUMERICAL_WATERFALL_V3_PRODUCT,
    POWER_TIMELINE_V3_PRODUCT,
    PROBE_SCHEDULE_V3_PRODUCT,
    QUALITY_V2_PRODUCT,
    STATEFUL_PATH_V1_PRODUCT,
)
from leo.analysis.standard.native_reducers import (
    native_paired_waterfall_source,
    reduce_native_paired_evidence,
    reduce_native_radio_evidence,
)
from leo.analysis.standard.native_runner import run_standard_native_observability
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import (
    StandardNativeNumericalWaterfallV3,
    StandardNativePowerTimelineV3,
    StandardNativeQualityV2,
    StandardNativeSourceV1,
    StandardProbeScheduleV3,
)
from leo.contracts.standard_native_stateful import (
    NativeStatefulSegmentV1,
    StandardNativeStatefulPathV1,
)
from leo.contracts.standard_pipeline import StandardPairInputBindV2
from leo.pipeline import AnalysisContext, ScopeIdentityV1, StageOutcome, UpstreamJsonProduct
from leo.presentation.standard_pipeline import StandardViewKindV2
from leo.presentation.standard_png import render_full_standard_plot_png
from tests.analysis.test_standard_native_observability import _binding, _inventory, _Reader


def _source(
    base: StandardNativeSourceV1,
    *,
    stream_id: str,
    radio_id: str,
    receiver_id: int,
    first_utc_shift_ns: int,
) -> StandardNativeSourceV1:
    timing = base.timing.model_copy(
        update={
            "first_estimate_utc_ns": base.timing.first_estimate_utc_ns + first_utc_shift_ns,
            "first_earliest_utc_ns": base.timing.first_earliest_utc_ns + first_utc_shift_ns,
            "first_latest_utc_ns": base.timing.first_latest_utc_ns + first_utc_shift_ns,
            "last_estimate_utc_ns": base.timing.last_estimate_utc_ns + first_utc_shift_ns,
            "last_earliest_utc_ns": base.timing.last_earliest_utc_ns + first_utc_shift_ns,
            "last_latest_utc_ns": base.timing.last_latest_utc_ns + first_utc_shift_ns,
        }
    )
    return base.model_copy(
        update={
            "stream_id": stream_id,
            "radio_id": radio_id,
            "receiver_id": receiver_id,
            "path_input_binding_digest": canonical_digest(
                {"stream": stream_id, "receiver": receiver_id}
            ),
            "timing": timing,
        }
    )


def _path_documents(
    source: StandardNativeSourceV1,
    result: Any,
) -> dict[str, dict[str, Any]]:
    receiver = result.quality.receivers[0].model_copy(update={"receiver_id": source.receiver_id})
    quality = StandardNativeQualityV2(
        source=source,
        clipping_abs_threshold=result.quality.clipping_abs_threshold,
        uncovered_region_count=result.quality.uncovered_region_count,
        receivers=(receiver,),
    )
    power = StandardNativePowerTimelineV3(
        source=source,
        timeline=result.power.timeline.model_copy(update={"receiver_ids": (source.receiver_id,)}),
    )
    waterfall = StandardNativeNumericalWaterfallV3(
        source=source,
        waterfall=result.waterfall.waterfall.model_copy(
            update={"receiver_ids": (source.receiver_id,)}
        ),
    )
    schedule_values = result.schedule.model_dump(mode="json", exclude={"schedule_digest"})
    schedule_values["source"] = source.model_dump(mode="json")
    schedule = StandardProbeScheduleV3.model_validate(
        {
            **schedule_values,
            "schedule_digest": canonical_digest(schedule_values),
        }
    )
    stateful_segments = []
    for segment in source.continuity_segments:
        segment_values = {
            "schema_version": 1,
            "continuity_segment": segment.model_dump(mode="json"),
            "continuity_segment_index": segment.segment_index,
            "global_device_sample_start": segment.device_sample_start,
            "global_device_sample_stop": segment.device_sample_stop,
            "disposition": (
                "empty_terminal"
                if segment.observed_sample_count == 0
                else "global_schedule_unavailable"
            ),
            "local_science": None,
        }
        stateful_segments.append(
            NativeStatefulSegmentV1.model_validate(
                {**segment_values, "segment_digest": canonical_digest(segment_values)}
            )
        )
    stateful_values = {
        "schema_version": 1,
        "algorithm_version": "standard-native-stateful-path-v1",
        "source": source.model_dump(mode="json"),
        "starlink_edge": "lower",
        "science_configuration_digest": canonical_digest({"stateful-config": 1}),
        "stateful_science_status": "unavailable_global_schedule",
        "maximum_outer_window_count": 120,
        "analyzed_outer_window_count": 0,
        "segments": tuple(item.model_dump(mode="json") for item in stateful_segments),
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    stateful = StandardNativeStatefulPathV1.model_validate(
        {**stateful_values, "stateful_path_digest": canonical_digest(stateful_values)}
    )
    return {
        QUALITY_V2_PRODUCT.kind: quality.model_dump(mode="json"),
        POWER_TIMELINE_V3_PRODUCT.kind: power.model_dump(mode="json"),
        NUMERICAL_WATERFALL_V3_PRODUCT.kind: waterfall.model_dump(mode="json"),
        PROBE_SCHEDULE_V3_PRODUCT.kind: schedule.model_dump(mode="json"),
        STATEFUL_PATH_V1_PRODUCT.kind: stateful.model_dump(mode="json"),
    }


def _upstream(
    source: StandardNativeSourceV1,
    result: Any,
    *,
    node_id: str,
) -> dict[str, UpstreamJsonProduct]:
    return {
        kind: UpstreamJsonProduct(
            producer_node_id=node_id,
            producer_scope=ScopeIdentityV1.receiver_path(
                session_id=source.session_id,
                stream_id=source.stream_id,
                receiver_id=source.receiver_id,
            ),
            outcome=StageOutcome.PARTIAL_COVERAGE,
            product_digest=canonical_digest(document),
            document=document,
        )
        for kind, document in _path_documents(source, result).items()
    }


def _radio_report(
    base: StandardNativeSourceV1,
    result: Any,
    *,
    stream_id: str,
    radio_id: str,
    node_prefix: str,
    first_utc_shift_ns: int,
):
    sources = tuple(
        _source(
            base,
            stream_id=stream_id,
            radio_id=radio_id,
            receiver_id=receiver_id,
            first_utc_shift_ns=first_utc_shift_ns,
        )
        for receiver_id in (0, 1)
    )
    upstream = tuple(
        _upstream(source, result, node_id=f"{node_prefix}-{source.receiver_id}")
        for source in sources
    )
    context = AnalysisContext(
        session_id=base.session_id,
        run_id="native-run",
        pipeline_release="1" * 40,
        scope=ScopeIdentityV1.radio(
            session_id=base.session_id,
            stream_id=stream_id,
            radio_id=radio_id,
        ),
        dependency_node_ids=tuple(f"{node_prefix}-{item}" for item in (0, 1)),
    )
    report = reduce_native_radio_evidence(
        context,
        quality_products=tuple(item[QUALITY_V2_PRODUCT.kind] for item in upstream),
        power_products=tuple(item[POWER_TIMELINE_V3_PRODUCT.kind] for item in upstream),
        waterfall_products=tuple(item[NUMERICAL_WATERFALL_V3_PRODUCT.kind] for item in upstream),
        schedule_products=tuple(item[PROBE_SCHEDULE_V3_PRODUCT.kind] for item in upstream),
        stateful_products=tuple(item[STATEFUL_PATH_V1_PRODUCT.kind] for item in upstream),
    )
    return report, upstream


def test_native_reducers_sum_sufficient_statistics_and_intersect_valid_utc() -> None:
    inventory = _inventory()
    result = run_standard_native_observability(_Reader(inventory), _binding(inventory))
    base = result.quality.source
    left, left_paths = _radio_report(
        base,
        result,
        stream_id="stream-0",
        radio_id="radio-0",
        node_prefix="path-0",
        first_utc_shift_ns=0,
    )
    right, right_paths = _radio_report(
        base,
        result,
        stream_id="stream-1",
        radio_id="radio-1",
        node_prefix="path-1",
        first_utc_shift_ns=1_000,
    )
    pair_values = {
        "schema_version": 2,
        "algorithm_version": "standard-pair-input-bind-v2",
        "session_id": base.session_id,
        "manifest_digest": base.manifest_digest,
        "synchronization_inventory_digest": base.synchronization_inventory_digest,
        "raw_integrity_attestation_digests": (
            canonical_digest({"raw": 0}),
            canonical_digest({"raw": 1}),
        ),
        "timing": {
            "schema_version": 1,
            "synchronization_inventory_digest": base.synchronization_inventory_digest,
            "union_start_utc_ns": 999_999_900,
            "union_end_utc_ns": 2_000_001_100,
            "estimated_overlap_start_utc_ns": 1_000_001_000,
            "estimated_overlap_end_utc_ns": 2_000_000_000,
            "estimated_start_skew_ns": 1_000,
            "start_skew_uncertainty_ns": 200,
            "guaranteed_overlap_ns": 999_998_000,
            "synchronization_grade": "host_bracket",
            "phase_coherent": False,
        },
    }
    pair_binding = StandardPairInputBindV2.model_validate(
        {**pair_values, "binding_digest": canonical_digest(pair_values)}
    )
    radio_products = (
        UpstreamJsonProduct(
            producer_node_id="radio-0",
            producer_scope=ScopeIdentityV1.radio(
                session_id=base.session_id,
                stream_id=left.stream_id,
                radio_id=left.radio_id,
            ),
            outcome=StageOutcome(left.status),
            product_digest=left.report_digest,
            document=left.model_dump(mode="json"),
        ),
        UpstreamJsonProduct(
            producer_node_id="radio-1",
            producer_scope=ScopeIdentityV1.radio(
                session_id=base.session_id,
                stream_id=right.stream_id,
                radio_id=right.radio_id,
            ),
            outcome=StageOutcome(right.status),
            product_digest=right.report_digest,
            document=right.model_dump(mode="json"),
        ),
    )
    paired_context = AnalysisContext(
        session_id=base.session_id,
        run_id="native-run",
        pipeline_release="1" * 40,
        scope=ScopeIdentityV1.paired(
            session_id=base.session_id,
            synchronization_inventory_digest=base.synchronization_inventory_digest,
        ),
        dependency_node_ids=("radio-0", "radio-1"),
    )

    paired = reduce_native_paired_evidence(
        paired_context,
        pair_binding=pair_binding,
        radio_products=radio_products,
    )

    assert paired.status == "partial_coverage"
    assert paired.current_eligible is False
    assert (
        left.paths[0].stateful_path_product_digest
        == left_paths[0][STATEFUL_PATH_V1_PRODUCT.kind].product_digest
    )
    assert paired.aggregate_statistics.receiver_path_count == 4
    assert paired.aggregate_statistics.energy_sum_ci16_squared == 4 * (
        inventory.observed_sample_count * 98
    )
    assert len(paired.valid_utc_intervals) == 2
    assert paired.valid_utc_intervals[0].start_utc_ns == (
        left.valid_utc_intervals[0].start_utc_ns + 1_000
    )

    waterfalls = tuple(
        path[NUMERICAL_WATERFALL_V3_PRODUCT.kind]
        for group in (left_paths, right_paths)
        for path in group
    )
    presentation_context = paired_context.model_copy(
        update={"dependency_node_ids": tuple(item.producer_node_id for item in waterfalls)}
    )
    source = native_paired_waterfall_source(presentation_context, waterfalls)
    payload = render_full_standard_plot_png(source, StandardViewKindV2.WATERFALL)
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(source.paths) == 4
