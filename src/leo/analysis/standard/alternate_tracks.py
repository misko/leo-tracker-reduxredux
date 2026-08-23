"""Bounded candidate-only Hough line finder over persisted pilot evidence."""

from __future__ import annotations

import io
from threading import RLock
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.analysis.cfo_lines import (
    CfoPoint,
    HoughConfig,
    LineDetectionConfig,
    circular_residual_hz,
    weighted_hough_lines,
)
from leo.analysis.residual_hough import (
    ResidualHoughSelectionConfig,
    detect_all_residual_hough_lines,
    hough_config_from_contract,
)
from leo.contracts.alternate_cfo_tracks import (
    AlternateCfoLineFinderConfigV1,
    AlternateCfoTrackBankV1,
    AlternateCfoTrackBankV2,
    AlternateCfoTrackBankV3,
    AlternateCfoTrackV1,
    AlternateCfoTrackV2,
    RankedCandidateResidualHoughConfigV3,
    ResidualHoughParentSelectionV2,
    ResidualHoughSegmentationConfigV2,
)
from leo.contracts.digests import canonical_digest

_RENDER_LOCK = RLock()


def default_alternate_cfo_hough_v1_config() -> AlternateCfoLineFinderConfigV1:
    return AlternateCfoLineFinderConfigV1(
        alias_spacing_hz=1.0 / 4.4e-6,
        minimum_slope_hz_per_s=-15_000.0,
        maximum_slope_hz_per_s=15_000.0,
        residual_gate_hz=2_500.0,
        maximum_gap_s=0.75,
        minimum_span_s=0.75,
        minimum_support=8,
        minimum_point_weight=0.5,
        slope_bins=121,
        intercept_bins=512,
        peak_candidates=64,
        maximum_detected_tracks=32,
        maximum_published_tracks=16,
        maximum_input_points=25_000,
    )


def default_alternate_cfo_config() -> ResidualHoughSegmentationConfigV2:
    """Return the reviewed V2 split policy around the frozen V1 Hough proposal map."""

    return ResidualHoughSegmentationConfigV2(
        initial_hough=default_alternate_cfo_hough_v1_config(),
        minimum_split_gain=200.0,
        maximum_proposals_per_parent=8,
        maximum_parent_support=5_000,
        maximum_input_points=50_000,
    )


def default_alternate_cfo_display_config() -> ResidualHoughSegmentationConfigV2:
    """Return the same expanded, contract-bounded inventory used by Standard."""

    return default_alternate_cfo_config()


def pilot_scan_points(
    document: dict[str, Any], *, maximum_candidates_per_probe: int | None = None
) -> tuple[CfoPoint, ...]:
    points: list[CfoPoint] = []
    for detection in document["detections"]:
        for candidate in detection["candidates"]:
            if (
                maximum_candidates_per_probe is not None
                and candidate["rank"] >= maximum_candidates_per_probe
            ):
                continue
            score = next((row for row in candidate["scores"] if row["method"] == "glrt64"), None)
            if score is None or score["control_score"] is None:
                continue
            points.append(
                CfoPoint(
                    point_id=f"{detection['sample_start']}:{candidate['rank']}",
                    time_s=float(detection["time_s"]),
                    frequency_hz=float(score["tracking_cfo_hz"]),
                    exact_score=float(score["exact_score"]),
                    control_score=float(score["control_score"]),
                    margin=float(score["margin"]),
                )
            )
    return tuple(points)


