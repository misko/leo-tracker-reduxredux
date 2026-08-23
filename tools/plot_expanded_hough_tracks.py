#!/usr/bin/env python3
"""Plot an expanded, untruncated residual-Hough inventory for one persisted path."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from leo.analysis.standard.alternate_tracks import (
    _residual_hough_inventory,
    default_alternate_cfo_config,
    pilot_scan_points,
)
from leo.analysis.standard.analyzers import _png_source
from leo.contracts.alternate_cfo_tracks import (
    AlternateCfoLineFinderConfigV1,
    ResidualHoughSegmentationConfigV2,
)
from leo.presentation.standard_pipeline import StandardViewKindV2
from leo.presentation.standard_png import render_full_standard_plot_png


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path_presentation", type=Path)
    parser.add_argument("output_png", type=Path)
    parser.add_argument("--maximum-detected-tracks", type=int, default=32)
    parser.add_argument("--peak-candidates", type=int, default=64)
    return parser.parse_args()


def _expanded_config(
    *, maximum_detected_tracks: int, peak_candidates: int
) -> ResidualHoughSegmentationConfigV2:
    base = default_alternate_cfo_config()
    initial_values = base.initial_hough.model_dump(mode="python")
    initial_values.update(
        maximum_detected_tracks=maximum_detected_tracks,
        maximum_published_tracks=min(16, maximum_detected_tracks),
        peak_candidates=peak_candidates,
    )
    initial = AlternateCfoLineFinderConfigV1.model_validate(initial_values)
    values = base.model_dump(mode="python")
    values["initial_hough"] = initial.model_dump(mode="python")
    return ResidualHoughSegmentationConfigV2.model_validate(values)


def _trajectory_row(track: Any) -> dict[str, Any]:
    reference_time_s = float(track.start_s)
    reference_cfo_hz = (
        float(track.slope_hz_per_s) * reference_time_s
        + float(track.intercept_mod_alias_hz)
    )
    return {
        "trajectory_id": str(track.track_id),
        "family_id": str(track.source_parent_track_id),
        "model": "linear",
        "polynomial_degree": 1,
        "reference_time_s": reference_time_s,
        "coefficients_hz": [float(track.slope_hz_per_s), reference_cfo_hz],
        "start_s": float(track.start_s),
        "end_s": float(track.end_s),
        "duration_s": float(track.span_s),
        "point_count": int(track.support_count),
        "residual_rms_hz": float(track.residual_rms_hz),
        "bic": 0.0,
        "selected_for_correction": False,
        "fit_matches_well": True,
        "corrected_glrt64_probe_count": 0,
        "median_glrt64_margin_delta": 0.0,
        "high_gate": 0.0,
        "em_iterations": 0,
    }


def main() -> None:
    args = _arguments()
    document = json.loads(args.path_presentation.read_text())
    config = _expanded_config(
        maximum_detected_tracks=args.maximum_detected_tracks,
        peak_candidates=args.peak_candidates,
    )
    points = pilot_scan_points(document["pilot_scan"])
    parents, _, tracks = _residual_hough_inventory(points, config)
    tracks = sorted(
        tracks,
        key=lambda track: (
            track.start_s,
            track.end_s,
            track.slope_hz_per_s,
            track.track_id,
        ),
    )

    source = _png_source(
        (
            f"{document['session_id']} · {document['stream_id']}/{document['radio_id']}/"
            f"RX{document['receiver_id']} · expanded Hough: {len(parents)} parents, "
            f"{len(tracks)} untruncated linear proposals"
        ),
        "expanded-hough-diagnostic",
        (document,),
    )
    path = replace(
        source.paths[0],
        trajectory_table={"trajectories": [_trajectory_row(track) for track in tracks]},
    )
    source = replace(source, paths=(path,))

    args.output_png.parent.mkdir(parents=True, exist_ok=True)
    args.output_png.write_bytes(
        render_full_standard_plot_png(
            source,
            StandardViewKindV2.CFO_TRAJECTORY,
            show_legend=False,
        )
    )
    sidecar = args.output_png.with_suffix(".json")
    sidecar.write_text(
        json.dumps(
            {
                "source_path_presentation": str(args.path_presentation),
                "source_point_count": len(points),
                "eligible_point_count": sum(point.weight >= 0.5 for point in points),
                "initial_parent_count": len(parents),
                "returned_track_count": len(tracks),
                "active_count_limit_hit": len(parents) >= args.maximum_detected_tracks,
                "configuration": config.model_dump(mode="json"),
                "tracks": [
                    {
                        "track_id": str(track.track_id),
                        "parent_track_id": str(track.source_parent_track_id),
                        "start_s": track.start_s,
                        "end_s": track.end_s,
                        "slope_hz_per_s": track.slope_hz_per_s,
                        "hard_support_count": track.support_count,
                        "weighted_support": track.weighted_support,
                        "residual_rms_hz": track.residual_rms_hz,
                    }
                    for track in tracks
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
