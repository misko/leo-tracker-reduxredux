#!/usr/bin/env python3
"""Render raw-GLRT context for the piecewise pilot Doppler-rate report.

The default invocation reads only the exact persisted Standard products used by
the report.  It does not open raw IQ, rerun a detector, or mutate the analysis
corpus.  "Raw GLRT" here means the independent-search GLRT64 candidate values
persisted before trajectory correction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

SESSION_ID = "cap-20260821T140820-470384cc9284"
ANALYSIS_SCOPE = "sha256:ccdc4b152617f6e99b23044948cea7be040905cf1e7dd074bb36668b36dc0963"
TARGET_BRANCH_PREFIX = "sha256:5852a936"
DEFAULT_ANALYSIS_ROOT = Path(
    "/srv/bulk/leo/analysis/cap-20260821T140820-470384cc9284/"
    "capture-438ad263e01048ef82f660975ec55a08/scientific/path-standard/" + ANALYSIS_SCOPE
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_piecewise_pilot_doppler_rate")

BLUE = "#2678a8"
GREEN = "#4f9b66"
AMBER = "#d28a29"
RED = "#c44e52"
PURPLE = "#7f62a6"
INK = "#193549"
GRAY = "#728694"


@dataclass(frozen=True, slots=True)
class GlrtPoint:
    time_s: float
    cfo_hz: float
    margin: float
    exact_score: float
    control_score: float
    rank: int


@dataclass(frozen=True, slots=True)
class PolynomialTrack:
    trajectory_id: str
    coefficients_hz: tuple[float, ...]
    reference_time_s: float
    start_s: float
    end_s: float
    polynomial_degree: int

    def frequency_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        values = np.polyval(
            np.asarray(self.coefficients_hz),
            np.asarray(time_s) - self.reference_time_s,
        )
        return float(values) if np.ndim(values) == 0 else values


@dataclass(frozen=True, slots=True)
class TargetTrack(PolynomialTrack):
    branch_id: str


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-root", type=Path, default=DEFAULT_ANALYSIS_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--start-s", type=float, default=33.7)
    parser.add_argument("--end-s", type=float, default=37.7)
    parser.add_argument("--minimum-glrt64-margin", type=float, default=0.05)
    parser.add_argument("--maximum-model-error-hz", type=float, default=2_500.0)
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _glrt64_score(candidate: dict[str, Any]) -> dict[str, Any]:
    scores = [item for item in candidate["scores"] if item["method"] == "glrt64"]
    if len(scores) != 1:
        raise ValueError("candidate does not contain exactly one GLRT64 score")
    return scores[0]


def _raw_glrt_points(scan: dict[str, Any]) -> tuple[GlrtPoint, ...]:
    points: list[GlrtPoint] = []
    for detection in scan["detections"]:
        for candidate in detection["candidates"]:
            score = _glrt64_score(candidate)
            points.append(
                GlrtPoint(
                    time_s=float(detection["time_s"]),
                    cfo_hz=float(score["tracking_cfo_hz"]),
                    margin=float(score["margin"]),
                    exact_score=float(score["exact_score"]),
                    control_score=float(score["control_score"]),
                    rank=int(candidate["rank"]),
                )
            )
    return tuple(points)


def _raw_tracks(document: dict[str, Any]) -> tuple[PolynomialTrack, ...]:
    tracks = tuple(
        PolynomialTrack(
            trajectory_id=str(item["trajectory_id"]),
            coefficients_hz=tuple(float(value) for value in item["coefficients_hz"]),
            reference_time_s=float(item["reference_time_s"]),
            start_s=float(item["start_s"]),
            end_s=float(item["end_s"]),
            polynomial_degree=int(item["polynomial_degree"]),
        )
        for item in document["trajectories"]
    )
    if any(len(item.coefficients_hz) != item.polynomial_degree + 1 for item in tracks):
        raise ValueError("raw trajectory polynomial geometry is inconsistent")
    return tracks


def _target_track(document: dict[str, Any]) -> TargetTrack:
    matches = [
        item
        for item in document["trajectories"]
        if str(item["branch_id"]).startswith(TARGET_BRANCH_PREFIX)
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one target branch, found {len(matches)}")
    item = matches[0]
    coefficients = tuple(float(value) for value in item["absolute_coefficients_hz"])
    degree = int(item["polynomial_degree"])
    if len(coefficients) != degree + 1:
        raise ValueError("target trajectory polynomial geometry is inconsistent")
    return TargetTrack(
        trajectory_id=str(item["trajectory_id"]),
        coefficients_hz=coefficients,
        reference_time_s=float(item["reference_time_s"]),
        start_s=float(item["start_s"]),
        end_s=float(item["end_s"]),
        polynomial_degree=degree,
        branch_id=str(item["branch_id"]),
    )


def _selected_dense_windows(
    scan: dict[str, Any],
    target: TargetTrack,
    *,
    start_s: float,
    end_s: float,
    minimum_margin: float,
    maximum_model_error_hz: float,
) -> tuple[GlrtPoint, ...]:
    selected: list[GlrtPoint] = []
    for detection in scan["detections"]:
        time_s = float(detection["time_s"])
        if not start_s <= time_s <= end_s:
            continue
        model_hz = float(target.frequency_hz(time_s))
        eligible: list[tuple[float, GlrtPoint]] = []
        for candidate in detection["candidates"]:
            score = _glrt64_score(candidate)
            point = GlrtPoint(
                time_s=time_s,
                cfo_hz=float(score["tracking_cfo_hz"]),
                margin=float(score["margin"]),
                exact_score=float(score["exact_score"]),
                control_score=float(score["control_score"]),
                rank=int(candidate["rank"]),
            )
            if point.margin < minimum_margin:
                continue
            eligible.append((abs(point.cfo_hz - model_hz), point))
        if not eligible:
            continue
        error_hz, point = min(eligible, key=lambda item: item[0])
        if error_hz <= maximum_model_error_hz:
            selected.append(point)
    return tuple(selected)


def _plot_style() -> dict[str, Any]:
    return {
        "font.size": 10,
        "axes.labelcolor": INK,
        "axes.titlecolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "text.color": INK,
        "grid.color": "#cbd7dd",
        "grid.alpha": 0.35,
        "legend.frameon": False,
        "figure.facecolor": "white",
        "axes.facecolor": "#fbfcfd",
    }


def _save(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=190,
        bbox_inches="tight",
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )
    plt.close(figure)


def _interval_points(
    points: tuple[GlrtPoint, ...], start_s: float, end_s: float
) -> tuple[GlrtPoint, ...]:
    return tuple(item for item in points if start_s <= item.time_s <= end_s)


def _mark_interval_boundaries(axis: Any, start_s: float, end_s: float) -> None:
    axis.axvspan(start_s, end_s, color=AMBER, alpha=0.055, zorder=0)
    axis.axvline(start_s, color=RED, linewidth=1.1, linestyle="--", zorder=6)
    axis.axvline(end_s, color=RED, linewidth=1.1, linestyle="--", zorder=6)


def _plot_glrt_window_context(
    points: tuple[GlrtPoint, ...],
    selected: tuple[GlrtPoint, ...],
    target: TargetTrack,
    *,
    start_s: float,
    end_s: float,
    minimum_margin: float,
    maximum_model_error_hz: float,
    path: Path,
) -> None:
    window = _interval_points(points, start_s, end_s)
    if not window or not selected:
        raise ValueError("GLRT detail interval has no candidate or selected points")
    times = np.asarray([item.time_s for item in window])
    cfo_hz = np.asarray([item.cfo_hz for item in window])
    model_hz = np.asarray(target.frequency_hz(times))
    residual_hz = cfo_hz - model_hz
    neighborhood_hz = max(10_000.0, 4 * maximum_model_error_hz)
    near = np.abs(residual_hz) <= neighborhood_hz
    selected_times = np.asarray([item.time_s for item in selected])
    selected_cfo = np.asarray([item.cfo_hz for item in selected])
    selected_residual = selected_cfo - np.asarray(target.frequency_hz(selected_times))
    selected_margin = np.asarray([item.margin for item in selected])
    model_times = np.linspace(start_s, end_s, 600)

    with plt.rc_context(_plot_style()):
        figure, axes = plt.subplots(3, 1, figsize=(14.5, 11.2), sharex=True)
        figure.subplots_adjust(hspace=0.17)

        axes[0].scatter(
            times,
            cfo_hz / 1e3,
            s=9,
            color=GRAY,
            alpha=0.30,
            linewidths=0,
            rasterized=True,
        )
        axes[0].plot(
            model_times,
            np.asarray(target.frequency_hz(model_times)) / 1e3,
            color=BLUE,
            linewidth=2.4,
        )
        axes[0].scatter(
            selected_times,
            selected_cfo / 1e3,
            s=30,
            color=AMBER,
            marker="^",
            edgecolor="white",
            linewidth=0.45,
            zorder=5,
        )
        axes[0].set_ylabel("Baseband CFO (kHz)")
        probe_count = len({item.time_s for item in window})
        axes[0].set_title(
            f"A · raw field inside the dense window: {len(window):,} candidates, "
            f"{probe_count} probes",
            loc="left",
            fontweight="bold",
        )

        axes[1].scatter(
            times[near],
            residual_hz[near],
            s=14,
            color=GRAY,
            alpha=0.42,
            linewidths=0,
        )
        axes[1].scatter(
            selected_times,
            selected_residual,
            s=32,
            color=AMBER,
            marker="^",
            edgecolor="white",
            linewidth=0.45,
            zorder=5,
        )
        axes[1].axhline(0, color=INK, linewidth=1)
        axes[1].axhline(maximum_model_error_hz, color=RED, linestyle=":", linewidth=1)
        axes[1].axhline(-maximum_model_error_hz, color=RED, linestyle=":", linewidth=1)
        axes[1].set_ylim(-neighborhood_hz, neighborhood_hz)
        axes[1].set_ylabel("Raw GLRT64 minus\nfrozen track (Hz)")
        axes[1].set_title(
            f"B · target neighborhood: nearest positive-margin candidate must be within "
            f"±{maximum_model_error_hz / 1e3:.1f} kHz",
            loc="left",
            fontweight="bold",
        )

        axes[2].scatter(
            times[near],
            np.asarray([item.margin for item, keep in zip(window, near, strict=True) if keep]),
            s=14,
            color=GRAY,
            alpha=0.42,
            linewidths=0,
        )
        axes[2].scatter(
            selected_times,
            selected_margin,
            s=32,
            color=AMBER,
            marker="^",
            edgecolor="white",
            linewidth=0.45,
            zorder=5,
        )
        axes[2].axhline(minimum_margin, color=RED, linestyle=":", linewidth=1.2)
        axes[2].set_ylabel("Exact − control\nGLRT64 margin")
        axes[2].set_xlabel("Capture time (s)")
        axes[2].set_title(
            f"C · raw GLRT64 quality: {len(selected)} timing locks pass margin and model gates",
            loc="left",
            fontweight="bold",
        )

        for axis in axes:
            _mark_interval_boundaries(axis, start_s, end_s)
            axis.set_xlim(start_s - 0.12, end_s + 0.12)
            axis.grid(True)
        axes[0].legend(
            handles=(
                Line2D(
                    [],
                    [],
                    marker="o",
                    linestyle="",
                    color=GRAY,
                    label="raw independent GLRT64 candidate",
                ),
                Line2D([], [], color=BLUE, linewidth=2.4, label="target frozen trajectory"),
                Line2D(
                    [],
                    [],
                    marker="^",
                    linestyle="",
                    color=AMBER,
                    label=f"dense source timing lock ({len(selected)})",
                ),
                Line2D(
                    [],
                    [],
                    color=RED,
                    linestyle="--",
                    label=f"analysis boundaries {start_s:.1f}–{end_s:.1f} s",
                ),
            ),
            loc="lower left",
            ncol=2,
        )
        figure.suptitle(
            "Raw independent-search GLRT64 evidence used to seed the dense pilot analysis\n"
            "before trajectory correction · candidate-only · no satellite attribution",
            fontsize=15,
            fontweight="bold",
            color=INK,
        )
        _save(figure, path)


def _plot_full_glrt_track_context(
    points: tuple[GlrtPoint, ...],
    raw_tracks: tuple[PolynomialTrack, ...],
    selected: tuple[GlrtPoint, ...],
    target: TargetTrack,
    *,
    start_s: float,
    end_s: float,
    path: Path,
) -> None:
    if not points or not raw_tracks:
        raise ValueError("full GLRT context requires candidates and raw tracks")
    times = np.asarray([item.time_s for item in points])
    cfo_khz = np.asarray([item.cfo_hz for item in points]) / 1e3
    selected_times = np.asarray([item.time_s for item in selected])
    selected_khz = np.asarray([item.cfo_hz for item in selected]) / 1e3
    degree_style = {
        1: (BLUE, "--"),
        2: (GREEN, "-."),
        3: (PURPLE, ":"),
    }

    with plt.rc_context(_plot_style()):
        figure, axis = plt.subplots(figsize=(15.5, 7.2))
        axis.scatter(
            times,
            cfo_khz,
            s=7,
            color=GRAY,
            alpha=0.22,
            linewidths=0,
            rasterized=True,
            zorder=1,
        )
        _mark_interval_boundaries(axis, start_s, end_s)
        for track in raw_tracks:
            color, linestyle = degree_style[track.polynomial_degree]
            track_times = np.linspace(track.start_s, track.end_s, 240)
            axis.plot(
                track_times,
                np.asarray(track.frequency_hz(track_times)) / 1e3,
                color=color,
                linestyle=linestyle,
                linewidth=1.35,
                alpha=0.82,
                zorder=3,
            )
        target_times = np.linspace(target.start_s, target.end_s, 600)
        axis.plot(
            target_times,
            np.asarray(target.frequency_hz(target_times)) / 1e3,
            color=INK,
            linewidth=3.0,
            zorder=4,
        )
        axis.scatter(
            selected_times,
            selected_khz,
            s=28,
            color=AMBER,
            marker="^",
            edgecolor="white",
            linewidth=0.4,
            zorder=5,
        )
        axis.set_xlim(float(np.min(times)), float(np.max(times)))
        padding_khz = 0.035 * float(np.ptp(cfo_khz))
        axis.set_ylim(float(np.min(cfo_khz) - padding_khz), float(np.max(cfo_khz) + padding_khz))
        axis.set_xlabel("Elapsed recording time (s)")
        axis.set_ylabel("Baseband CFO (kHz)")
        axis.grid(True)
        axis.set_title(
            f"Full persisted GLRT64 field: {len(points):,} raw candidates and "
            f"{len(raw_tracks)} fitted trajectories\n"
            f"highlighted dense-analysis window = {start_s:.1f}–{end_s:.1f} s",
            fontsize=15,
            fontweight="bold",
        )
        axis.legend(
            handles=(
                Line2D(
                    [],
                    [],
                    marker="o",
                    linestyle="",
                    color=GRAY,
                    label="raw independent GLRT64 candidate",
                ),
                Line2D([], [], color=BLUE, linestyle="--", label="raw degree-1 fit"),
                Line2D([], [], color=GREEN, linestyle="-.", label="raw degree-2 fit"),
                Line2D([], [], color=PURPLE, linestyle=":", label="raw degree-3 fit"),
                Line2D([], [], color=INK, linewidth=3, label="final target cubic / frozen model"),
                Line2D(
                    [],
                    [],
                    marker="^",
                    linestyle="",
                    color=AMBER,
                    label=f"dense source timing lock ({len(selected)})",
                ),
                Patch(facecolor=AMBER, alpha=0.15, label="dense-analysis time window"),
            ),
            loc="lower left",
            ncol=3,
        )
        _save(figure, path)


def _write_evidence(
    path: Path,
    *,
    analysis_root: Path,
    scan_path: Path,
    raw_table_path: Path,
    final_bank_path: Path,
    points: tuple[GlrtPoint, ...],
    raw_tracks: tuple[PolynomialTrack, ...],
    selected: tuple[GlrtPoint, ...],
    target: TargetTrack,
    start_s: float,
    end_s: float,
    minimum_margin: float,
    maximum_model_error_hz: float,
    figures: tuple[Path, ...],
) -> None:
    window = _interval_points(points, start_s, end_s)
    document = {
        "schema_version": 1,
        "algorithm": "piecewise-pilot-doppler-raw-glrt-context-v1",
        "input": {
            "session_id": SESSION_ID,
            "analysis_scope": ANALYSIS_SCOPE,
            "analysis_root": str(analysis_root),
            "pilot_scan": {"path": scan_path.name, "sha256": _sha256(scan_path)},
            "raw_trajectory_table": {
                "path": raw_table_path.name,
                "sha256": _sha256(raw_table_path),
            },
            "final_trajectory_bank": {
                "path": final_bank_path.name,
                "sha256": _sha256(final_bank_path),
            },
        },
        "inventory": {
            "full_detection_count": len({item.time_s for item in points}),
            "full_raw_glrt64_candidate_count": len(points),
            "raw_track_count": len(raw_tracks),
            "raw_track_count_by_degree": {
                str(degree): sum(item.polynomial_degree == degree for item in raw_tracks)
                for degree in (1, 2, 3)
            },
            "window_start_s": start_s,
            "window_end_s": end_s,
            "window_detection_count": len({item.time_s for item in window}),
            "window_raw_glrt64_candidate_count": len(window),
            "dense_source_timing_lock_count": len(selected),
        },
        "selection": {
            "rule": (
                "per probe, retain the positive-margin GLRT64 candidate nearest the target "
                "frozen model, then require its absolute model error to pass the declared gate"
            ),
            "minimum_glrt64_margin": minimum_margin,
            "maximum_model_error_hz": maximum_model_error_hz,
        },
        "target": asdict(target),
        "figures": [
            {"path": item.name, "sha256": _sha256(item), "bytes": item.stat().st_size}
            for item in figures
        ],
        "candidate_only": True,
        "payload_decoded": False,
        "satellite_attribution_claimed": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = _arguments()
    if (
        not math.isfinite(args.start_s)
        or not math.isfinite(args.end_s)
        or args.end_s <= args.start_s
    ):
        raise ValueError("report interval must be finite and increasing")
    if args.minimum_glrt64_margin < 0 or args.maximum_model_error_hz <= 0:
        raise ValueError("selection gates must be nonnegative and positive")

    scan_path = args.analysis_root / "standard.pilot-scan.v3.json"
    raw_table_path = args.analysis_root / "standard.glrt64-trajectory-table.v2.json"
    final_bank_path = args.analysis_root / "standard.final-trajectory-bank.v2.json"
    scan = _load_json(scan_path)
    points = _raw_glrt_points(scan)
    raw_tracks = _raw_tracks(_load_json(raw_table_path))
    target = _target_track(_load_json(final_bank_path))
    selected = _selected_dense_windows(
        scan,
        target,
        start_s=args.start_s,
        end_s=args.end_s,
        minimum_margin=args.minimum_glrt64_margin,
        maximum_model_error_hz=args.maximum_model_error_hz,
    )

    figures = (
        args.output_root / "raw-glrt-window.png",
        args.output_root / "full-glrt-track-context.png",
    )
    _plot_glrt_window_context(
        points,
        selected,
        target,
        start_s=args.start_s,
        end_s=args.end_s,
        minimum_margin=args.minimum_glrt64_margin,
        maximum_model_error_hz=args.maximum_model_error_hz,
        path=figures[0],
    )
    _plot_full_glrt_track_context(
        points,
        raw_tracks,
        selected,
        target,
        start_s=args.start_s,
        end_s=args.end_s,
        path=figures[1],
    )
    _write_evidence(
        args.output_root / "glrt-context.json",
        analysis_root=args.analysis_root,
        scan_path=scan_path,
        raw_table_path=raw_table_path,
        final_bank_path=final_bank_path,
        points=points,
        raw_tracks=raw_tracks,
        selected=selected,
        target=target,
        start_s=args.start_s,
        end_s=args.end_s,
        minimum_margin=args.minimum_glrt64_margin,
        maximum_model_error_hz=args.maximum_model_error_hz,
        figures=figures,
    )
    print(
        f"rendered {len(figures)} GLRT context figures from {len(points)} candidates, "
        f"{len(raw_tracks)} raw track fits, and {len(selected)} dense source locks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
