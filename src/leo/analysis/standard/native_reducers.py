"""Truthful evidence-only reducers for Standard-native path products."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, cast

from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import (
    NativeOpportunityAccountingV1,
    NativePathEvidenceV1,
    NativeQualityReceiverV2,
    NativeSufficientStatisticsV1,
    NativeValidUtcIntervalV1,
    StandardNativeNumericalWaterfallV3,
    StandardNativePairedReportV3,
    StandardNativePowerTimelineV3,
    StandardNativeQualityV2,
    StandardNativeRadioReportV3,
    StandardNativeSourceV1,
    StandardProbeScheduleV3,
)
from leo.contracts.standard_native_stateful import StandardNativeStatefulPathV1
from leo.contracts.standard_pipeline import StandardPairInputBindV2
from leo.pipeline import AnalysisContext, ScopeKind, StageOutcome, UpstreamJsonProduct

_NANOSECONDS_PER_SECOND = 1_000_000_000


def reduce_native_radio_evidence(
    context: AnalysisContext,
    *,
    quality_products: tuple[UpstreamJsonProduct, ...],
    power_products: tuple[UpstreamJsonProduct, ...],
    waterfall_products: tuple[UpstreamJsonProduct, ...],
    schedule_products: tuple[UpstreamJsonProduct, ...],
    stateful_products: tuple[UpstreamJsonProduct, ...],
) -> StandardNativeRadioReportV3:
    """Reduce exactly two path jobs without averaging invalid zero-fill."""

    scope = context.scope
    if (
        scope is None
        or scope.kind is not ScopeKind.RADIO
        or scope.stream_id is None
        or scope.radio_id is None
    ):
        raise ValueError("native radio reducer requires an exact radio scope")
    inventories = (
        quality_products,
        power_products,
        waterfall_products,
        schedule_products,
        stateful_products,
    )
    node_ids = tuple(item.producer_node_id for item in quality_products)
    if len(node_ids) != 2 or node_ids != context.dependency_node_ids:
        raise ValueError("native radio reducer requires exactly two authorized path nodes")
    if any(
        tuple(item.producer_node_id for item in inventory) != node_ids for inventory in inventories
    ):
        raise ValueError("native radio product fan-in does not share one exact path inventory")

    paths: list[NativePathEvidenceV1] = []
    for quality_item, power_item, waterfall_item, schedule_item, stateful_item in zip(
        *inventories,
        strict=True,
    ):
        upstream = (quality_item, power_item, waterfall_item, schedule_item, stateful_item)
        if len({item.outcome for item in upstream}) != 1:
            raise ValueError("native path products disagree on their terminal outcome")
        producer_scope = quality_item.producer_scope
        if any(item.producer_scope != producer_scope for item in upstream):
            raise ValueError("native path products disagree on producer scope")
        if (
            producer_scope.kind is not ScopeKind.RECEIVER_PATH
            or producer_scope.session_id != context.session_id
            or producer_scope.stream_id != scope.stream_id
            or producer_scope.receiver_id is None
        ):
            raise ValueError("native radio reducer received foreign path membership")

        quality = StandardNativeQualityV2.model_validate(quality_item.document)
        power = StandardNativePowerTimelineV3.model_validate(power_item.document)
        waterfall = StandardNativeNumericalWaterfallV3.model_validate(waterfall_item.document)
        schedule = StandardProbeScheduleV3.model_validate(schedule_item.document)
        stateful = StandardNativeStatefulPathV1.model_validate(stateful_item.document)
        source = quality.source
        if any(
            item != source
            for item in (power.source, waterfall.source, schedule.source, stateful.source)
        ):
            raise ValueError("native path products do not share exact source authority")
        if (
            source.session_id != context.session_id
            or source.stream_id != scope.stream_id
            or source.radio_id != scope.radio_id
            or source.receiver_id != producer_scope.receiver_id
        ):
            raise ValueError("native path product source disagrees with reducer scope")
        outcome = _path_outcome(quality_item.outcome)
        expected_stateful_status = (
            "complete" if outcome == "complete" else "unavailable_global_schedule"
        )
        if stateful.stateful_science_status != expected_stateful_status:
            raise ValueError("native path outcome disagrees with stateful schedule availability")
        paths.append(
            NativePathEvidenceV1(
                source=source,
                stage_outcome=outcome,
                quality_product_digest=quality_item.product_digest,
                power_timeline_product_digest=power_item.product_digest,
                numerical_waterfall_product_digest=waterfall_item.product_digest,
                probe_schedule_product_digest=schedule_item.product_digest,
                stateful_path_product_digest=stateful_item.product_digest,
                clipping_abs_threshold=quality.clipping_abs_threshold,
                uncovered_region_count=quality.uncovered_region_count,
                quality=quality.receivers[0],
                opportunities=schedule.accounting,
                valid_utc_intervals=valid_utc_intervals(source),
            )
        )
    ordered = cast(
        tuple[NativePathEvidenceV1, NativePathEvidenceV1],
        tuple(sorted(paths, key=lambda item: item.source.receiver_id)),
    )
    intervals = intersect_valid_utc_intervals(
        ordered[0].valid_utc_intervals,
        ordered[1].valid_utc_intervals,
    )
    status = (
        "insufficient_data"
        if not intervals
        else (
            "complete"
            if all(item.stage_outcome == "complete" for item in ordered)
            else "partial_coverage"
        )
    )
    values = {
        "schema_version": 3,
        "algorithm_version": "standard-native-radio-report-v3",
        "session_id": context.session_id,
        "stream_id": scope.stream_id,
        "radio_id": scope.radio_id,
        "manifest_digest": ordered[0].source.manifest_digest,
        "synchronization_inventory_digest": (ordered[0].source.synchronization_inventory_digest),
        "sample_rate_hz": ordered[0].source.sample_rate_hz,
        "status": status,
        "reason": _status_reason(status, subject="receiver paths"),
        "paths": tuple(item.model_dump(mode="json") for item in ordered),
        "aggregate_statistics": aggregate_sufficient_statistics(
            tuple(item.quality for item in ordered)
        ).model_dump(mode="json"),
        "aggregate_opportunities": aggregate_opportunities(
            tuple(item.opportunities for item in ordered)
        ).model_dump(mode="json"),
        "valid_utc_intervals": tuple(item.model_dump(mode="json") for item in intervals),
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return StandardNativeRadioReportV3.model_validate(
        {**values, "report_digest": canonical_digest(values)}
    )


def reduce_native_paired_evidence(
    context: AnalysisContext,
    *,
    pair_binding: StandardPairInputBindV2,
    radio_products: tuple[UpstreamJsonProduct, ...],
) -> StandardNativePairedReportV3:
    """Intersect exact radio validity intervals in UTC and merge their statistics."""

    scope = context.scope
    if (
        scope is None
        or scope.kind is not ScopeKind.PAIRED
        or scope.synchronization_inventory_digest is None
    ):
        raise ValueError("native paired reducer requires an exact paired scope")
    if (
        len(radio_products) != 2
        or tuple(item.producer_node_id for item in radio_products) != context.dependency_node_ids
    ):
        raise ValueError("native paired reducer requires exactly two authorized radio nodes")
    if (
        pair_binding.session_id != context.session_id
        or pair_binding.synchronization_inventory_digest != scope.synchronization_inventory_digest
    ):
        raise ValueError("native pair binding disagrees with exact paired scope")
    if any(item.producer_scope.kind is not ScopeKind.RADIO for item in radio_products):
        raise ValueError("native paired reducer received non-radio membership")
    radios = tuple(
        sorted(
            (StandardNativeRadioReportV3.model_validate(item.document) for item in radio_products),
            key=lambda item: (item.stream_id, item.radio_id),
        )
    )
    typed_radios = cast(tuple[StandardNativeRadioReportV3, StandardNativeRadioReportV3], radios)
    for product, report in zip(radio_products, radios, strict=True):
        product_scope = product.producer_scope
        if (
            product.outcome.value != report.status
            or product_scope.session_id != report.session_id
            or product_scope.stream_id != report.stream_id
            or product_scope.radio_id != report.radio_id
        ):
            raise ValueError("native radio report outcome or membership is inconsistent")
    if (
        any(item.session_id != context.session_id for item in radios)
        or any(item.manifest_digest != pair_binding.manifest_digest for item in radios)
        or any(
            item.synchronization_inventory_digest != pair_binding.synchronization_inventory_digest
            for item in radios
        )
        or len({item.sample_rate_hz for item in radios}) != 1
    ):
        raise ValueError("native paired reducer received foreign radio authority")
    intervals = intersect_valid_utc_intervals(
        typed_radios[0].valid_utc_intervals,
        typed_radios[1].valid_utc_intervals,
    )
    status = (
        "insufficient_data"
        if not intervals
        else (
            "complete"
            if all(item.status == "complete" for item in typed_radios)
            else "partial_coverage"
        )
    )
    values = {
        "schema_version": 3,
        "algorithm_version": "standard-native-paired-report-v3",
        "session_id": context.session_id,
        "manifest_digest": pair_binding.manifest_digest,
        "synchronization_inventory_digest": pair_binding.synchronization_inventory_digest,
        "pair_input_binding_digest": pair_binding.binding_digest,
        "sample_rate_hz": typed_radios[0].sample_rate_hz,
        "status": status,
        "reason": _status_reason(status, subject="radios"),
        "radios": tuple(item.model_dump(mode="json") for item in typed_radios),
        "aggregate_statistics": aggregate_sufficient_statistics(
            tuple(item.aggregate_statistics for item in typed_radios)
        ).model_dump(mode="json"),
        "aggregate_opportunities": aggregate_opportunities(
            tuple(item.aggregate_opportunities for item in typed_radios)
        ).model_dump(mode="json"),
        "valid_utc_intervals": tuple(item.model_dump(mode="json") for item in intervals),
        "native_evidence_only": True,
        "current_eligible": False,
        "phase_coherent": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return StandardNativePairedReportV3.model_validate(
        {**values, "report_digest": canonical_digest(values)}
    )


def valid_utc_intervals(
    source: StandardNativeSourceV1,
) -> tuple[NativeValidUtcIntervalV1, ...]:
    """Project device segments into conservative inner UTC intervals.

    The first-sample host bracket is the timing authority.  Starting from its
    latest bound and stopping from its earliest bound prevents timing
    uncertainty from fabricating common support.  Sample offsets use exact
    integer nominal-rate arithmetic; empty inner intervals are omitted.
    """

    intervals: list[NativeValidUtcIntervalV1] = []
    for segment in source.continuity_segments:
        start_offset = _ceil_div(
            segment.device_sample_start * _NANOSECONDS_PER_SECOND,
            source.sample_rate_hz,
        )
        stop_offset = (
            segment.device_sample_stop * _NANOSECONDS_PER_SECOND
        ) // source.sample_rate_hz
        start = source.timing.first_latest_utc_ns + start_offset
        stop = source.timing.first_earliest_utc_ns + stop_offset
        if stop <= start:
            continue
        if intervals and intervals[-1].stop_utc_ns == start:
            intervals[-1] = intervals[-1].model_copy(update={"stop_utc_ns": stop})
        else:
            intervals.append(NativeValidUtcIntervalV1(start_utc_ns=start, stop_utc_ns=stop))
    return tuple(intervals)


def intersect_valid_utc_intervals(
    left: tuple[NativeValidUtcIntervalV1, ...],
    right: tuple[NativeValidUtcIntervalV1, ...],
) -> tuple[NativeValidUtcIntervalV1, ...]:
    """Return the maximally merged intersection of two canonical interval sets."""

    output: list[NativeValidUtcIntervalV1] = []
    left_index = 0
    right_index = 0
    while left_index < len(left) and right_index < len(right):
        left_item = left[left_index]
        right_item = right[right_index]
        start = max(left_item.start_utc_ns, right_item.start_utc_ns)
        stop = min(left_item.stop_utc_ns, right_item.stop_utc_ns)
        if stop > start:
            if output and output[-1].stop_utc_ns == start:
                output[-1] = output[-1].model_copy(update={"stop_utc_ns": stop})
            else:
                output.append(NativeValidUtcIntervalV1(start_utc_ns=start, stop_utc_ns=stop))
        if left_item.stop_utc_ns <= right_item.stop_utc_ns:
            left_index += 1
        else:
            right_index += 1
    return tuple(output)


def aggregate_sufficient_statistics(
    children: tuple[NativeQualityReceiverV2 | NativeSufficientStatisticsV1, ...],
) -> NativeSufficientStatisticsV1:
    """Merge integers first and derive fractions exactly once at the parent."""

    if not children:
        raise ValueError("native sufficient-stat aggregation requires children")
    path_count = sum(
        1 if isinstance(item, NativeQualityReceiverV2) else item.receiver_path_count
        for item in children
    )
    valid_count = sum(
        item.valid_sample_count
        if isinstance(item, NativeQualityReceiverV2)
        else item.valid_complex_sample_count
        for item in children
    )
    energy_sum = sum(item.energy_sum_ci16_squared for item in children)
    clipped_components = sum(item.clipped_component_count for item in children)
    clipped_samples = sum(item.clipped_complex_sample_count for item in children)
    minimum_i = tuple(item.minimum_i for item in children if item.minimum_i is not None)
    maximum_i = tuple(item.maximum_i for item in children if item.maximum_i is not None)
    minimum_q = tuple(item.minimum_q for item in children if item.minimum_q is not None)
    maximum_q = tuple(item.maximum_q for item in children if item.maximum_q is not None)
    if not valid_count or not all((minimum_i, maximum_i, minimum_q, maximum_q)):
        raise ValueError("native sufficient-stat aggregation requires observed IQ")
    min_i = min(minimum_i)
    max_i = max(maximum_i)
    min_q = min(minimum_q)
    max_q = max(maximum_q)
    return NativeSufficientStatisticsV1(
        receiver_path_count=path_count,
        valid_complex_sample_count=valid_count,
        energy_sum_ci16_squared=energy_sum,
        clipped_component_count=clipped_components,
        clipped_complex_sample_count=clipped_samples,
        clipped_complex_fraction=clipped_samples / valid_count,
        mean_power_full_scale_squared=energy_sum / (valid_count * 32_768**2),
        constant_iq=min_i == max_i and min_q == max_q,
        minimum_i=min_i,
        maximum_i=max_i,
        minimum_q=min_q,
        maximum_q=max_q,
    )


def aggregate_opportunities(
    children: tuple[NativeOpportunityAccountingV1, ...],
) -> NativeOpportunityAccountingV1:
    if not children:
        raise ValueError("native opportunity aggregation requires children")
    return NativeOpportunityAccountingV1(
        scheduled_count=sum(item.scheduled_count for item in children),
        valid_count=sum(item.valid_count for item in children),
        analyzed_count=sum(item.analyzed_count for item in children),
        passing_count=sum(item.passing_count for item in children),
        gap_excluded_count=sum(item.gap_excluded_count for item in children),
        continuity_boundary_excluded_count=sum(
            item.continuity_boundary_excluded_count for item in children
        ),
        outside_span_count=sum(item.outside_span_count for item in children),
    )


def native_paired_waterfall_source(
    context: AnalysisContext,
    waterfall_products: tuple[UpstreamJsonProduct, ...],
):
    """Build the existing renderer's in-process source from exact native products."""

    from leo.presentation.standard_png import StandardPngPathSource, StandardPngSource

    if context.scope is None or context.scope.kind is not ScopeKind.PAIRED:
        raise ValueError("native paired presentation requires an exact paired scope")
    if (
        len(waterfall_products) != 4
        or tuple(item.producer_node_id for item in waterfall_products)
        != context.dependency_node_ids
    ):
        raise ValueError("native paired presentation requires four authorized path products")
    validated: list[tuple[UpstreamJsonProduct, StandardNativeNumericalWaterfallV3]] = []
    for product in waterfall_products:
        document = StandardNativeNumericalWaterfallV3.model_validate(product.document)
        source = document.source
        scope = product.producer_scope
        if (
            scope.kind is not ScopeKind.RECEIVER_PATH
            or scope.session_id != context.session_id
            or scope.stream_id != source.stream_id
            or scope.receiver_id != source.receiver_id
            or source.session_id != context.session_id
        ):
            raise ValueError("native waterfall presentation received foreign path membership")
        validated.append((product, document))
    validated.sort(
        key=lambda item: (
            item[1].source.stream_id,
            item[1].source.radio_id,
            item[1].source.receiver_id,
        )
    )
    sources = tuple(item[1].source for item in validated)
    if (
        len({(item.stream_id, item.receiver_id) for item in sources}) != 4
        or len({item.manifest_digest for item in sources}) != 1
        or len({item.synchronization_inventory_digest for item in sources}) != 1
        or len({item.sample_rate_hz for item in sources}) != 1
    ):
        raise ValueError("native paired waterfall source inventory is inconsistent")
    origin_utc_ns = min(item.timing.first_estimate_utc_ns for item in sources)
    paths = tuple(
        StandardPngPathSource(
            path_id=f"{document.source.stream_id}:rx{document.source.receiver_id}",
            label=(
                f"{document.source.radio_id} · {document.source.stream_id} · "
                f"RX{document.source.receiver_id} · native evidence only"
            ),
            time_offset_s=(document.source.timing.first_estimate_utc_ns - origin_utc_ns)
            / _NANOSECONDS_PER_SECOND,
            tuned_center_frequency_hz=document.source.tuned_center_frequency_hz,
            sample_rate_hz=document.source.sample_rate_hz,
            receiver_id=document.source.receiver_id,
            waterfall=document.waterfall.model_dump(mode="json"),
            pilot_scan={},
            trajectory_feedback={},
            trajectory_table={},
            cfo_alias_map={},
            dealiased_trajectory_bank={},
            cfo_lift_replay={},
            final_trajectory_bank={},
            final_trajectory_table={},
        )
        for _, document in validated
    )
    return StandardPngSource(
        session_id=context.session_id,
        subject_id="paired-native-evidence-only",
        elapsed_start_s=0.0,
        elapsed_end_s=max(
            path.time_offset_s + source.logical_sample_count / source.sample_rate_hz
            for path, source in zip(paths, sources, strict=True)
        ),
        paths=paths,
    )


def _path_outcome(
    outcome: StageOutcome,
) -> Literal["complete", "partial_coverage"]:
    if outcome not in {StageOutcome.COMPLETE, StageOutcome.PARTIAL_COVERAGE}:
        raise ValueError("native path evidence has no reducible terminal outcome")
    return cast(Literal["complete", "partial_coverage"], outcome.value)


def _status_reason(status: str, *, subject: str) -> str:
    if status == "complete":
        return f"All {subject} have complete contiguous native evidence."
    if status == "partial_coverage":
        return f"At least one of the {subject} has gap or continuity-boundary exclusions."
    return f"The {subject} have no conservative common valid UTC interval."


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


def iter_native_sources(
    documents: Iterable[StandardNativeNumericalWaterfallV3],
) -> tuple[StandardNativeSourceV1, ...]:
    """Expose source extraction for focused presentation contract tests."""

    return tuple(item.source for item in documents)
