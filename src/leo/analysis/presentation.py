"""Immutable bounded presentation products for whole-dwell scientific results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol, cast

from pydantic import JsonValue

from leo.analysis.controls import ControlResult, ScientificSummary
from leo.analysis.doppler import DopplerFitResult, TleAssociationResult
from leo.analysis.graphs import ComputeTier
from leo.analysis.starlink import NumericalStatus
from leo.analysis.starlink.long_dwell import (
    ActivityTrackingResult,
    CandidateCloudResult,
    QamHandoffResult,
    SparseSurveyResult,
)
from leo.analysis.waterfall import WaterfallResult
from leo.pipeline import (
    AnalysisContext,
    IqReader,
    OutputSink,
    ProductReader,
    ProductRole,
    ProductSpec,
    ResourceClass,
    StageOutcome,
    StageResult,
    StageSpec,
)


@dataclass(frozen=True, slots=True)
class WholeDwellPresentationBundle:
    compute_tier: ComputeTier
    recording_digest: str
    pipeline_config_digest: str
    receiver_tuned_center_hz: float
    waterfall: WaterfallResult
    survey: SparseSurveyResult
    cloud: CandidateCloudResult
    tracks: ActivityTrackingResult
    doppler: DopplerFitResult
    qam: QamHandoffResult
    controls: ControlResult
    tle: TleAssociationResult
    summary: ScientificSummary


class WholeDwellBundleProvider(Protocol):
    def build(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
    ) -> WholeDwellPresentationBundle: ...


class WholeDwellPresentationAnalyzer:
    """Publish compact products without coupling science to storage or HTTP."""

    WATERFALL: ClassVar[ProductSpec] = ProductSpec(
        kind="waterfall.presentation",
        role=ProductRole.PRESENTATION,
    )
    DETECTION: ClassVar[ProductSpec] = ProductSpec(
        kind="detection.presentation",
        role=ProductRole.PRESENTATION,
    )
    QAM: ClassVar[ProductSpec] = ProductSpec(
        kind="qam.presentation",
        role=ProductRole.PRESENTATION,
    )
    DOPPLER: ClassVar[ProductSpec] = ProductSpec(
        kind="doppler.presentation",
        role=ProductRole.PRESENTATION,
    )
    CONTROLS: ClassVar[ProductSpec] = ProductSpec(
        kind="controls.presentation",
        role=ProductRole.PRESENTATION,
    )
    OVERLAYS: ClassVar[ProductSpec] = ProductSpec(
        kind="overlays.presentation",
        role=ProductRole.PRESENTATION,
    )
    PROVENANCE: ClassVar[ProductSpec] = ProductSpec(
        kind="provenance.presentation",
        role=ProductRole.PRESENTATION,
    )
    CARRIER_TIMING: ClassVar[ProductSpec] = ProductSpec(
        kind="carrier-timing.presentation",
        role=ProductRole.PRESENTATION,
    )
    QAM_TIMELINE: ClassVar[ProductSpec] = ProductSpec(
        kind="qam-timeline.presentation",
        role=ProductRole.PRESENTATION,
    )
    ANALYSIS_STAGE_TIMELINE: ClassVar[ProductSpec] = ProductSpec(
        kind="analysis-stage-timeline.presentation",
        role=ProductRole.PRESENTATION,
    )
    spec: ClassVar[StageSpec] = StageSpec(
        key="whole-dwell-present",
        algorithm_version="1.0.0",
        configuration_schema="whole-dwell-presentation.v1",
        output_products=(
            WATERFALL,
            DETECTION,
            QAM,
            DOPPLER,
            CONTROLS,
            OVERLAYS,
            PROVENANCE,
            CARRIER_TIMING,
            QAM_TIMELINE,
            ANALYSIS_STAGE_TIMELINE,
        ),
        resource_class=ResourceClass.CPU,
        deterministic=True,
    )

    def __init__(self, provider: WholeDwellBundleProvider) -> None:
        self._provider = provider

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        bundle = self._provider.build(context, iq, products)
        documents = whole_dwell_presentation_documents(context.run_id, bundle)
        published = tuple(
            outputs.publish_json(product, documents[product.kind])
            for product in self.spec.output_products
        )
        coverage = bundle.waterfall.coverage.observed_fraction
        if bundle.waterfall.coverage.observed_samples == 0:
            outcome = StageOutcome.INSUFFICIENT_DATA
            message = "whole-dwell presentation has no observed IQ coverage"
        elif coverage < 1.0:
            outcome = StageOutcome.PARTIAL_COVERAGE
            message = "whole-dwell presentation covers only part of the declared IQ span"
        elif bundle.survey.status is NumericalStatus.INSUFFICIENT:
            outcome = StageOutcome.INSUFFICIENT_DATA
            message = bundle.survey.reason
        elif bundle.cloud.status is NumericalStatus.NO_RESULT:
            outcome = StageOutcome.NO_RESULT
            message = "bounded survey produced no candidate cloud"
        else:
            outcome = StageOutcome.COMPLETE
            message = None
        metrics = _qam_metrics(bundle.qam)
        best_cfo = (
            max(
                bundle.cloud.candidates,
                key=lambda item: item.observation.verify_minus_control_margin,
            ).observation.absolute_cfo_hz
            if bundle.cloud.candidates
            else None
        )
        return StageResult(
            outcome=outcome,
            products=published,
            summary={
                "coverage_fraction": coverage,
                "candidate_count": len(bundle.cloud.candidates),
                "best_qam_accuracy": (max(item[1] for item in metrics) if metrics else None),
                "best_cfo_hz": best_cfo,
                "doppler_slope_hz_s": bundle.doppler.slope_hz_s,
                "compute_tier": bundle.compute_tier.value,
                "scientific_confidence": bundle.controls.confidence.value,
            },
            message=message,
        )


def whole_dwell_presentation_documents(
    run_id: str,
    bundle: WholeDwellPresentationBundle,
) -> dict[str, dict[str, JsonValue]]:
    """Project bounded documents; large numerical arrays are deliberately absent."""

    candidate_track = {
        candidate_id: track.track_id
        for track in bundle.tracks.tracks
        for candidate_id in track.candidate_ids
    }
    candidates: list[dict[str, JsonValue]] = [
        {
            "candidate_id": item.candidate_id,
            "receiver_key": str(item.observation.receiver_id),
            "time_s": item.observation.absolute_epoch_sample / bundle.waterfall.sample_rate_hz,
            "absolute_epoch_sample": item.observation.absolute_epoch_sample,
            "search_residual_cfo_hz": item.observation.residual_cfo_hz,
            "baseband_cfo_hz": item.observation.absolute_cfo_hz,
            "receiver_tuned_center_hz": bundle.receiver_tuned_center_hz,
            "tuned_signal_frequency_hz": (
                bundle.receiver_tuned_center_hz + item.observation.absolute_cfo_hz
            ),
            "verify_score": item.observation.verify_score,
            "control_score": item.observation.control_score,
            "margin": item.observation.verify_minus_control_margin,
            "rank_within_search": item.observation.rank_within_search,
            "track_id": candidate_track.get(item.candidate_id),
            "calibration_digest": item.observation.receiver_calibration_sha256,
            "parent_survey_config_digest": _bare_digest(item.parent_survey_config_digest),
        }
        for item in bundle.cloud.candidates[:256]
    ]
    detection: dict[str, JsonValue] = {
        "schema_version": 1,
        "run_id": run_id,
        "compute_tier": bundle.compute_tier.value,
        "confidence": bundle.controls.confidence.value,
        "confidence_reason": bundle.controls.reason,
        "known_pilot_candidate": bool(bundle.cloud.candidates),
        "calibrated_detection": bundle.controls.confidence.value == "qualified",
        "candidate_count": len(bundle.cloud.candidates),
        "returned_candidate_count": len(candidates),
        "candidate_lineage_truncated": len(candidates) < len(bundle.cloud.candidates),
        "candidate_coverage": {
            "scheduled_windows": bundle.survey.coverage.scheduled_window_count,
            "complete_windows": bundle.survey.coverage.complete_window_count,
            "searched_receiver_windows": bundle.survey.coverage.searched_receiver_window_count,
            "searched_samples": bundle.survey.coverage.searched_sample_count,
            "searched_time_fraction": bundle.survey.coverage.time_sample_fraction,
            "residual_cfo_min_hz": bundle.survey.coverage.residual_cfo_min_hz,
            "residual_cfo_max_hz": bundle.survey.coverage.residual_cfo_max_hz,
            "survey_config_digest": _bare_digest(bundle.survey.config_digest),
        },
        "candidates": cast(JsonValue, candidates),
    }
    receiver_metrics = [
        {
            "receiver_key": str(receiver_id),
            "candidate_epoch_sample": epoch_sample,
            "baseband_cfo_hz": result.absolute_cfo_hz,
            "residual_cfo_refinement_hz": result.residual_cfo_refinement_hz,
            "receiver_tuned_center_hz": bundle.receiver_tuned_center_hz,
            "tuned_signal_frequency_hz": (
                None
                if result.absolute_cfo_hz is None
                else bundle.receiver_tuned_center_hz + result.absolute_cfo_hz
            ),
            "accuracy": metrics.hard_symbol_accuracy,
            "rms_evm": metrics.rms_evm,
            "frame_count": metrics.frame_count,
            "noise_variance": metrics.noise_variance,
        }
        for receiver_id, epoch_sample, result in zip(
            bundle.qam.receiver_ids,
            bundle.qam.receiver_epoch_samples,
            bundle.qam.receiver_results,
            strict=True,
        )
        if (metrics := result.metrics) is not None
    ]
    combined = None if bundle.qam.combined is None else bundle.qam.combined.metrics
    qam: dict[str, JsonValue] = {
        "schema_version": 1,
        "run_id": run_id,
        "state": bundle.qam.status.value,
        "known_symbols_only": True,
        "candidate_only": True,
        "combined_accuracy": None if combined is None else combined.hard_symbol_accuracy,
        "combined_rms_evm": None if combined is None else combined.rms_evm,
        "combined_frame_count": None if combined is None else combined.frame_count,
        "receiver_metrics": cast(JsonValue, receiver_metrics),
        "reason": bundle.qam.reason,
    }
    doppler: dict[str, JsonValue] = {
        "schema_version": 1,
        "run_id": run_id,
        "state": bundle.doppler.status.value,
        "confidence": bundle.doppler.confidence.value,
        "motion_class": bundle.doppler.motion_class.value,
        "baseband_cfo_at_reference_hz": bundle.doppler.frequency_at_reference_hz,
        "receiver_tuned_center_hz": bundle.receiver_tuned_center_hz,
        "tuned_signal_frequency_at_reference_hz": (
            None
            if bundle.doppler.frequency_at_reference_hz is None
            else bundle.receiver_tuned_center_hz + bundle.doppler.frequency_at_reference_hz
        ),
        "slope_hz_s": bundle.doppler.slope_hz_s,
        "acceleration_hz_s2": bundle.doppler.acceleration_hz_s2,
        "residual_rms_hz": bundle.doppler.residual_rms_hz,
        "point_count": bundle.doppler.point_count,
        "time_coverage_s": bundle.doppler.time_coverage_s,
        "tle": {
            "status": bundle.tle.status.value,
            "object_id": bundle.tle.object_id,
            "frequency_residual_hz": bundle.tle.frequency_residual_hz,
            "slope_residual_hz_s": bundle.tle.slope_residual_hz_s,
            "candidate_only": bundle.tle.candidate_only,
            "reason": bundle.tle.reason,
        },
        "reason": bundle.doppler.reason,
    }
    controls: dict[str, JsonValue] = {
        "schema_version": 1,
        "run_id": run_id,
        "state": bundle.controls.status.value,
        "confidence": bundle.controls.confidence.value,
        "thresholds_calibrated": bundle.controls.thresholds_calibrated,
        "specificity_claimed": bundle.controls.specificity_claimed,
        "passed_candidate_count": sum(
            item.passed_research_gate for item in bundle.controls.evidence
        ),
        "best_held_out_margin": max(
            (item.held_out_margin for item in bundle.controls.evidence), default=None
        ),
        "best_surrogate_margin": max(
            (item.surrogate_margin for item in bundle.controls.evidence), default=None
        ),
        "reasons": cast(
            JsonValue,
            sorted({reason for item in bundle.controls.evidence for reason in item.reasons}),
        ),
        "reason": bundle.controls.reason,
    }
    waterfall = _waterfall_document(run_id, bundle.waterfall)
    overlays = _overlay_document(run_id, candidates, bundle.doppler)
    provenance: dict[str, JsonValue] = {
        "schema_version": 1,
        "run_id": run_id,
        "recording_digest": _bare_digest(bundle.recording_digest),
        "pipeline_config_digest": _bare_digest(bundle.pipeline_config_digest),
        "compute_tier": bundle.compute_tier.value,
        "config_digests": [_bare_digest(value) for value in bundle.summary.lineage_config_digests],
        "algorithm_versions": [
            bundle.waterfall.algorithm_version,
            bundle.survey.algorithm_version,
            "candidate-cloud-v1",
            "activity-track-v1",
            "doppler-fit-v1",
            "known-pilot-qam-v1",
            "candidate-controls-v1",
        ],
        "limitation_codes": list(bundle.summary.notes),
    }
    documents = {
        WholeDwellPresentationAnalyzer.WATERFALL.kind: waterfall,
        WholeDwellPresentationAnalyzer.DETECTION.kind: detection,
        WholeDwellPresentationAnalyzer.QAM.kind: qam,
        WholeDwellPresentationAnalyzer.DOPPLER.kind: doppler,
        WholeDwellPresentationAnalyzer.CONTROLS.kind: controls,
        WholeDwellPresentationAnalyzer.OVERLAYS.kind: overlays,
        WholeDwellPresentationAnalyzer.PROVENANCE.kind: provenance,
    }
    documents.update(whole_dwell_timeline_documents(run_id, bundle))
    return documents


def whole_dwell_timeline_documents(
    run_id: str,
    bundle: WholeDwellPresentationBundle,
) -> dict[str, dict[str, JsonValue]]:
    """Project only time evidence present in the current whole-dwell bundle.

    QAM currently yields one aggregate result for each selected receiver window,
    not per-window samples across the dwell.  Stage execution/signal-time events
    are not carried by this bundle.  Both limitations are explicit in the
    returned documents so clients cannot mistake sparse evidence for a curve.
    """

    source_candidates = bundle.cloud.candidates
    returned_candidates = source_candidates[:256]
    candidate_track = {
        candidate_id: track.track_id
        for track in bundle.tracks.tracks
        for candidate_id in track.candidate_ids
    }
    fit_source_ids = set(bundle.doppler.source_candidate_ids)
    fit_available = (
        bundle.doppler.status is NumericalStatus.COMPLETE
        and bundle.doppler.reference_time_s is not None
        and bundle.doppler.frequency_at_reference_hz is not None
        and bundle.doppler.slope_hz_s is not None
        and bundle.doppler.acceleration_hz_s2 is not None
    )
    carrier_points: list[dict[str, JsonValue]] = []
    for item in returned_candidates:
        time_s = item.observation.absolute_epoch_sample / bundle.waterfall.sample_rate_hz
        fitted_cfo_hz: float | None = None
        if fit_available:
            assert bundle.doppler.reference_time_s is not None
            assert bundle.doppler.frequency_at_reference_hz is not None
            assert bundle.doppler.slope_hz_s is not None
            assert bundle.doppler.acceleration_hz_s2 is not None
            delta_s = time_s - bundle.doppler.reference_time_s
            fitted_cfo_hz = (
                bundle.doppler.frequency_at_reference_hz
                + bundle.doppler.slope_hz_s * delta_s
                + 0.5 * bundle.doppler.acceleration_hz_s2 * delta_s**2
            )
        carrier_points.append(
            {
                "candidate_id": item.candidate_id,
                "track_id": candidate_track.get(item.candidate_id),
                "receiver_key": str(item.observation.receiver_id),
                "time_s": time_s,
                "absolute_epoch_sample": item.observation.absolute_epoch_sample,
                "observed_baseband_cfo_hz": item.observation.absolute_cfo_hz,
                "fitted_baseband_cfo_hz": fitted_cfo_hz,
                "verify_minus_control_margin": item.observation.verify_minus_control_margin,
                "used_by_doppler_fit": item.candidate_id in fit_source_ids,
            }
        )
    if carrier_points:
        carrier_state = "available" if fit_available else "partial"
        carrier_reason = (
            "observed candidate CFO and Doppler fit evaluated at observed timestamps"
            if fit_available
            else "observed candidate CFO is available; Doppler fit is unavailable"
        )
    else:
        carrier_state = "unavailable"
        carrier_reason = "no candidate carrier observations are available"
    carrier: dict[str, JsonValue] = {
        "schema_version": 1,
        "run_id": run_id,
        "state": carrier_state,
        "time_unit": "s",
        "frequency_unit": "Hz",
        "source_point_count": len(source_candidates),
        "returned_point_count": len(carrier_points),
        "truncated": len(source_candidates) > len(carrier_points),
        "points": cast(JsonValue, carrier_points),
        "doppler_fit_available": fit_available,
        "reason": carrier_reason,
    }

    source_qam_points = [
        {
            "receiver_key": str(receiver_id),
            "time_s": epoch_sample / bundle.waterfall.sample_rate_hz,
            "candidate_epoch_sample": epoch_sample,
            "accuracy": result.metrics.hard_symbol_accuracy,
            "rms_evm": result.metrics.rms_evm,
            "frame_count": result.metrics.frame_count,
        }
        for receiver_id, epoch_sample, result in zip(
            bundle.qam.receiver_ids,
            bundle.qam.receiver_epoch_samples,
            bundle.qam.receiver_results,
            strict=True,
        )
        if result.metrics is not None
    ]
    qam_points = source_qam_points[:16]
    qam: dict[str, JsonValue] = {
        "schema_version": 1,
        "run_id": run_id,
        "state": "partial" if qam_points else "unavailable",
        "time_unit": "s",
        "temporal_resolution": "aggregate_candidate_window",
        "source_point_count": len(source_qam_points),
        "returned_point_count": len(qam_points),
        "truncated": len(source_qam_points) > len(qam_points),
        "points": cast(JsonValue, qam_points),
        "continuous_time_series_available": False,
        "reason": (
            "candidate-window QAM aggregates are available; continuous QAM-versus-time "
            "samples were not produced"
            if qam_points
            else "no candidate-window QAM metrics are available"
        ),
    }
    stages: dict[str, JsonValue] = {
        "schema_version": 1,
        "run_id": run_id,
        "state": "unavailable",
        "stages": [],
        "reason": (
            "the whole-dwell bundle does not contain persisted per-stage signal-time events"
        ),
    }
    return {
        "carrier-timing.presentation": carrier,
        "qam-timeline.presentation": qam,
        "analysis-stage-timeline.presentation": stages,
    }


def _waterfall_document(run_id: str, waterfall: WaterfallResult) -> dict[str, JsonValue]:
    values = [
        value
        for tile in waterfall.tiles
        for receiver in tile.receiver_power_dbfs
        for value in receiver
        if value is not None
    ]
    lower = min(values, default=-160.0)
    upper = max(values, default=0.0)
    scale = max(upper - lower, 1e-12)
    points = []
    for tile in waterfall.tiles:
        time_s = (tile.sample_start + tile.sample_stop) / (2 * waterfall.sample_rate_hz)
        for frequency_index, frequency_hz in enumerate(waterfall.frequency_bin_centers_hz):
            per_receiver = [
                row[frequency_index]
                for row in tile.receiver_power_dbfs
                if row[frequency_index] is not None
            ]
            if not per_receiver:
                continue
            points.append(
                {
                    "x": time_s,
                    "y": frequency_hz,
                    "value": (max(value for value in per_receiver if value is not None) - lower)
                    / scale,
                }
            )
    return {
        "schema_version": 1,
        "kind": "waterfall",
        "metadata": {
            "run_id": run_id,
            "time_unit": "s",
            "frequency_unit": "Hz",
            "value_unit": "normalized dBFS",
            "source_value_min_dbfs": lower,
            "source_value_max_dbfs": upper,
            "receiver_reducer": "maximum",
            "coverage_fraction": waterfall.coverage.observed_fraction,
            "config_digest": _bare_digest(waterfall.config_digest),
        },
        "points": cast(JsonValue, points),
    }


def _overlay_document(
    run_id: str,
    candidates: list[dict[str, JsonValue]],
    doppler: DopplerFitResult,
) -> dict[str, JsonValue]:
    points = [
        {
            "x": candidate["time_s"],
            "y": candidate["baseband_cfo_hz"],
            "value": candidate["margin"],
        }
        for candidate in candidates
    ]
    return {
        "schema_version": 1,
        "kind": "overlays",
        "metadata": {
            "run_id": run_id,
            "time_unit": "s",
            "frequency_unit": "Hz",
            "frequency_axis": "baseband_cfo_hz",
            "value_unit": "held-out margin",
            "doppler_slope_hz_s": doppler.slope_hz_s,
            "doppler_residual_rms_hz": doppler.residual_rms_hz,
            "source_candidate_count": len(candidates),
        },
        "points": cast(JsonValue, points),
    }


def _qam_metrics(qam: QamHandoffResult) -> tuple[tuple[str, float], ...]:
    values = [
        (str(receiver_id), result.metrics.hard_symbol_accuracy)
        for receiver_id, result in zip(qam.receiver_ids, qam.receiver_results, strict=True)
        if result.metrics is not None
    ]
    if qam.combined is not None and qam.combined.metrics is not None:
        values.append(("combined", qam.combined.metrics.hard_symbol_accuracy))
    return tuple(values)


def _bare_digest(value: str) -> str:
    candidate = value.removeprefix("sha256:")
    if len(candidate) != 64 or any(character not in "0123456789abcdef" for character in candidate):
        raise ValueError("presentation provenance requires a SHA-256 digest")
    return candidate