def build_alternate_cfo_tracks(
    pilot_document: dict[str, Any],
    *,
    pilot_digest: str,
    config: AlternateCfoLineFinderConfigV1,
) -> AlternateCfoTrackBankV1:
    points = pilot_scan_points(pilot_document)
    if len(points) > config.maximum_input_points:
        raise ValueError("pilot point inventory exceeds alternate line-finder bound")
    common = LineDetectionConfig(
        alias_spacing_hz=config.alias_spacing_hz,
        minimum_slope_hz_per_s=config.minimum_slope_hz_per_s,
        maximum_slope_hz_per_s=config.maximum_slope_hz_per_s,
        residual_gate_hz=config.residual_gate_hz,
        maximum_gap_s=config.maximum_gap_s,
        minimum_span_s=config.minimum_span_s,
        minimum_support=config.minimum_support,
        minimum_point_weight=config.minimum_point_weight,
        maximum_tracks=config.maximum_detected_tracks,
    )
    segments = weighted_hough_lines(
        points,
        HoughConfig(
            common=common,
            slope_bins=config.slope_bins,
            intercept_bins=config.intercept_bins,
            peak_candidates=config.peak_candidates,
        ),
    )
    selected = segments[: config.maximum_published_tracks]
    tracks = tuple(
        AlternateCfoTrackV1(
            track_id=item.segment_id,
            start_s=item.start_s,
            end_s=item.end_s,
            span_s=item.end_s - item.start_s,
            support_count=item.support,
            weighted_support=item.weighted_support,
            slope_hz_per_s=item.slope_hz_per_s,
            intercept_mod_alias_hz=item.intercept_mod_alias_hz,
            residual_rms_hz=item.residual_rms_hz,
            residual_max_hz=item.residual_max_hz,
            maximum_gap_s=item.maximum_gap_s,
            confidence=(
                "strong_geometry"
                if item.support >= 20
                and item.end_s - item.start_s >= 1.0
                and item.residual_rms_hz <= 1_000
                else "candidate_geometry"
            ),
        )
        for item in selected
    )
    return AlternateCfoTrackBankV1(
        pilot_scan_content_digest=pilot_digest,
        configuration_digest=canonical_digest(config.model_dump(mode="json")),
        configuration=config,
        source_point_count=len(points),
        detected_track_count=len(segments),
        returned_track_count=len(tracks),
        truncated_track_count=len(segments) - len(tracks),
        tracks=tracks,
    )


def _hough_config(config: AlternateCfoLineFinderConfigV1) -> HoughConfig:
    return hough_config_from_contract(config)


def build_residual_hough_cfo_tracks(
    pilot_document: dict[str, Any],
    *,
    pilot_digest: str,
    config: ResidualHoughSegmentationConfigV2,
) -> AlternateCfoTrackBankV2:
    """Refine every bounded initial Hough parent and publish only linear segments."""

    points = pilot_scan_points(pilot_document)
    initial = config.initial_hough
    if len(points) > config.maximum_input_points:
        raise ValueError("pilot point inventory exceeds alternate line-finder bound")
    parents, parent_rows, tracks = _residual_hough_inventory(points, config)
    detected = len(tracks)
    selected = tuple(tracks[: initial.maximum_published_tracks])
    return AlternateCfoTrackBankV2(
        pilot_scan_content_digest=pilot_digest,
        configuration_digest=canonical_digest(config.model_dump(mode="json")),
        configuration=config,
        source_point_count=len(points),
        initial_track_count=len(parents),
        refined_parent_count=len(parent_rows),
        detected_track_count=detected,
        returned_track_count=len(selected),
        truncated_track_count=detected - len(selected),
        parent_selections=tuple(parent_rows),
        tracks=selected,
    )


def build_ranked_residual_hough_cfo_tracks(
    pilot_document: dict[str, Any],
    *,
    pilot_digest: str,
    config: RankedCandidateResidualHoughConfigV3,
) -> AlternateCfoTrackBankV3:
    """Preserve dense evidence while fitting a disclosed ranked prefix per probe."""

    source_point_count = len(pilot_scan_points(pilot_document))
    points = pilot_scan_points(
        pilot_document,
        maximum_candidates_per_probe=config.maximum_candidates_per_probe,
    )
    segmentation = config.segmentation
    bound = min(
        segmentation.maximum_input_points,
        segmentation.initial_hough.maximum_input_points,
    )
    if len(points) > bound:
        raise ValueError("selected pilot point inventory exceeds alternate line-finder bound")
    parents, parent_rows, tracks = _residual_hough_inventory(points, segmentation)
    detected = len(tracks)
    selected = tuple(tracks[: segmentation.initial_hough.maximum_published_tracks])
    return AlternateCfoTrackBankV3(
        pilot_scan_content_digest=pilot_digest,
        configuration_digest=canonical_digest(config.model_dump(mode="json")),
        configuration=config,
        source_point_count=source_point_count,
        selected_point_count=len(points),
        omitted_point_count=source_point_count - len(points),
        initial_track_count=len(parents),
        refined_parent_count=len(parent_rows),
        detected_track_count=detected,
        returned_track_count=len(selected),
        truncated_track_count=detected - len(selected),
        parent_selections=tuple(parent_rows),
        tracks=selected,
    )


