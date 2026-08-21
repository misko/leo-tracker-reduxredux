"""Bounded candidate-only Hough line finder over persisted pilot evidence."""

from __future__ import annotations

import io
from threading import RLock
from typing import Any

import matplotlib

matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.analysis.cfo_lines import (
    CfoPoint,
    HoughConfig,
    LineDetectionConfig,
    weighted_hough_lines,
)
from leo.contracts.alternate_cfo_tracks import (
    AlternateCfoLineFinderConfigV1,
    AlternateCfoTrackBankV1,
    AlternateCfoTrackV1,
)
from leo.contracts.digests import canonical_digest

_RENDER_LOCK = RLock()


def default_alternate_cfo_config() -> AlternateCfoLineFinderConfigV1:
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
        peak_candidates=24,
        maximum_detected_tracks=16,
        maximum_published_tracks=8,
        maximum_input_points=25_000,
    )


def pilot_scan_points(document: dict[str, Any]) -> tuple[CfoPoint, ...]:
    points: list[CfoPoint] = []
    for detection in document["detections"]:
        for candidate in detection["candidates"]:
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


def render_alternate_cfo_tracks_png(
    pilot_document: dict[str, Any], bank: AlternateCfoTrackBankV1
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
        raw_lower_hz = min(raw_frequency_hz, default=-bank.configuration.alias_spacing_hz / 2)
        raw_upper_hz = max(raw_frequency_hz, default=bank.configuration.alias_spacing_hz / 2)
        for index, track in enumerate(bank.tracks):
            line_times = (track.start_s, track.end_s)
            canonical_frequency = tuple(
                track.slope_hz_per_s * time + track.intercept_mod_alias_hz for time in line_times
            )
            minimum_alias = (
                int(
                    (raw_lower_hz - max(canonical_frequency)) // bank.configuration.alias_spacing_hz
                )
                - 1
            )
            maximum_alias = (
                int(
                    (raw_upper_hz - min(canonical_frequency)) // bank.configuration.alias_spacing_hz
                )
                + 1
            )
            labelled = False
            for alias in range(minimum_alias, maximum_alias + 1):
                frequency = tuple(
                    (value + alias * bank.configuration.alias_spacing_hz) / 1_000
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
                        f"H{index + 1} · n={track.support_count} · {track.slope_hz_per_s:+.0f} Hz/s"
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
            "Research-only weighted alias-aware Hough candidates", loc="left", fontweight="bold"
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
            metadata={"Software": "leo-tracker alternate-cfo-hough-v1"},
        )
        return target.getvalue()
