"""Pure PNG projections over sealed Standard-native path products."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast

import numpy as np

from leo.analysis.standard.full_capture_glrt20ms import (
    FullCaptureGlrt20msResult,
    WindowResult,
    render_full_capture_glrt20ms_png,
)
from leo.analysis.standard.native_products import (
    CFO_TRAJECTORIES_PNG_V2_PRODUCT,
    DEALIASED_CFO_TRAJECTORIES_PNG_V2_PRODUCT,
    FINAL_CFO_TRAJECTORIES_PNG_V2_PRODUCT,
    PILOT_METHODS_PNG_V2_PRODUCT,
    WATERFALL_PNG_V2_PRODUCT,
)
from leo.analysis.standard.runner import (
    ReceiverStandardConfig,
    receiver_standard_configuration_digest,
)
from leo.analysis.starlink.cfo_dealias import build_final_trajectory_table_v3
from leo.analysis.starlink.pilot_doppler_segments import (
    render_standard_pilot_carrier_tracking_v2_png,
    render_standard_pilot_doppler_segments_png,
    render_standard_pilot_segment_rates_png,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.pilot_doppler_segments import (
    PilotDopplerSegmentV2,
    StandardPilotDopplerSegmentsV2,
)
from leo.contracts.standard_native import StandardNativeNumericalWaterfallV3
from leo.contracts.standard_native_glrt import StandardNativeFullCaptureGlrt20msV1
from leo.contracts.standard_native_path_report import StandardNativePathReportV3
from leo.contracts.standard_native_stateful import NativeSegmentLocalScienceV1
from leo.contracts.standard_native_stateful_v2 import StandardNativeStatefulPathV2
from leo.pipeline import AnalysisContext, ProductSpec, ScopeKind, UpstreamJsonProduct
from leo.presentation.standard_pipeline import StandardViewKindV2
from leo.presentation.standard_png import (
    StandardPngPathSource,
    StandardPngSource,
    render_full_cfo_stage_png,
    render_full_standard_plot_png,
)

_NANOSECONDS_PER_SECOND = 1_000_000_000


def _global_time(value: float, *, offset_s: float) -> float:
    result = float(value) + offset_s
    if not math.isfinite(result) or result < 0:
        raise ValueError("native PNG global time is invalid")
    return result


def _globalize_detection(
    document: dict[str, Any],
    *,
    sample_offset: int,
    time_offset_s: float,
) -> dict[str, Any]:
    return {
        **document,
        "sample_start": int(document["sample_start"]) + sample_offset,
        "time_s": _global_time(float(document["time_s"]), offset_s=time_offset_s),
    }


def _gap_break_detection(*, time_s: float, sample_start: int) -> dict[str, Any]:
    """Create one in-process NaN row that breaks legacy line rendering at a gap."""

    return {
        "status": "insufficient",
        "sample_start": sample_start,
        "time_s": time_s,
        "local_epoch_sample": None,
        "acquired_cfo_hz": None,
        "scores": (),
        "qam_accuracy": None,
        "qam_evm": None,
        "reason": "continuity boundary; no scientific sample",
        "source_candidate_count": 0,
        "truncated_candidate_count": 0,
        "candidates": (),
    }


def _globalize_replay(
    document: dict[str, Any],
    *,
    sample_offset: int,
    time_offset_s: float,
) -> dict[str, Any]:
    return {
        **document,
        "sample_start": int(document["sample_start"]) + sample_offset,
        "time_s": _global_time(float(document["time_s"]), offset_s=time_offset_s),
    }


def _raw_trajectory_table(science: NativeSegmentLocalScienceV1) -> tuple[dict[str, Any], ...]:
    family_by_member = {
        trajectory_id: family.family_id
        for family in science.residual_hough_bank.families
        for trajectory_id in family.member_trajectory_ids
    }
    replayed = {item.trajectory.trajectory_id for item in science.residual_hough_representatives}
    rows: list[dict[str, Any]] = []
    for trajectory in science.residual_hough_bank.trajectories:
        if trajectory.method != "glrt64":
            continue
        deltas = np.asarray(
            [
                item.margin_delta
                for item in science.conditioned_hough_replay
                if item.trajectory_id == trajectory.trajectory_id
                and item.detector_method == "glrt64"
            ],
            dtype=np.float64,
        )
        rows.append(
            {
                "trajectory_id": trajectory.trajectory_id,
                "family_id": family_by_member.get(trajectory.trajectory_id),
                "model": {1: "linear", 2: "quadratic", 3: "cubic"}[trajectory.polynomial_degree],
                "polynomial_degree": trajectory.polynomial_degree,
                "reference_time_s": trajectory.reference_time_s,
                "coefficients_hz": list(trajectory.coefficients_hz),
                "start_s": trajectory.start_s,
                "end_s": trajectory.end_s,
                "duration_s": trajectory.end_s - trajectory.start_s,
                "point_count": trajectory.point_count,
                "residual_rms_hz": trajectory.residual_rms_hz,
                "bic": trajectory.bic,
                "high_gate": trajectory.high_gate,
                "em_iterations": trajectory.em_iterations,
                "fit_matches_well": trajectory.residual_rms_hz <= 2_500.0,
                "selected_for_correction": trajectory.trajectory_id in replayed,
                "corrected_glrt64_probe_count": int(deltas.size),
                "median_glrt64_margin_delta": (float(np.median(deltas)) if deltas.size else None),
            }
        )
    return tuple(rows)


def _globalize_model(document: dict[str, Any], *, offset_s: float) -> dict[str, Any]:
    return {
        **document,
        "reference_time_s": _global_time(float(document["reference_time_s"]), offset_s=offset_s),
        "start_s": _global_time(float(document["start_s"]), offset_s=offset_s),
        "end_s": _global_time(float(document["end_s"]), offset_s=offset_s),
    }


def _globalize_dealiased_branches(
    science: NativeSegmentLocalScienceV1,
    *,
    offset_s: float,
) -> tuple[dict[str, Any], ...]:
    result = []
    for branch in science.dealiased_trajectory_bank.branches:
        document = cast(dict[str, Any], branch.model_dump(mode="json"))
        if "model" in document:
            document["model"] = _globalize_model(
                cast(dict[str, Any], document["model"]), offset_s=offset_s
            )
        if "models" in document:
            document["models"] = tuple(
                _globalize_model(cast(dict[str, Any], item), offset_s=offset_s)
                for item in cast(list[dict[str, Any]], document["models"])
            )
        document["start_s"] = _global_time(float(document["start_s"]), offset_s=offset_s)
        document["end_s"] = _global_time(float(document["end_s"]), offset_s=offset_s)
        result.append(document)
    return tuple(result)


def _globalize_final_rows(
    science: NativeSegmentLocalScienceV1,
    *,
    offset_s: float,
) -> tuple[dict[str, Any], ...]:
    table = build_final_trajectory_table_v3(science.final_trajectory_bank)
    return tuple(
        _globalize_model(cast(dict[str, Any], item), offset_s=offset_s)
        for item in table.model_dump(mode="json")["trajectories"]
    )


def _path_source(
    waterfall: StandardNativeNumericalWaterfallV3,
    stateful: StandardNativeStatefulPathV2,
    report: StandardNativePathReportV3,
    *,
    config: ReceiverStandardConfig,
    origin_utc_ns: int,
) -> StandardPngPathSource:
    source = stateful.source
    detections: list[dict[str, Any]] = []
    replay: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    dealiased_branches: list[dict[str, Any]] = []
    final_rows: list[dict[str, Any]] = []
    alias_map: dict[str, Any] | None = None
    for segment in stateful.segments:
        science = segment.local_science
        if science is None:
            continue
        offset_samples = segment.global_device_sample_start
        offset_s = offset_samples / source.sample_rate_hz
        if detections:
            detections.append(_gap_break_detection(time_s=offset_s, sample_start=offset_samples))
        detections.extend(
            _globalize_detection(
                cast(dict[str, Any], item.model_dump(mode="json")),
                sample_offset=offset_samples,
                time_offset_s=offset_s,
            )
            for item in science.detections
        )
        replay.extend(
            _globalize_replay(
                cast(dict[str, Any], item.model_dump(mode="json")),
                sample_offset=offset_samples,
                time_offset_s=offset_s,
            )
            for item in science.conditioned_hough_replay
        )
        raw_rows.extend(
            _globalize_model(item, offset_s=offset_s) for item in _raw_trajectory_table(science)
        )
        dealiased_branches.extend(_globalize_dealiased_branches(science, offset_s=offset_s))
        final_rows.extend(_globalize_final_rows(science, offset_s=offset_s))
        if alias_map is None:
            alias_map = cast(dict[str, Any], science.cfo_alias_map.model_dump(mode="json"))
        elif (
            alias_map["alias_spacing_numerator_hz"],
            alias_map["alias_spacing_denominator"],
        ) != (
            science.cfo_alias_map.alias_spacing_numerator_hz,
            science.cfo_alias_map.alias_spacing_denominator,
        ):
            raise ValueError("native PNG source changed alias spacing between segments")
    sample_rate_hz = source.sample_rate_hz
    return StandardPngPathSource(
        path_id=f"{source.stream_id}:rx{source.receiver_id}",
        label=f"{source.radio_id} · {source.stream_id} · RX{source.receiver_id}",
        time_offset_s=(source.timing.first_estimate_utc_ns - origin_utc_ns)
        / _NANOSECONDS_PER_SECOND,
        tuned_center_frequency_hz=source.tuned_center_frequency_hz,
        sample_rate_hz=sample_rate_hz,
        receiver_id=source.receiver_id,
        waterfall=waterfall.waterfall.model_dump(mode="json"),
        pilot_scan={
            "coarse_window_samples": sample_rate_hz,
            "subwindow_samples": (sample_rate_hz * config.feedback.subwindow_ms // 1_000),
            "probe_samples": sample_rate_hz * config.feedback.probe_ms // 1_000,
            "detections": tuple(detections),
        },
        trajectory_feedback={"results": tuple(replay)},
        trajectory_table={"trajectories": tuple(raw_rows)},
        cfo_alias_map=alias_map
        or {
            "alias_spacing_numerator_hz": 2_500_000,
            "alias_spacing_denominator": 11,
        },
        dealiased_trajectory_bank={"branches": tuple(dealiased_branches)},
        cfo_lift_replay={},
        final_trajectory_bank={
            "trajectories": tuple(
                trajectory
                for segment in report.segments
                for trajectory in segment.final_trajectories
            )
        },
        final_trajectory_table={"trajectories": tuple(final_rows)},
    )


def _clip_model_rows(
    rows: tuple[dict[str, Any], ...],
    *,
    path_offset_s: float,
    intervals: tuple[tuple[float, float], ...],
) -> tuple[dict[str, Any], ...]:
    clipped: list[dict[str, Any]] = []
    for row in rows:
        global_start = path_offset_s + float(row["start_s"])
        global_stop = path_offset_s + float(row["end_s"])
        for allowed_start, allowed_stop in intervals:
            start = max(global_start, allowed_start)
            stop = min(global_stop, allowed_stop)
            if start < stop:
                clipped.append(
                    {
                        **row,
                        "start_s": start - path_offset_s,
                        "end_s": stop - path_offset_s,
                    }
                )
    return tuple(clipped)


def _restrict_path_to_common_intervals(
    path: StandardPngPathSource,
    *,
    intervals: tuple[tuple[float, float], ...],
) -> StandardPngPathSource:
    def point_is_valid(time_s: float) -> bool:
        global_time = path.time_offset_s + time_s
        return any(start <= global_time < stop for start, stop in intervals)

    waterfall = dict(path.waterfall)
    tiles = []
    for item in cast(tuple[dict[str, Any], ...], tuple(waterfall["tiles"])):
        start = path.time_offset_s + int(item["sample_start"]) / path.sample_rate_hz
        stop = path.time_offset_s + int(item["sample_stop"]) / path.sample_rate_hz
        fully_valid = any(left <= start and stop <= right for left, right in intervals)
        if fully_valid:
            tiles.append(item)
        else:
            matrix = cast(tuple[tuple[float | None, ...], ...], item["receiver_power_dbfs"])
            tiles.append(
                {
                    **item,
                    "transform_count": 0,
                    "receiver_power_dbfs": tuple(tuple(None for _ in row) for row in matrix),
                }
            )
    waterfall["tiles"] = tuple(tiles)
    detections = tuple(
        item
        for item in cast(tuple[dict[str, Any], ...], path.pilot_scan["detections"])
        if point_is_valid(float(item["time_s"]))
    )
    replay = tuple(
        item
        for item in cast(tuple[dict[str, Any], ...], path.trajectory_feedback["results"])
        if point_is_valid(float(item["time_s"]))
    )
    raw_rows = _clip_model_rows(
        cast(tuple[dict[str, Any], ...], path.trajectory_table["trajectories"]),
        path_offset_s=path.time_offset_s,
        intervals=intervals,
    )
    dealiased_branches: list[dict[str, Any]] = []
    for branch in cast(tuple[dict[str, Any], ...], path.dealiased_trajectory_bank["branches"]):
        if "model" in branch:
            selected = cast(dict[str, Any], branch["model"])
        else:
            selected = next(
                item
                for item in cast(tuple[dict[str, Any], ...], tuple(branch["models"]))
                if item["model_id"] == branch["selected_model_id"]
            )
        for model in _clip_model_rows(
            (selected,),
            path_offset_s=path.time_offset_s,
            intervals=intervals,
        ):
            if "model" in branch:
                dealiased_branches.append({**branch, "model": model})
            else:
                dealiased_branches.append({**branch, "models": (model,)})
    final_rows = _clip_model_rows(
        cast(tuple[dict[str, Any], ...], path.final_trajectory_table["trajectories"]),
        path_offset_s=path.time_offset_s,
        intervals=intervals,
    )
    return replace(
        path,
        waterfall=waterfall,
        pilot_scan={**path.pilot_scan, "detections": detections},
        trajectory_feedback={**path.trajectory_feedback, "results": replay},
        trajectory_table={"trajectories": raw_rows},
        dealiased_trajectory_bank={"branches": tuple(dealiased_branches)},
        final_trajectory_table={"trajectories": final_rows},
    )


def native_standard_png_source(
    context: AnalysisContext,
    *,
    waterfall_products: tuple[UpstreamJsonProduct, ...],
    stateful_products: tuple[UpstreamJsonProduct, ...],
    path_report_products: tuple[UpstreamJsonProduct, ...],
    config: ReceiverStandardConfig,
    configs_by_sample_rate_hz: Mapping[int, ReceiverStandardConfig] | None = None,
    valid_utc_intervals: tuple[tuple[int, int], ...] | None = None,
) -> StandardPngSource:
    """Build one legacy-compatible plot source from exact sealed native path products."""

    expected_count = {
        ScopeKind.RECEIVER_PATH: 1,
        ScopeKind.RADIO: 2,
        ScopeKind.PAIRED: 4,
    }
    if context.scope is None or context.scope.kind not in expected_count:
        raise ValueError("native PNG projection requires path, radio, or paired scope")
    inventories = (waterfall_products, stateful_products, path_report_products)
    node_ids = tuple(item.producer_node_id for item in waterfall_products)
    if (
        len(node_ids) != expected_count[context.scope.kind]
        or len(set(node_ids)) != len(node_ids)
        or any(
            tuple(item.producer_node_id for item in values) != node_ids for values in inventories
        )
        or not set(node_ids) <= set(context.dependency_node_ids)
    ):
        raise ValueError("native PNG projection path inventory is not exact")
    validated = []
    configurations = {
        config.replay_gate.sample_rate_hz: config,
        **({} if configs_by_sample_rate_hz is None else configs_by_sample_rate_hz),
    }
    for waterfall_item, stateful_item, report_item in zip(*inventories, strict=True):
        if not (
            waterfall_item.producer_scope
            == stateful_item.producer_scope
            == report_item.producer_scope
        ):
            raise ValueError("native PNG products disagree on producer scope")
        producer_scope = waterfall_item.producer_scope
        waterfall = StandardNativeNumericalWaterfallV3.model_validate(waterfall_item.document)
        stateful = StandardNativeStatefulPathV2.model_validate(stateful_item.document)
        report = StandardNativePathReportV3.model_validate(report_item.document)
        source = stateful.source
        path_config = configurations.get(source.sample_rate_hz)
        if (
            waterfall.source != source
            or report.source != source
            or report.products.numerical_waterfall_product_digest != waterfall_item.product_digest
            or report.products.stateful_path_product_digest != stateful_item.product_digest
            or producer_scope.kind is not ScopeKind.RECEIVER_PATH
            or producer_scope.session_id != context.session_id
            or (producer_scope.stream_id, producer_scope.receiver_id)
            != (source.stream_id, source.receiver_id)
            or path_config is None
            or stateful.science_configuration_digest
            != receiver_standard_configuration_digest(path_config)
        ):
            raise ValueError("native PNG source authority does not close")
        if context.scope.kind is ScopeKind.RADIO and (
            source.stream_id != context.scope.stream_id or source.radio_id != context.scope.radio_id
        ):
            raise ValueError("native radio PNG received foreign path")
        validated.append((waterfall, stateful, report, path_config))
    validated.sort(key=lambda item: (item[1].source.stream_id, item[1].source.receiver_id))
    sources = tuple(item[1].source for item in validated)
    if (
        len({item.path_input_binding_digest for item in sources}) != len(sources)
        or len({item.manifest_digest for item in sources}) != 1
        or len({item.synchronization_inventory_digest for item in sources}) != 1
    ):
        raise ValueError("native PNG source inventory is inconsistent")
    origin_utc_ns = min(item.timing.first_estimate_utc_ns for item in sources)
    paths = tuple(
        _path_source(
            waterfall,
            stateful,
            report,
            config=path_config,
            origin_utc_ns=origin_utc_ns,
        )
        for waterfall, stateful, report, path_config in validated
    )
    if valid_utc_intervals is not None:
        relative_intervals = tuple(
            (
                (start - origin_utc_ns) / _NANOSECONDS_PER_SECOND,
                (stop - origin_utc_ns) / _NANOSECONDS_PER_SECOND,
            )
            for start, stop in valid_utc_intervals
        )
        paths = tuple(
            _restrict_path_to_common_intervals(path, intervals=relative_intervals) for path in paths
        )
    if context.scope.kind is ScopeKind.RECEIVER_PATH:
        subject_id = f"{context.scope.stream_id}:rx{context.scope.receiver_id}"
    elif context.scope.kind is ScopeKind.RADIO:
        subject_id = f"{context.scope.stream_id}:{context.scope.radio_id}"
    else:
        subject_id = "paired-standard-native"
    return StandardPngSource(
        session_id=context.session_id,
        subject_id=subject_id,
        elapsed_start_s=0.0,
        elapsed_end_s=max(
            path.time_offset_s + source.logical_sample_count / source.sample_rate_hz
            for path, source in zip(paths, sources, strict=True)
        ),
        paths=paths,
    )


def render_standard_native_common_pngs(
    source: StandardPngSource,
) -> tuple[tuple[ProductSpec, bytes], ...]:
    """Render the five common Standard views from one sealed native source."""

    return (
        (
            WATERFALL_PNG_V2_PRODUCT,
            render_full_standard_plot_png(source, StandardViewKindV2.WATERFALL),
        ),
        (
            PILOT_METHODS_PNG_V2_PRODUCT,
            render_full_standard_plot_png(source, StandardViewKindV2.GLRT64),
        ),
        (
            CFO_TRAJECTORIES_PNG_V2_PRODUCT,
            render_full_standard_plot_png(
                source,
                StandardViewKindV2.CFO_TRAJECTORY,
                show_legend=False,
            ),
        ),
        (
            DEALIASED_CFO_TRAJECTORIES_PNG_V2_PRODUCT,
            render_full_cfo_stage_png(source, stage="dealiased"),
        ),
        (
            FINAL_CFO_TRAJECTORIES_PNG_V2_PRODUCT,
            render_full_cfo_stage_png(source, stage="final"),
        ),
    )


def _native_glrt_runtime_result(
    product: StandardNativeFullCaptureGlrt20msV1,
    config: ReceiverStandardConfig,
) -> FullCaptureGlrt20msResult:
    windows = tuple(
        WindowResult(
            probe_index=window.opportunity_index,
            sample_start=window.global_device_sample_start,
            start_time_s=window.global_start_time_s,
            center_time_s=window.global_center_time_s,
            end_time_s=window.global_end_time_s,
            acquisition_status=window.acquisition_status,
            candidate_count=window.candidate_count,
            best_candidate_rank=window.best_candidate_rank,
            epoch_sample=window.global_epoch_device_sample,
            acquired_cfo_hz=window.acquired_cfo_hz,
            residual_cfo_hz=window.residual_cfo_hz,
            tracking_cfo_hz=window.tracking_cfo_hz,
            glrt_exact_score=window.glrt_exact_score,
            glrt_control_score=window.glrt_control_score,
            glrt_margin=window.glrt_margin,
            passed_margin_gate=window.passed_margin_gate,
            lattice_frame_count=window.lattice_frame_count,
            measured_frame_count=window.measured_frame_count,
            robust_line_available=window.robust_line_available,
            robust_reference_time_s=window.global_robust_reference_time_s,
            robust_cfo_at_reference_hz=window.robust_cfo_at_reference_hz,
            robust_slope_hz_s=window.robust_slope_hz_s,
            robust_slope_sigma_hz_s=window.robust_slope_sigma_hz_s,
            robust_residual_rms_hz=window.robust_residual_rms_hz,
            robust_median_absolute_residual_hz=(window.robust_median_absolute_residual_hz),
            robust_mad_scale_hz=window.robust_mad_scale_hz,
            robust_outlier_count=window.robust_outlier_count,
            robust_converged=window.robust_converged,
            reason=window.reason,
        )
        for segment in product.segments
        for window in segment.windows
    )
    tracks = tuple(
        {
            "track_label": (
                f"segment {segment.continuity_segment.segment_index} · {track.track_label}"
            ),
            "reference_time_s": track.global_reference_time_s,
            "start_s": track.global_start_time_s,
            "end_s": track.global_end_time_s,
            "slope_hz_s": track.slope_hz_s,
            "cfo_at_reference_hz": track.cfo_at_reference_hz,
            "observation_count": track.observation_count,
            "observations": tuple(
                {
                    "time_s": observation.global_time_s,
                    "raw_cfo_hz": observation.raw_cfo_hz,
                    "alias_index": observation.alias_index,
                }
                for observation in track.observations
            ),
        }
        for segment in product.segments
        for track in segment.hough.tracks
    )
    segment_rates = tuple(
        {
            "segment_index": segment.continuity_segment.segment_index,
            "start_s": summary.global_start_time_s,
            "end_s": summary.global_end_time_s,
            "constant_doppler_rate_hz_s": summary.constant_doppler_rate_hz_s,
            "point_count": summary.point_count,
        }
        for segment in product.segments
        if (summary := segment.constant_rate) is not None
    )
    return FullCaptureGlrt20msResult(
        windows=windows,
        hough_analysis={
            "tracks": tracks,
            "dealias_config": {
                "alias_spacing_hz": config.dealias.alias_spacing_hz,
                "continuity_gap_s": config.dealias.continuity_gap_s,
            },
            "segment_constant_rates": segment_rates,
        },
        constant_doppler_rate=None,
        status_note=(
            f"{product.accounting.analyzed_count}/{product.accounting.scheduled_count} "
            "globally scheduled windows analyzed; excluded windows overlap gaps or resets"
        ),
    )


def render_standard_native_full_capture_glrt_png(
    product: StandardNativeFullCaptureGlrt20msV1,
    *,
    config: ReceiverStandardConfig,
    path_label: str,
) -> bytes:
    """Render the global native schedule while retaining every segment-local fit."""

    return render_full_capture_glrt20ms_png(
        _native_glrt_runtime_result(product, config),
        session_id=product.source.session_id,
        path_label=path_label,
        config=config.full_capture_glrt20ms,
    )


def _global_pilot_doppler_segments(
    stateful: StandardNativeStatefulPathV2,
    *,
    config: ReceiverStandardConfig,
) -> StandardPilotDopplerSegmentsV2:
    segments: list[PilotDopplerSegmentV2] = []
    for outer in stateful.segments:
        science = outer.local_science
        if science is None:
            continue
        local = science.pilot_doppler_segments
        if local.config != config.pilot_doppler_segments:
            raise ValueError("native pilot Doppler plot policy does not match release config")
        offset_s = outer.global_device_sample_start / stateful.source.sample_rate_hz
        for locklet in local.segments:
            identity = canonical_digest(
                {
                    "kind": "standard-native-global-pilot-locklet-trajectory-v1",
                    "continuity_segment_index": outer.continuity_segment_index,
                    "source_trajectory_id": locklet.source_trajectory_id,
                }
            )
            branch_identity = canonical_digest(
                {
                    "kind": "standard-native-global-pilot-locklet-branch-v1",
                    "continuity_segment_index": outer.continuity_segment_index,
                    "source_branch_id": locklet.source_branch_id,
                }
            )
            segments.append(
                locklet.model_copy(
                    update={
                        "segment_index": len(segments),
                        "source_trajectory_id": identity,
                        "source_branch_id": branch_identity,
                        "source_probe_sample_start": (
                            locklet.source_probe_sample_start + outer.global_device_sample_start
                        ),
                        "start_time_s": locklet.start_time_s + offset_s,
                        "end_time_s": locklet.end_time_s + offset_s,
                        "reference_time_s": locklet.reference_time_s + offset_s,
                    }
                )
            )
    return StandardPilotDopplerSegmentsV2.model_construct(
        schema_version=2,
        algorithm_version="standard-pilot-doppler-segments-v2",
        path_input_binding_digest=stateful.source.path_input_binding_digest,
        pilot_scan_digest=canonical_digest(
            {
                "kind": "standard-native-global-pilot-scan-display-v1",
                "stateful_path_digest": stateful.stateful_path_digest,
            }
        ),
        dealiased_bank_digest=stateful.stateful_path_digest,
        final_trajectory_bank_digest=stateful.stateful_path_digest,
        kalman_tracking_digest=stateful.stateful_path_digest,
        config=config.pilot_doppler_segments,
        config_digest=config.pilot_doppler_segments.digest,
        source_track_count=len(segments),
        analyzed_track_count=len(segments),
        truncated_track_count=0,
        candidate_window_count=len(segments),
        analyzed_segment_count=len(segments),
        qualified_segment_count=sum(item.qualified for item in segments),
        trajectory_summaries=(),
        segments=tuple(segments),
        status="complete" if segments else "insufficient",
        reason=(
            "Segment-local native pilot Doppler evidence projected on the global axis."
            if segments
            else "No analyzed segment contains pilot Doppler evidence."
        ),
        content_digest=stateful.stateful_path_digest,
    )


def render_standard_native_pilot_diagnostics_pngs(
    stateful: StandardNativeStatefulPathV2,
    *,
    config: ReceiverStandardConfig,
    path_label: str,
) -> tuple[bytes, bytes, bytes]:
    """Render the three pilot views without joining reset-local carrier state."""

    product = _global_pilot_doppler_segments(stateful, config=config)
    arguments = {"session_id": stateful.source.session_id, "path_label": path_label}
    return (
        render_standard_pilot_doppler_segments_png(product, **arguments),
        render_standard_pilot_carrier_tracking_v2_png(product, **arguments),
        render_standard_pilot_segment_rates_png(product, **arguments),
    )
