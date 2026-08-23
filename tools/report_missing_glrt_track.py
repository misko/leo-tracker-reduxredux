#!/usr/bin/env python3
"""Reproduce one missing-track diagnosis from persisted Standard evidence.

The tool is intentionally read-only.  It rebuilds the residual-Hough inventory
from a registered pilot scan, identifies detected segments hidden by the
published-track cap, and optionally replays those omitted segments against the
verified local recording store.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt

from leo.analysis.standard.alternate_tracks import (
    _residual_hough_inventory,
    build_residual_hough_cfo_tracks,
    pilot_scan_points,
    render_alternate_cfo_tracks_png,
)
from leo.analysis.standard.analyzers import _pilot_detections
from leo.analysis.standard.runner import SingleReceiverIqReader
from leo.analysis.starlink.templates import StarlinkEdge
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    fit_residual_hough_pilot_trajectories,
    infer_hough_replay_alias_indices,
    replay_pilot_trajectories_with_conditioned_scores,
    trajectory_observations,
)
from leo.contracts.alternate_cfo_tracks import AlternateCfoTrackBankV2
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.storage import RecordingStore

_BLUE = "#0072b2"
_ORANGE = "#e69f00"
_RED = "#d55e00"
_GREEN = "#009e73"
_GRAY = "#8b949e"
_DARK = "#1f2933"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-scan", type=Path, required=True)
    parser.add_argument("--alternate-bank", type=Path, required=True)
    parser.add_argument("--release-config", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--bundle-uri", required=True)
    parser.add_argument("--stream-id", required=True)
    parser.add_argument("--receiver-id", type=int, required=True)
    parser.add_argument("--edge", choices=("lower", "upper"), required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--window-start-s", type=float, default=17.0)
    parser.add_argument("--window-end-s", type=float, default=23.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a JSON object")
    return value


def _digest_file(path: Path) -> str:
    return sha256_digest(path.read_bytes())


def _overlaps(track: Any, start_s: float, end_s: float) -> bool:
    return track.end_s >= start_s and track.start_s <= end_s


def _track_document(track: Any, *, order: int, published: bool) -> dict[str, Any]:
    value = track.model_dump(mode="json")
    value["selection_order"] = order
    value["published_by_current_cap"] = published
    return value


def _plot_aliases(
    axis: Any,
    track: Any,
    *,
    alias_spacing_hz: float,
    lower_hz: float,
    upper_hz: float,
    color: str,
    linestyle: str,
    linewidth: float,
    label: str | None = None,
) -> None:
    times = np.asarray((track.start_s, track.end_s), dtype=float)
    canonical = track.slope_hz_per_s * times + track.intercept_mod_alias_hz
    minimum_alias = math.floor((lower_hz - float(np.max(canonical))) / alias_spacing_hz) - 1
    maximum_alias = math.ceil((upper_hz - float(np.min(canonical))) / alias_spacing_hz) + 1
    labelled = False
    for alias_index in range(minimum_alias, maximum_alias + 1):
        values = canonical + alias_index * alias_spacing_hz
        if float(np.max(values)) < lower_hz or float(np.min(values)) > upper_hz:
            continue
        axis.plot(
            times,
            values / 1_000.0,
            color=color,
            linestyle=linestyle,
            linewidth=linewidth,
            alpha=0.95,
            label=label if label is not None and not labelled else None,
            zorder=5,
        )
        labelled = True


def _render_overview(
    *,
    points: tuple[Any, ...],
    tracks: list[Any],
    published_ids: set[str],
    window_ids: set[str],
    alias_spacing_hz: float,
    start_s: float,
    end_s: float,
    output: Path,
) -> None:
    figure, axis = plt.subplots(figsize=(15, 6), dpi=160, constrained_layout=True)
    axis.scatter(
        [point.time_s for point in points],
        [point.frequency_hz / 1_000.0 for point in points],
        s=3,
        color=_GRAY,
        alpha=0.16,
        rasterized=True,
        label="all persisted independent-search GLRT64 candidates",
    )
    lower_hz = min(point.frequency_hz for point in points)
    upper_hz = max(point.frequency_hz for point in points)
    used = {"published": False, "window": False, "other": False}
    for track in tracks:
        if track.track_id in published_ids:
            category = "published"
            color, style, width = _BLUE, "-", 2.0
            label = "published/replayed (8-track cap)"
        elif track.track_id in window_ids:
            category = "window"
            color, style, width = _RED, "--", 2.7
            label = "detected but truncated; overlaps 17–23 s"
        else:
            category = "other"
            color, style, width = _ORANGE, ":", 1.8
            label = "other detected but truncated"
        _plot_aliases(
            axis,
            track,
            alias_spacing_hz=alias_spacing_hz,
            lower_hz=lower_hz,
            upper_hz=upper_hz,
            color=color,
            linestyle=style,
            linewidth=width,
            label=None if used[category] else label,
        )
        used[category] = True
    axis.axvspan(start_s, end_s, color=_ORANGE, alpha=0.09, label="reported gap window")
    axis.set_xlabel("Elapsed capture time (s)")
    axis.set_ylabel("Baseband CFO (kHz)")
    axis.set_title(
        "Full GLRT64 evidence: the 17–23 s line was detected, then hidden by the output cap",
        loc="left",
        fontweight="bold",
    )
    axis.grid(alpha=0.2)
    axis.legend(loc="upper center", ncols=3, fontsize=8)
    figure.savefig(output)
    plt.close(figure)


def _render_closeup(
    *,
    points: tuple[Any, ...],
    relevant: list[Any],
    point_ids_by_track: dict[str, tuple[str, ...]],
    alias_spacing_hz: float,
    start_s: float,
    end_s: float,
    output: Path,
) -> None:
    by_id = {point.point_id: point for point in points}
    target_values = []
    for track in relevant:
        times = np.asarray((max(start_s, track.start_s), min(end_s, track.end_s)))
        target_values.extend(track.slope_hz_per_s * times + track.intercept_mod_alias_hz)
    target_centre = float(np.median(target_values))
    alias = round(-target_centre / alias_spacing_hz)
    target_centre += alias * alias_spacing_hz
    lower_hz, upper_hz = target_centre - 55_000.0, target_centre + 55_000.0
    window_points = tuple(
        point
        for point in points
        if start_s <= point.time_s <= end_s and lower_hz <= point.frequency_hz <= upper_hz
    )
    figure, axes = plt.subplots(2, 1, figsize=(13, 9), dpi=160, constrained_layout=True)
    top, bottom = axes
    weak = tuple(point for point in window_points if point.weight < 0.5)
    eligible = tuple(point for point in window_points if point.weight >= 0.5)
    top.scatter(
        [point.time_s for point in weak],
        [point.frequency_hz / 1_000.0 for point in weak],
        s=7,
        color=_GRAY,
        alpha=0.18,
        rasterized=True,
        label="below Hough weight gate",
    )
    scatter = top.scatter(
        [point.time_s for point in eligible],
        [point.frequency_hz / 1_000.0 for point in eligible],
        s=12,
        c=[point.weight for point in eligible],
        cmap="viridis",
        vmin=0.5,
        vmax=16.0,
        alpha=0.7,
        rasterized=True,
        label="eligible GLRT64 candidates",
    )
    for index, track in enumerate(relevant, start=1):
        _plot_aliases(
            top,
            track,
            alias_spacing_hz=alias_spacing_hz,
            lower_hz=lower_hz,
            upper_hz=upper_hz,
            color=(_GREEN, _RED, _ORANGE)[(index - 1) % 3],
            linestyle="--",
            linewidth=2.7,
            label=(
                f"omitted segment {index}: {track.start_s:.3f}–{track.end_s:.3f} s, "
                f"{track.slope_hz_per_s:+.0f} Hz/s"
            ),
        )
    top.set_xlim(start_s, end_s)
    top.set_ylim(lower_hz / 1_000.0, upper_hz / 1_000.0)
    top.set_xlabel("Elapsed capture time (s)")
    top.set_ylabel("Baseband CFO (kHz)")
    top.set_title("A · Raw GLRT64 close-up and omitted Hough fits", loc="left", fontweight="bold")
    top.grid(alpha=0.2)
    top.legend(loc="best", fontsize=8)
    figure.colorbar(scatter, ax=top, label="control-normalized GLRT64 weight")

    colors = (_RED, _GREEN, _ORANGE)
    for index, track in enumerate(relevant):
        track_support = tuple(
            point
            for point in (by_id[point_id] for point_id in point_ids_by_track[track.track_id])
            if start_s <= point.time_s <= end_s
        )
        bottom.scatter(
            [point.time_s for point in track_support],
            [point.weight for point in track_support],
            s=13,
            color=colors[index % len(colors)],
            alpha=0.72,
            label=f"segment {index + 1} support (n={len(track_support)} in window)",
        )
    bottom.axhline(0.5, color=_DARK, linestyle=":", linewidth=1.6, label="weight gate = 0.5")
    bottom.set_xlim(start_s, end_s)
    bottom.set_ylim(0.0, 16.6)
    bottom.set_xlabel("Elapsed capture time (s)")
    bottom.set_ylabel("Control-normalized GLRT64 weight")
    bottom.set_title(
        "B · Exact points assigned to the omitted segments",
        loc="left",
        fontweight="bold",
    )
    bottom.grid(alpha=0.2)
    bottom.legend(loc="best", fontsize=8)
    figure.savefig(output)
    plt.close(figure)


def _render_selection_and_replay(
    *,
    tracks: list[Any],
    published_ids: set[str],
    window_ids: set[str],
    replay_rows: list[dict[str, Any]],
    positive_margin: float,
    output: Path,
) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(15, 7), dpi=160, constrained_layout=True)
    ranking, replay = axes
    positions = np.arange(1, len(tracks) + 1)
    colors = [
        _BLUE
        if track.track_id in published_ids
        else _RED
        if track.track_id in window_ids
        else _GRAY
        for track in tracks
    ]
    ranking.barh(positions, [track.weighted_support for track in tracks], color=colors, alpha=0.85)
    for position, track in zip(positions, tracks, strict=True):
        ranking.text(
            track.weighted_support + 35,
            position,
            f"{track.start_s:.2f}–{track.end_s:.2f} s · n={track.support_count}",
            va="center",
            fontsize=7,
        )
    ranking.axhline(8.5, color=_DARK, linestyle="--", linewidth=1.5)
    ranking.text(50, 8.35, "published cap", va="bottom", fontsize=8)
    ranking.invert_yaxis()
    ranking.set_yticks(positions, [f"order {value}" for value in positions])
    ranking.set_xlabel("Weighted Hough support")
    ranking.set_ylabel("Parent-preserving publication order")
    ranking.set_title(
        "A · Strong later-parent segments fall below row 8",
        loc="left",
        fontweight="bold",
    )
    ranking.grid(axis="x", alpha=0.2)

    markers = ("o", "s", "^")
    trajectory_ids = sorted(
        {str(row["trajectory_id"]) for row in replay_rows},
        key=lambda trajectory_id: min(
            float(row["time_s"]) for row in replay_rows if row["trajectory_id"] == trajectory_id
        ),
    )
    for index, trajectory_id in enumerate(trajectory_ids):
        values = [row for row in replay_rows if row["trajectory_id"] == trajectory_id]
        replay.scatter(
            [row["time_s"] for row in values],
            [row["conditioned_corrected_margin"] for row in values],
            s=15,
            marker=markers[index % len(markers)],
            alpha=0.7,
            label=(
                f"omitted segment {index + 1} · "
                f"{min(row['time_s'] for row in values):.2f}–"
                f"{max(row['time_s'] for row in values):.2f} s"
            ),
        )
    replay.axhline(
        positive_margin,
        color=_RED,
        linestyle="--",
        linewidth=1.7,
        label=f"positive-margin reference = {positive_margin:g}",
    )
    replay.axhline(0.0, color=_DARK, linewidth=1.0)
    replay.set_xlabel("Elapsed capture time (s)")
    replay.set_ylabel("Conditioned corrected GLRT64 margin")
    replay.set_title(
        "B · Raw-IQ replay does not corroborate the geometric line",
        loc="left",
        fontweight="bold",
    )
    replay.grid(alpha=0.2)
    replay.legend(loc="best", fontsize=8)
    figure.savefig(output)
    plt.close(figure)


def main() -> None:
    args = _args()
    if args.window_end_s <= args.window_start_s:
        raise ValueError("window bounds are not ordered")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pilot = _read_json(args.pilot_scan)
    current = AlternateCfoTrackBankV2.model_validate(_read_json(args.alternate_bank))
    release = _read_json(args.release_config)
    standard_stage = release["pipeline_lanes"]["standard"]["stages"]["path-standard"]
    positive_margin = float(standard_stage["trajectory_accounting"]["positive_margin"])
    points = pilot_scan_points(pilot)
    parents, parent_rows, tracks = _residual_hough_inventory(points, current.configuration)

    # Recover exact residual-line memberships for the close-up evidence plot.
    from leo.analysis.residual_hough import (
        ResidualHoughSelectionConfig,
        detect_all_residual_hough_lines,
        hough_config_from_contract,
    )

    hough_config = hough_config_from_contract(current.configuration.initial_hough)
    selection = ResidualHoughSelectionConfig(
        minimum_split_gain=current.configuration.minimum_split_gain,
        maximum_proposals=current.configuration.maximum_proposals_per_parent,
        maximum_parent_support=current.configuration.maximum_parent_support,
    )
    _, refined = detect_all_residual_hough_lines(
        points=points,
        hough_config=hough_config,
        selection_config=selection,
    )
    raw_lines = [line for _parent, row in refined for line in row.lines]
    point_ids_by_track = {line.line_id: line.point_ids for line in raw_lines}

    published_ids = {track.track_id for track in current.tracks}
    relevant = [
        track
        for track in tracks
        if track.track_id not in published_ids
        and _overlaps(track, args.window_start_s, args.window_end_s)
    ]
    relevant.sort(key=lambda track: (track.start_s, track.end_s, track.track_id))
    window_ids = {track.track_id for track in relevant}
    points_by_id = {point.point_id: point for point in points}
    window_probe_times = {
        point.time_s for point in points if args.window_start_s <= point.time_s <= args.window_end_s
    }
    assigned_window_ids = {
        point_id
        for track in relevant
        for point_id in point_ids_by_track[track.track_id]
        if args.window_start_s <= points_by_id[point_id].time_s <= args.window_end_s
    }
    window_support_summaries = []
    for track in relevant:
        assigned = [
            points_by_id[point_id]
            for point_id in point_ids_by_track[track.track_id]
            if args.window_start_s <= points_by_id[point_id].time_s <= args.window_end_s
        ]
        weights = [point.weight for point in assigned]
        window_support_summaries.append(
            {
                "track_id": track.track_id,
                "assigned_candidate_count": len(assigned),
                "minimum_weight": min(weights),
                "median_weight": statistics.median(weights),
                "maximum_weight": max(weights),
            }
        )

    feedback_values = dict(standard_stage["feedback"])
    feedback_values["probe_offsets_ms"] = tuple(feedback_values["probe_offsets_ms"])
    feedback = TrajectoryFeedbackConfig(**feedback_values)
    expanded_config = current.configuration.model_copy(
        update={
            "initial_hough": current.configuration.initial_hough.model_copy(
                update={"maximum_published_tracks": 16}
            )
        }
    )
    detections = _pilot_detections(pilot)
    trajectory_bank, representatives = fit_residual_hough_pilot_trajectories(
        detections,
        feedback,
        expanded_config,
    )
    replay_representatives = tuple(
        (family_id, trajectory)
        for family_id, trajectory in representatives
        if _overlaps(trajectory, args.window_start_s, args.window_end_s)
        and any(
            math.isclose(trajectory.start_s, track.start_s, abs_tol=1e-9)
            and math.isclose(trajectory.end_s, track.end_s, abs_tol=1e-9)
            for track in relevant
        )
    )
    observations = trajectory_observations(detections)
    alias_spacing_hz = current.configuration.initial_hough.alias_spacing_hz
    alias_indices = infer_hough_replay_alias_indices(
        replay_representatives,
        observations,
        alias_spacing_hz=alias_spacing_hz,
    )
    store = RecordingStore.open_read_only(args.bulk_root)
    try:
        bundle = store.inspect_uri(args.bundle_uri)
        reader = SingleReceiverIqReader(
            store.reader(bundle, args.stream_id, verify=True),
            args.receiver_id,
        )
        replay_started = time.monotonic()
        replay = replay_pilot_trajectories_with_conditioned_scores(
            reader,
            detections,
            replay_representatives,
            feedback,
            edge=StarlinkEdge(args.edge),
            alias_indices=alias_indices,
            alias_spacing_hz=alias_spacing_hz,
            association_gate_hz=2_500.0,
        )
        replay_runtime_s = time.monotonic() - replay_started
        manifest_digest = bundle.manifest_sha256
    finally:
        store.close()
    replay_rows = [
        row
        for row in replay
        if row["detector_method"] == "glrt64" and "conditioned_corrected_margin" in row
    ]

    display_benchmark: dict[str, Any] = {}
    display_payloads: dict[str, bytes] = {}
    pilot_digest = canonical_digest(pilot)
    for label, config in (
        ("current_cap_8", current.configuration),
        ("display_cap_16", expanded_config),
    ):
        elapsed: list[float] = []
        byte_sizes: list[int] = []
        returned_counts: list[int] = []
        for _ in range(5):
            started = time.perf_counter()
            bank = build_residual_hough_cfo_tracks(
                pilot,
                pilot_digest=pilot_digest,
                config=config,
            )
            payload = render_alternate_cfo_tracks_png(pilot, bank)
            elapsed.append(time.perf_counter() - started)
            byte_sizes.append(len(payload))
            returned_counts.append(bank.returned_track_count)
        display_benchmark[label] = {
            "repeat_count": len(elapsed),
            "median_seconds": statistics.median(elapsed),
            "minimum_seconds": min(elapsed),
            "maximum_seconds": max(elapsed),
            "returned_track_count": returned_counts[0],
            "png_bytes": byte_sizes[0],
        }
        display_payloads[label] = payload
    (args.output_dir / "current-cfo-alternate-cap-8.png").write_bytes(
        display_payloads["current_cap_8"]
    )
    (args.output_dir / "proposed-cfo-alternate-cap-16.png").write_bytes(
        display_payloads["display_cap_16"]
    )

    _render_overview(
        points=points,
        tracks=tracks,
        published_ids=published_ids,
        window_ids=window_ids,
        alias_spacing_hz=alias_spacing_hz,
        start_s=args.window_start_s,
        end_s=args.window_end_s,
        output=args.output_dir / "glrt-track-recovery-overview.png",
    )
    _render_closeup(
        points=points,
        relevant=relevant,
        point_ids_by_track=point_ids_by_track,
        alias_spacing_hz=alias_spacing_hz,
        start_s=args.window_start_s,
        end_s=args.window_end_s,
        output=args.output_dir / "glrt-hidden-track-closeup.png",
    )
    _render_selection_and_replay(
        tracks=tracks,
        published_ids=published_ids,
        window_ids=window_ids,
        replay_rows=replay_rows,
        positive_margin=positive_margin,
        output=args.output_dir / "selection-and-replay-diagnostics.png",
    )

    replay_summaries = []
    for _family_id, trajectory in replay_representatives:
        rows = [row for row in replay_rows if row["trajectory_id"] == trajectory.trajectory_id]
        margins = [float(row["conditioned_corrected_margin"]) for row in rows]
        deltas = [
            float(row["margin_delta"])
            for row in replay
            if row["trajectory_id"] == trajectory.trajectory_id
            and row["detector_method"] == "glrt64"
        ]
        replay_summaries.append(
            {
                "trajectory_id": trajectory.trajectory_id,
                "start_s": trajectory.start_s,
                "end_s": trajectory.end_s,
                "source_support_count": trajectory.point_count,
                "source_residual_rms_hz": trajectory.residual_rms_hz,
                "alias_index": alias_indices[trajectory.trajectory_id],
                "replay_probe_count": len(deltas),
                "conditioned_associated_probe_count": len(margins),
                "median_conditioned_corrected_margin": (
                    statistics.median(margins) if margins else None
                ),
                "maximum_conditioned_corrected_margin": max(margins) if margins else None,
                "positive_margin_threshold": positive_margin,
                "positive_margin_probe_count": sum(value >= positive_margin for value in margins),
                "median_ordinary_margin_delta": statistics.median(deltas) if deltas else None,
            }
        )

    evidence = {
        "schema_version": 1,
        "analysis": "missing-glrt-track-root-cause-v1",
        "session_id": args.session_id,
        "receiver_path": {
            "stream_id": args.stream_id,
            "receiver_id": args.receiver_id,
            "edge": args.edge,
        },
        "pipeline_release_id": args.release_id,
        "window_s": [args.window_start_s, args.window_end_s],
        "inputs": {
            "pilot_scan": str(args.pilot_scan),
            "pilot_scan_file_digest": _digest_file(args.pilot_scan),
            "pilot_scan_content_digest": canonical_digest(pilot),
            "alternate_bank": str(args.alternate_bank),
            "alternate_bank_file_digest": _digest_file(args.alternate_bank),
            "release_config": str(args.release_config),
            "release_config_file_digest": _digest_file(args.release_config),
            "recording_bundle_uri": args.bundle_uri,
            "verified_recording_manifest_digest": manifest_digest,
        },
        "configuration": current.configuration.model_dump(mode="json"),
        "inventory": {
            "source_glrt64_candidate_count": len(points),
            "initial_parent_count": len(parents),
            "refined_parent_count": len(parent_rows),
            "detected_segment_count": len(tracks),
            "published_segment_count": len(published_ids),
            "truncated_segment_count": len(tracks) - len(published_ids),
            "window_overlapping_truncated_segment_count": len(relevant),
            "tracks": [
                _track_document(
                    track,
                    order=index,
                    published=track.track_id in published_ids,
                )
                for index, track in enumerate(tracks, start=1)
            ],
        },
        "window_overlapping_truncated_tracks": [
            _track_document(
                track,
                order=tracks.index(track) + 1,
                published=False,
            )
            for track in relevant
        ],
        "window_support": {
            "probe_count": len(window_probe_times),
            "assigned_candidate_count": len(assigned_window_ids),
            "assigned_probe_coverage_fraction": len(assigned_window_ids) / len(window_probe_times),
            "minimum_hough_weight": current.configuration.initial_hough.minimum_point_weight,
            "segments": window_support_summaries,
        },
        "raw_iq_replay": {
            "runtime_seconds": replay_runtime_s,
            "trajectory_count": len(replay_representatives),
            "summaries": replay_summaries,
        },
        "display_fix_benchmark": display_benchmark,
        "root_cause": (
            "Residual Hough detected the requested geometry, but the 8-track parent-preserving "
            "publication/replay cap truncated its later-parent segments. The UI rendered the "
            "registered product faithfully. Raw-IQ replay does not justify automatic promotion."
        ),
    }
    (args.output_dir / "evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
