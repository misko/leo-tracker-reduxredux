"""Small presentation-ready overlays derived from immutable scientific products."""

from __future__ import annotations

from dataclasses import dataclass

from leo.analysis.controls.evidence import ControlResult
from leo.analysis.doppler import DopplerFitResult, TleAssociationResult
from leo.analysis.starlink.long_dwell import (
    ActivityTrackingResult,
    CandidateCloudResult,
    QamHandoffResult,
    ScientificConfidence,
)
from leo.analysis.waterfall import WaterfallResult


@dataclass(frozen=True, slots=True)
class CandidateOverlayPoint:
    candidate_id: str
    receiver_id: int
    time_s: float
    absolute_cfo_hz: float
    margin: float


@dataclass(frozen=True, slots=True)
class TrackOverlay:
    track_id: str
    receiver_id: int
    time_s: tuple[float, ...]
    absolute_cfo_hz: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ScientificSummary:
    schema_version: int
    confidence: ScientificConfidence
    candidate_count: int
    track_count: int
    best_qam_accuracy: float | None
    best_qam_evm: float | None
    doppler_slope_hz_s: float | None
    doppler_residual_rms_hz: float | None
    tle_candidate: str | None
    waterfall_time_bins: int
    waterfall_frequency_bins: int
    coverage_fraction: float
    candidate_overlay: tuple[CandidateOverlayPoint, ...]
    track_overlays: tuple[TrackOverlay, ...]
    lineage_config_digests: tuple[str, ...]
    notes: tuple[str, ...]


def build_scientific_summary(
    *,
    sample_rate_hz: float,
    waterfall: WaterfallResult,
    cloud: CandidateCloudResult,
    tracks: ActivityTrackingResult,
    doppler: DopplerFitResult,
    qam: QamHandoffResult,
    controls: ControlResult,
    tle: TleAssociationResult,
) -> ScientificSummary:
    """Project bounded scientific values without embedding large arrays."""

    metrics = [item.metrics for item in qam.receiver_results if item.metrics is not None]
    if qam.combined is not None and qam.combined.metrics is not None:
        metrics.append(qam.combined.metrics)
    overlay = tuple(
        CandidateOverlayPoint(
            item.candidate_id,
            item.observation.receiver_id,
            item.observation.absolute_epoch_sample / sample_rate_hz,
            item.observation.absolute_cfo_hz,
            item.observation.verify_minus_control_margin,
        )
        for item in cloud.candidates
    )
    track_overlays = tuple(
        TrackOverlay(
            item.track_id,
            item.receiver_id,
            tuple(position / sample_rate_hz for position in item.sample_positions),
            item.absolute_cfo_hz,
        )
        for item in tracks.tracks
    )
    notes = (
        controls.reason,
        doppler.reason,
        tle.reason,
        "compute tier is recorded separately and does not determine confidence",
    )
    return ScientificSummary(
        1,
        controls.confidence,
        len(cloud.candidates),
        len(tracks.tracks),
        max((item.hard_symbol_accuracy for item in metrics), default=None),
        min((item.rms_evm for item in metrics), default=None),
        doppler.slope_hz_s,
        doppler.residual_rms_hz,
        tle.object_id,
        len(waterfall.tiles),
        len(waterfall.frequency_bin_centers_hz),
        waterfall.coverage.observed_fraction,
        overlay,
        track_overlays,
        (
            waterfall.config_digest,
            cloud.config_digest,
            tracks.config_digest,
            doppler.config_digest,
            controls.config_digest,
        ),
        notes,
    )