def _residual_hough_inventory(
    points: tuple[CfoPoint, ...], config: ResidualHoughSegmentationConfigV2
) -> tuple[
    tuple[Any, ...],
    list[ResidualHoughParentSelectionV2],
    list[AlternateCfoTrackV2],
]:
    initial = config.initial_hough
    hough_config = _hough_config(initial)
    by_id = {point.point_id: point for point in points}
    selection_config = ResidualHoughSelectionConfig(
        minimum_split_gain=config.minimum_split_gain,
        maximum_proposals=config.maximum_proposals_per_parent,
        maximum_parent_support=config.maximum_parent_support,
    )
    parent_rows: list[ResidualHoughParentSelectionV2] = []
    tracks: list[AlternateCfoTrackV2] = []
    parents, refined = detect_all_residual_hough_lines(
        points=points,
        hough_config=hough_config,
        selection_config=selection_config,
    )
    for parent, selection in refined:
        parent_rows.append(
            ResidualHoughParentSelectionV2(
                parent_track_id=parent.segment_id,
                parent_support_count=parent.support,
                residual_gate_hz=selection.residual_gate_hz,
                detected_proposal_count=selection.detected_proposal_count,
                considered_proposal_count=selection.considered_proposal_count,
                assigned_point_count=selection.assigned_point_count,
                unassigned_point_count=selection.unassigned_point_count,
                admissible_partition_count=selection.admissible_partition_count,
                selected_line_count=selection.selected_line_count,
                robust_mdl=selection.robust_mdl,
                adjusted_robust_mdl=selection.adjusted_robust_mdl,
                gaussian_bic=selection.gaussian_bic,
                adjusted_gaussian_bic=selection.adjusted_gaussian_bic,
                gaussian_selected_line_count=selection.gaussian_selected_line_count,
            )
        )
        parent_tracks: list[AlternateCfoTrackV2] = []
        for line in selection.lines:
            support = tuple(by_id[point_id] for point_id in line.point_ids)
            times = np.asarray([point.time_s for point in support], dtype=float)
            frequencies = np.asarray([point.frequency_hz for point in support], dtype=float)
            residual = circular_residual_hz(
                frequencies,
                line.mapped_slope_hz_per_s * times + line.mapped_intercept_hz,
                initial.alias_spacing_hz,
            )
            gaps = np.diff(np.sort(times))
            weighted_support = float(sum(point.weight for point in support))
            residual_rms = float(np.sqrt(np.mean(residual**2)))
            residual_max = float(np.max(np.abs(residual)))
            parent_tracks.append(
                AlternateCfoTrackV2(
                    track_id=line.line_id,
                    source_parent_track_id=parent.segment_id,
                    source_residual_proposal_numbers=line.source_proposal_numbers,
                    start_s=line.start_s,
                    end_s=line.end_s,
                    span_s=line.end_s - line.start_s,
                    support_count=line.support,
                    weighted_support=weighted_support,
                    slope_hz_per_s=line.mapped_slope_hz_per_s,
                    intercept_mod_alias_hz=line.mapped_intercept_hz % initial.alias_spacing_hz,
                    residual_rms_hz=residual_rms,
                    residual_max_hz=residual_max,
                    median_absolute_residual_hz=float(np.median(np.abs(residual))),
                    maximum_gap_s=float(np.max(gaps)) if gaps.size else 0.0,
                    confidence=(
                        "strong_geometry"
                        if line.support >= 20
                        and line.end_s - line.start_s >= 1.0
                        and residual_rms <= 1_000.0
                        else "candidate_geometry"
                    ),
                )
            )
        parent_tracks.sort(
            key=lambda item: (
                -item.weighted_support,
                -item.span_s,
                -item.support_count,
                item.residual_rms_hz,
                item.track_id,
            )
        )
        # Initial parents are already peeled strongest-first. Preserve that order
        # so a weaker later parent cannot evict a valid split of the strongest one.
        tracks.extend(parent_tracks)
    return parents, parent_rows, tracks


