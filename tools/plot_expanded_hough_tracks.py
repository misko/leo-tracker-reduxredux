#!/usr/bin/env python3
"""Plot expanded, untruncated residual-Hough inventories for persisted paths."""

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
    parser.add_argument(
        "source",
        type=Path,
        help="one path-presentation JSON or a run root containing all path presentations",
    )
    parser.add_argument("output_png", type=Path)
    parser.add_argument("--maximum-detected-tracks", type=int, default=32)
    parser.add_argument("--peak-candidates", type=int, default=64)
    return parser.parse_args()


def _presentation_paths(source: Path) -> tuple[Path, ...]:
    if source.is_file():
        return (source,)
    paths = tuple(
        sorted(
            source.glob(
                "presentation/path-standard/*/standard.path-presentation.v4.json"
            )
        )
    )
    if not paths:
        raise ValueError(f"no path presentations found beneath {source}")
    if len(paths) > 4:
        raise ValueError(f"expected at most four path presentations, found {len(paths)}")
    return paths


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
    presentation_paths = _presentation_paths(args.source)
    documents = tuple(json.loads(path.read_text()) for path in presentation_paths)
    config = _expanded_config(
        maximum_detected_tracks=args.maximum_detected_tracks,
        peak_candidates=args.peak_candidates,
    )
    inventories: dict[tuple[str, int], dict[str, Any]] = {}
    for source_path, document in zip(presentation_paths, documents, strict=True):
        points = pilot_scan_points(document["pilot_scan"])
        parents, _, raw_tracks = _residual_hough_inventory(points, config)
        tracks = sorted(
            raw_tracks,
            key=lambda track: (
                track.start_s,
                track.end_s,
                track.slope_hz_per_s,
                track.track_id,
            ),
        )
        inventories[(str(document["stream_id"]), int(document["receiver_id"]))] = {
            "source_path": source_path,
            "points": points,
            "parents": parents,
            "tracks": tracks,
        }

    source = _png_source(
        f"{documents[0]['session_id']} · expanded Hough · untruncated linear proposals",
        "expanded-hough-diagnostic",
        documents,
    )
    expanded_paths = []
    for path, document in zip(
        source.paths,
        sorted(documents, key=lambda item: (item["stream_id"], item["receiver_id"])),
        strict=True,
    ):
        inventory = inventories[(str(document["stream_id"]), int(document["receiver_id"]))]
        parents = inventory["parents"]
        tracks = inventory["tracks"]
        expanded_paths.append(
            replace(
                path,
                label=(
                    f"{path.label} · {len(parents)} parents · "
                    f"{len(tracks)} untruncated proposals"
                ),
                trajectory_table={
                    "trajectories": [_trajectory_row(track) for track in tracks]
                },
            )
        )
    source = replace(
        source,
        paths=tuple(expanded_paths),
    )

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
                "source": str(args.source),
                "configuration": config.model_dump(mode="json"),
                "paths": [
                    {
                        "source_path_presentation": str(inventory["source_path"]),
                        "stream_id": stream_id,
                        "receiver_id": receiver_id,
                        "source_point_count": len(inventory["points"]),
                        "eligible_point_count": sum(
                            point.weight >= 0.5 for point in inventory["points"]
                        ),
                        "initial_parent_count": len(inventory["parents"]),
                        "returned_track_count": len(inventory["tracks"]),
                        "active_count_limit_hit": (
                            len(inventory["parents"])
                            >= args.maximum_detected_tracks
                        ),
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
                            for track in inventory["tracks"]
                        ],
                    }
                    for (stream_id, receiver_id), inventory in sorted(inventories.items())
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
