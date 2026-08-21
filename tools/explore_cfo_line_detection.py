#!/usr/bin/env python3
"""Run bounded offline line detectors on a persisted Standard pilot-scan product."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.research.cfo_lines import (
    CfoPoint,
    DynamicProgrammingConfig,
    HoughConfig,
    LineSegment,
    RansacConfig,
    dynamic_programming_lines,
    robust_ransac_lines,
    weighted_hough_lines,
    with_common,
)

SESSION_ID = "cap-20260821T001023-1cafa7c30c52"
SCOPE = "radio_pluto_5d4d / stream-0 / RX1"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-scan", type=Path, required=True)
    parser.add_argument("--dealiased", type=Path)
    parser.add_argument("--final", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--maximum-tracks", type=int, default=10)
    return parser.parse_args()


def load_glrt64_points(path: Path) -> tuple[CfoPoint, ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 3 or "glrt64" not in document.get("methods", []):
        raise ValueError("input must be a Standard pilot-scan v3 product containing GLRT64")
    result = []
    for detection_index, detection in enumerate(document["detections"]):
        for candidate in detection["candidates"]:
            score = next(
                (item for item in candidate["scores"] if item["method"] == "glrt64"),
                None,
            )
            if score is None:
                continue
            result.append(
                CfoPoint(
                    point_id=(
                        f"probe-{detection_index:04d}-sample-{int(detection['sample_start'])}"
                        f"-rank-{int(candidate['rank'])}"
                    ),
                    time_s=float(detection["time_s"]),
                    frequency_hz=float(score["tracking_cfo_hz"]),
                    exact_score=float(score["exact_score"]),
                    control_score=float(score["control_score"]),
                    margin=float(score["margin"]),
                )
            )
    if not result:
        raise ValueError("pilot scan contains no GLRT64 candidate points")
    return tuple(result)


def _reference_branches(path: Path | None) -> tuple[dict[str, Any], ...]:
    if path is None:
        return ()
    document = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for branch in document["branches"]:
        model = next(
            item for item in branch["models"] if item["model_id"] == branch["selected_model_id"]
        )
        result.append(
            {
                "branch_id": branch["branch_id"],
                "short_id": branch["branch_id"].removeprefix("sha256:")[:8],
                "start_s": float(branch["start_s"]),
                "end_s": float(branch["end_s"]),
                "reference_time_s": float(model["reference_time_s"]),
                "coefficients_hz": tuple(float(value) for value in model["coefficients_hz"]),
                "support": len(branch["observation_ids"]),
                "residual_rms_hz": float(model["residual_rms_hz"]),
            }
        )
    return tuple(result)


def _compare_reference(
    segment: LineSegment,
    reference: dict[str, Any],
    alias_spacing_hz: float,
) -> dict[str, Any] | None:
    start = max(segment.start_s, reference["start_s"])
    end = min(segment.end_s, reference["end_s"])
    if end <= start:
        return None
    sample = np.linspace(start, end, 128)
    detected = segment.slope_hz_per_s * sample + segment.intercept_hz
    expected = np.polyval(reference["coefficients_hz"], sample - reference["reference_time_s"])
    residual = (
        detected - expected + alias_spacing_hz / 2.0
    ) % alias_spacing_hz - alias_spacing_hz / 2.0
    return {
        "branch_id": reference["branch_id"],
        "short_id": reference["short_id"],
        "overlap_s": float(end - start),
        "modulo_alias_rms_hz": float(np.sqrt(np.mean(residual**2))),
        "modulo_alias_max_hz": float(np.max(np.abs(residual))),
    }


def _run(
    points: tuple[CfoPoint, ...], maximum_tracks: int
) -> tuple[dict[str, tuple[LineSegment, ...]], dict[str, float]]:
    detections: dict[str, tuple[LineSegment, ...]] = {}
    runtimes: dict[str, float] = {}
    started = time.perf_counter()
    detections["weighted_hough"] = weighted_hough_lines(
        points, with_common(HoughConfig(), maximum_tracks=maximum_tracks)
    )
    runtimes["weighted_hough"] = time.perf_counter() - started
    started = time.perf_counter()
    detections["robust_ransac"] = robust_ransac_lines(
        points, with_common(RansacConfig(), maximum_tracks=maximum_tracks)
    )
    runtimes["robust_ransac"] = time.perf_counter() - started
    started = time.perf_counter()
    detections["dynamic_programming"] = dynamic_programming_lines(
        points, with_common(DynamicProgrammingConfig(), maximum_tracks=maximum_tracks)
    )
    runtimes["dynamic_programming"] = time.perf_counter() - started
    return detections, runtimes


def _plot(
    path: Path,
    points: tuple[CfoPoint, ...],
    detections: dict[str, tuple[LineSegment, ...]],
    references: tuple[dict[str, Any], ...],
    *,
    start_s: float,
    end_s: float,
    title: str,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    alias_spacing = 1.0 / 4.4e-6
    times = np.asarray([point.time_s for point in points])
    frequency = np.asarray([point.frequency_hz for point in points])
    margin = np.asarray([point.margin for point in points])
    names = tuple(detections)
    figure, axes = plt.subplots(len(names), 1, figsize=(16, 12), sharex=True, sharey=True)
    colors = ("#d73027", "#1a9850", "#4575b4", "#984ea3", "#e6ab02", "#1b9e77")
    for axis, name in zip(axes, names, strict=True):
        visible = (times >= start_s) & (times <= end_s)
        axis.scatter(
            times[visible],
            frequency[visible] / 1_000.0,
            s=3,
            color="#aeb7c2",
            alpha=0.16,
            linewidths=0,
            rasterized=True,
            label="all retained independent-search candidates",
        )
        strong = visible & (margin >= 0.05)
        axis.scatter(
            times[strong],
            frequency[strong] / 1_000.0,
            s=10,
            c=margin[strong],
            cmap="viridis",
            vmin=0.05,
            vmax=0.65,
            alpha=0.72,
            linewidths=0,
            rasterized=True,
            label="GLRT64 margin ≥ 0.05",
        )
        for index, segment in enumerate(detections[name]):
            segment_start = max(start_s, segment.start_s)
            segment_end = min(end_s, segment.end_s)
            if segment_end <= segment_start:
                continue
            dense = np.linspace(segment_start, segment_end, 160)
            base = segment.slope_hz_per_s * dense + segment.intercept_hz
            for alias in range(-3, 4):
                curve = base + alias * alias_spacing
                mask = (curve >= -525_000.0) & (curve <= 525_000.0)
                axis.plot(
                    dense[mask],
                    curve[mask] / 1_000.0,
                    color=colors[index % len(colors)],
                    linewidth=1.9,
                    alpha=0.88,
                )
            axis.plot(
                [],
                [],
                color=colors[index % len(colors)],
                linewidth=2,
                label=(
                    f"L{index + 1}: n={segment.support}, "
                    f"{segment.slope_hz_per_s / 1_000:.2f} kHz/s, "
                    f"RMS={segment.residual_rms_hz:.0f} Hz"
                ),
            )
        for reference in references:
            overlap_start = max(start_s, reference["start_s"])
            overlap_end = min(end_s, reference["end_s"])
            if overlap_end <= overlap_start:
                continue
            dense = np.linspace(overlap_start, overlap_end, 160)
            base = np.polyval(reference["coefficients_hz"], dense - reference["reference_time_s"])
            for alias in range(-3, 4):
                curve = base + alias * alias_spacing
                mask = (curve >= -525_000.0) & (curve <= 525_000.0)
                axis.plot(
                    dense[mask],
                    curve[mask] / 1_000.0,
                    color="black",
                    linestyle="--",
                    linewidth=1.0,
                    alpha=0.8,
                )
            axis.plot([], [], "k--", linewidth=1, label=f"Standard branch {reference['short_id']}")
        axis.set_title(name.replace("_", " ").title(), loc="left")
        axis.set_ylabel("Raw GLRT64 CFO (kHz)")
        axis.set_xlim(start_s, end_s)
        axis.set_ylim(-525.0, 525.0)
        axis.grid(alpha=0.16)
        axis.legend(loc="upper left", ncol=2, fontsize=7)
    axes[-1].set_xlabel("Recording time (s)")
    figure.suptitle(
        title
        + "\nFixed axes · dashed: current de-aliased branches · solid: offline line detections"
    )
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def main() -> None:
    args = _arguments()
    args.output_root.mkdir(parents=True, exist_ok=True)
    points = load_glrt64_points(args.pilot_scan)
    references = _reference_branches(args.dealiased)
    detections, runtimes = _run(points, args.maximum_tracks)
    alias_spacing = 1.0 / 4.4e-6
    output: dict[str, Any] = {
        "schema": "org.leo.research.cfo-line-detection/v1",
        "session_id": SESSION_ID,
        "scope": SCOPE,
        "source": {
            "pilot_scan": str(args.pilot_scan),
            "dealiased": None if args.dealiased is None else str(args.dealiased),
            "final": None if args.final is None else str(args.final),
            "point_count": len(points),
            "strong_margin_point_count": sum(point.margin >= 0.05 for point in points),
            "unique_probe_count": len({_time_key(point.time_s) for point in points}),
        },
        "alias_spacing_hz": alias_spacing,
        "algorithms": {},
    }
    for name, segments in detections.items():
        output["algorithms"][name] = {
            "runtime_s": runtimes[name],
            "segment_count": len(segments),
            "segments": [
                {
                    **asdict(segment),
                    "reference_comparisons": [
                        comparison
                        for reference in references
                        if (comparison := _compare_reference(segment, reference, alias_spacing))
                        is not None
                    ],
                }
                for segment in segments
            ],
        }
    report_path = args.output_root / "metrics.json"
    report_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _plot(
        args.output_root / "full-duration.png",
        points,
        detections,
        references,
        start_s=0.0,
        end_s=60.0,
        title=f"{SESSION_ID} · {SCOPE} · GLRT64 CFO line finding",
    )
    _plot(
        args.output_root / "late-branch-zoom.png",
        points,
        detections,
        references,
        start_s=38.0,
        end_s=60.0,
        title=f"Late-branch zoom · {SCOPE} · includes 68fe3fe1 and d9e9d74c",
    )
    print(report_path)


def _time_key(time_s: float) -> int:
    return int(round(time_s * 1_000_000_000.0))


if __name__ == "__main__":
    main()