def render_alternate_cfo_tracks_png(
    pilot_document: dict[str, Any],
    bank: AlternateCfoTrackBankV1 | AlternateCfoTrackBankV2 | AlternateCfoTrackBankV3,
) -> bytes:
    points = pilot_scan_points(pilot_document)
    with _RENDER_LOCK:
        figure = Figure(figsize=(15, 6), dpi=160, constrained_layout=True)
        FigureCanvasAgg(figure)
        axis = figure.subplots(1, 1)
        axis.scatter(
            [point.time_s for point in points],
            [point.frequency_hz / 1_000 for point in points],
            s=4,
            color="#8b949e",
            alpha=0.22,
            rasterized=True,
            label="persisted independent-search GLRT64 candidates",
        )
        colors = (
            "#0072b2",
            "#d55e00",
            "#009e73",
            "#cc79a7",
            "#e69f00",
            "#56b4e9",
            "#000000",
            "#f0e442",
        )
        raw_frequency_hz = [point.frequency_hz for point in points]
        if isinstance(bank, AlternateCfoTrackBankV1):
            line_config = bank.configuration
        elif isinstance(bank, AlternateCfoTrackBankV2):
            line_config = bank.configuration.initial_hough
        else:
            line_config = bank.configuration.segmentation.initial_hough
        raw_lower_hz = min(raw_frequency_hz, default=-line_config.alias_spacing_hz / 2)
        raw_upper_hz = max(raw_frequency_hz, default=line_config.alias_spacing_hz / 2)
        rendered_tracks: tuple[AlternateCfoTrackV1 | AlternateCfoTrackV2, ...] = tuple(bank.tracks)
        for index, track in enumerate(rendered_tracks):
            line_times = (track.start_s, track.end_s)
            canonical_frequency = tuple(
                track.slope_hz_per_s * time + track.intercept_mod_alias_hz for time in line_times
            )
            minimum_alias = (
                int((raw_lower_hz - max(canonical_frequency)) // line_config.alias_spacing_hz) - 1
            )
            maximum_alias = (
                int((raw_upper_hz - min(canonical_frequency)) // line_config.alias_spacing_hz) + 1
            )
            labelled = False
            for alias in range(minimum_alias, maximum_alias + 1):
                frequency = tuple(
                    (value + alias * line_config.alias_spacing_hz) / 1_000
                    for value in canonical_frequency
                )
                if max(frequency) * 1_000 < raw_lower_hz or min(frequency) * 1_000 > raw_upper_hz:
                    continue
                axis.plot(
                    line_times,
                    frequency,
                    linewidth=2.1,
                    color=colors[index % len(colors)],
                    alpha=0.9,
                    label=(
                        f"L{index + 1} · n={track.support_count} · {track.slope_hz_per_s:+.0f} Hz/s"
                        if not labelled
                        else None
                    ),
                )
                labelled = True
        if points:
            point_times = [point.time_s for point in points]
            frequencies = [point.frequency_hz / 1_000 for point in points]
            axis.set_xlim(
                min(point_times),
                max(point_times) if max(point_times) > min(point_times) else min(point_times) + 1,
            )
            lower, upper = min(frequencies), max(frequencies)
            padding = max(20.0, 0.04 * max(upper - lower, 1.0))
            axis.set_ylim(lower - padding, upper + padding)
        axis.set_xlabel("Elapsed recording time (s)")
        axis.set_ylabel("Baseband CFO (kHz)")
        axis.set_title(
            (
                "Research-only weighted alias-aware Hough candidates"
                if isinstance(bank, AlternateCfoTrackBankV1)
                else "Split-penalized residual-Hough linear segments"
            ),
            loc="left",
            fontweight="bold",
        )
        axis.grid(alpha=0.2)
        if bank.tracks:
            axis.legend(loc="best", fontsize=7, ncols=2)
        target = io.BytesIO()
        figure.savefig(
            target,
            format="png",
            dpi=160,
            facecolor="white",
            metadata={"Software": f"leo-tracker {bank.algorithm_version}"},
        )
        return target.getvalue()
