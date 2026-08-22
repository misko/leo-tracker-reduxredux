#!/usr/bin/env python3
"""Rerun a dense, per-probe independent GLRT search on one recorded receiver path."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
)
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    detect_pilot_method_candidates,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.states import StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore

DEFAULT_SESSION_ID = "cap-20260821T201522-841b2a20e151"
DEFAULT_BASELINE = Path(
    "/srv/bulk/leo/analysis/cap-20260821T201522-841b2a20e151/"
    "capture-fb15d5f27c1c43b2b1c4f3fcf9fd13cf/scientific/path-standard/"
    "sha256:8725a64ff58c01ffc7fb1754cefafe1f92a2ffdd9a993cec31a9b0c73eeaae39/"
    "standard.pilot-scan.v3.json"
)


@dataclass(frozen=True, slots=True)
class CandidateRow:
    sample_start: int
    time_s: float
    rank: int
    local_epoch_sample: int
    acquired_cfo_hz: float
    tracking_cfo_hz: float
    residual_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float
    anchor_margin: float
    symbolwise_margin: float
    qam_accuracy: float | None


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", default=DEFAULT_SESSION_ID)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--stream", default="stream-0")
    parser.add_argument("--receiver", type=int, default=1)
    parser.add_argument("--edge", choices=("lower", "upper"), default="upper")
    parser.add_argument("--start-s", type=float, default=0.0)
    parser.add_argument("--end-s", type=float, default=27.25)
    parser.add_argument("--probe-ms", type=float, default=20.0)
    parser.add_argument("--probe-spacing-ms", type=float, default=25.0)
    parser.add_argument("--coarse-cfo-step-hz", type=float, default=10_000.0)
    parser.add_argument("--fine-cfo-radius-hz", type=float, default=10_000.0)
    parser.add_argument("--fine-cfo-step-hz", type=float, default=100.0)
    parser.add_argument("--conditioned-cfo-radius-hz", type=float, default=1_000.0)
    parser.add_argument("--conditioned-cfo-step-hz", type=float, default=25.0)
    parser.add_argument("--candidate-count", type=int, default=32)
    parser.add_argument("--candidate-cfo-separation-hz", type=float, default=10_000.0)
    parser.add_argument("--candidate-epoch-separation-samples", type=int, default=5)
    parser.add_argument("--glrt-size", type=int, default=4_096)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--candidate-output-only",
        action="store_true",
        help=(
            "persist independently scored candidate rows and run metadata without "
            "rendering the historical T1-specific summary"
        ),
    )
    parser.add_argument("--baseline-pilot-scan", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--line-rate-hz-s", type=float, default=-6_527.349480985292)
    parser.add_argument("--line-intercept-hz", type=float, default=-52_915.16263503293)
    parser.add_argument("--line-reference-s", type=float, default=16.178076169)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 block must have shape (samples,1,2)")
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / 32_768.0


def _score(candidate, method: PilotMethod):
    return next(item for item in candidate.scores if item.method is method)


def _detect_one(
    request: tuple[int, np.ndarray],
    *,
    sample_rate_hz: int,
    calibration: ReceiverFrequencyCalibration,
    config: SymbolwiseAcquisitionConfig,
    edge: StarlinkEdge,
    candidate_count: int,
    glrt_size: int,
) -> tuple[CandidateRow, ...]:
    sample_start, samples = request
    detection = detect_pilot_method_candidates(
        samples,
        sample_rate_hz,
        sample_start=sample_start,
        calibration=calibration,
        acquisition_config=config,
        edge=edge,
        maximum_scored_candidates=candidate_count,
        glrt_size=glrt_size,
    )
    result = []
    for candidate in detection.candidates:
        glrt = _score(candidate, PilotMethod.GLRT64)
        anchor = _score(candidate, PilotMethod.ANCHOR8)
        symbolwise = _score(candidate, PilotMethod.SYMBOLWISE)
        result.append(
            CandidateRow(
                sample_start=sample_start,
                time_s=sample_start / sample_rate_hz,
                rank=int(candidate.rank),
                local_epoch_sample=int(candidate.local_epoch_sample),
                acquired_cfo_hz=float(candidate.acquired_cfo_hz),
                tracking_cfo_hz=float(glrt.tracking_cfo_hz),
                residual_cfo_hz=float(glrt.residual_cfo_hz),
                exact_score=float(glrt.exact_score),
                control_score=float(glrt.control_score),
                margin=float(glrt.margin),
                anchor_margin=float(anchor.margin),
                symbolwise_margin=float(symbolwise.margin),
                qam_accuracy=(
                    None if candidate.qam_accuracy is None else float(candidate.qam_accuracy)
                ),
            )
        )
    return tuple(result)


def _baseline_rows(path: Path, start_s: float, end_s: float) -> tuple[CandidateRow, ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for detection in document["detections"]:
        time_s = float(detection["time_s"])
        if not start_s <= time_s < end_s:
            continue
        for candidate in detection["candidates"]:
            scores = {item["method"]: item for item in candidate["scores"]}
            glrt = scores["glrt64"]
            result.append(
                CandidateRow(
                    sample_start=int(detection["sample_start"]),
                    time_s=time_s,
                    rank=int(candidate["rank"]),
                    local_epoch_sample=int(candidate["local_epoch_sample"]),
                    acquired_cfo_hz=float(candidate["acquired_cfo_hz"]),
                    tracking_cfo_hz=float(glrt["tracking_cfo_hz"]),
                    residual_cfo_hz=float(glrt["residual_cfo_hz"]),
                    exact_score=float(glrt["exact_score"]),
                    control_score=float(glrt["control_score"]),
                    margin=float(glrt["margin"]),
                    anchor_margin=float(scores["anchor8"]["margin"]),
                    symbolwise_margin=float(scores["symbolwise"]["margin"]),
                    qam_accuracy=(
                        None
                        if candidate.get("qam_accuracy") is None
                        else float(candidate["qam_accuracy"])
                    ),
                )
            )
    return tuple(result)


def _candidate_run_metadata(
    args: argparse.Namespace,
    config: SymbolwiseAcquisitionConfig,
    dense: tuple[CandidateRow, ...],
    runtime_s: float,
) -> dict[str, Any]:
    return {
        "schema": "org.leo.research.dense-independent-glrt-candidates/v1",
        "session_id": args.session_id,
        "path": f"{args.stream}/RX{args.receiver}",
        "edge": args.edge,
        "time_interval_s": [args.start_s, args.end_s],
        "probe_ms": args.probe_ms,
        "probe_spacing_ms": args.probe_spacing_ms,
        "residual_cfo_min_hz": config.residual_cfo_min_hz,
        "residual_cfo_max_hz": config.residual_cfo_max_hz,
        "coarse_cfo_step_hz": args.coarse_cfo_step_hz,
        "fine_cfo_radius_hz": args.fine_cfo_radius_hz,
        "fine_cfo_step_hz": args.fine_cfo_step_hz,
        "conditioned_cfo_radius_hz": args.conditioned_cfo_radius_hz,
        "conditioned_cfo_step_hz": args.conditioned_cfo_step_hz,
        "candidate_count": args.candidate_count,
        "candidate_cfo_separation_hz": args.candidate_cfo_separation_hz,
        "candidate_epoch_separation_samples": args.candidate_epoch_separation_samples,
        "glrt_size": args.glrt_size,
        "workers": args.workers,
        "runtime_s": runtime_s,
        "probe_count": len({item.sample_start for item in dense}),
        "scored_candidate_count": len(dense),
        "first_stage_independent": True,
    }


def _write_candidates(path: Path, rows: tuple[CandidateRow, ...]) -> None:
    with path.open("wb") as raw_target:
        compressed = gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=9,
            fileobj=raw_target,
            mtime=0,
        )
        target = io.TextIOWrapper(compressed, encoding="utf-8")
        with target:
            for row in rows:
                target.write(
                    json.dumps(asdict(row), sort_keys=True, separators=(",", ":"))
                    + "\n"
                )


def _group(rows: tuple[CandidateRow, ...]) -> dict[int, tuple[CandidateRow, ...]]:
    result: dict[int, list[CandidateRow]] = {}
    for row in rows:
        result.setdefault(row.sample_start, []).append(row)
    return {
        sample_start: tuple(sorted(values, key=lambda item: item.rank))
        for sample_start, values in result.items()
    }


def _best_glrt(rows: tuple[CandidateRow, ...]) -> CandidateRow:
    return max(rows, key=lambda item: (item.margin, item.exact_score, -item.rank))


def _expected_cfo(args: argparse.Namespace, time_s: float) -> float:
    return args.line_intercept_hz + args.line_rate_hz_s * (time_s - args.line_reference_s)


def _nearest_line(args: argparse.Namespace, rows: tuple[CandidateRow, ...]) -> CandidateRow:
    return min(
        rows,
        key=lambda item: (
            abs(item.tracking_cfo_hz - _expected_cfo(args, item.time_s)),
            -item.margin,
            item.rank,
        ),
    )


def _theil_sen_line(rows: tuple[CandidateRow, ...]) -> tuple[float, float]:
    """Fit a deterministic robust line after independent probe scoring."""

    if len(rows) < 2:
        raise ValueError("robust line requires at least two points")
    slopes = [
        (right.tracking_cfo_hz - left.tracking_cfo_hz) / (right.time_s - left.time_s)
        for index, left in enumerate(rows)
        for right in rows[index + 1 :]
        if right.time_s != left.time_s
    ]
    rate_hz_s = float(np.median(slopes))
    intercept_hz = float(
        np.median([item.tracking_cfo_hz - rate_hz_s * item.time_s for item in rows])
    )
    return rate_hz_s, intercept_hz


def _local_continuity(by_probe: dict[int, tuple[CandidateRow, ...]]) -> dict[str, Any]:
    best = tuple(_best_glrt(rows) for rows in by_probe.values())
    local = tuple(item for item in best if 6.5 <= item.time_s < 8.5 and item.margin >= 0.05)
    rate_hz_s, intercept_hz = _theil_sen_line(local)

    def interval(start_s: float, end_s: float) -> dict[str, Any]:
        selected = tuple(item for item in best if start_s <= item.time_s < end_s)
        residuals = np.asarray(
            [item.tracking_cfo_hz - (rate_hz_s * item.time_s + intercept_hz) for item in selected]
        )
        return {
            "probe_count": len(selected),
            "strong_probe_count": sum(item.margin >= 0.05 for item in selected),
            "median_absolute_residual_hz": float(np.median(np.abs(residuals))),
            "within_500_hz_probe_count": int(np.sum(np.abs(residuals) <= 500.0)),
            "within_1000_hz_probe_count": int(np.sum(np.abs(residuals) <= 1_000.0)),
        }

    return {
        "fit_source_interval_s": [6.5, 8.5],
        "fit_source_strong_probe_count": len(local),
        "rate_hz_s": rate_hz_s,
        "intercept_at_zero_hz": intercept_hz,
        "full_zoom": interval(6.5, 8.5),
        "critical_7_5_to_7_9": interval(7.5, 7.9),
    }


def _paired_best_comparison(
    dense_by_probe: dict[int, tuple[CandidateRow, ...]],
    baseline_by_probe: dict[int, tuple[CandidateRow, ...]],
) -> dict[str, Any]:
    dense_best = {key: _best_glrt(value) for key, value in dense_by_probe.items()}
    baseline_best = {key: _best_glrt(value) for key, value in baseline_by_probe.items()}

    def interval(start_s: float, end_s: float) -> dict[str, Any]:
        pairs = tuple(
            (baseline_best[key], dense_best[key])
            for key in sorted(set(baseline_best) & set(dense_best))
            if start_s <= baseline_best[key].time_s < end_s
        )
        differences = np.asarray(
            [dense.tracking_cfo_hz - baseline.tracking_cfo_hz for baseline, dense in pairs]
        )
        margin_differences = np.asarray(
            [dense.margin - baseline.margin for baseline, dense in pairs]
        )
        return {
            "probe_count": len(pairs),
            "median_absolute_cfo_difference_hz": float(np.median(np.abs(differences))),
            "cfo_difference_p95_hz": float(np.quantile(np.abs(differences), 0.95)),
            "within_500_hz_probe_count": int(np.sum(np.abs(differences) <= 500.0)),
            "median_margin_difference": float(np.median(margin_differences)),
        }

    return {
        "full_interval": interval(-math.inf, math.inf),
        "focus_6_5_to_8_5": interval(6.5, 8.5),
        "critical_7_5_to_7_9": interval(7.5, 7.9),
    }


def _summarize(
    args: argparse.Namespace,
    dense_rows: tuple[CandidateRow, ...],
    baseline_rows: tuple[CandidateRow, ...],
    runtime_s: float,
) -> dict[str, Any]:
    dense_by_probe = _group(dense_rows)
    baseline_by_probe = _group(baseline_rows)
    focus = (7.5, 7.9)

    def population(by_probe: dict[int, tuple[CandidateRow, ...]]) -> dict[str, Any]:
        best = tuple(_best_glrt(rows) for rows in by_probe.values())
        nearest = tuple(_nearest_line(args, rows) for rows in by_probe.values())
        focus_nearest = tuple(item for item in nearest if focus[0] <= item.time_s < focus[1])
        errors = np.asarray(
            [abs(item.tracking_cfo_hz - _expected_cfo(args, item.time_s)) for item in nearest]
        )
        focus_errors = np.asarray(
            [abs(item.tracking_cfo_hz - _expected_cfo(args, item.time_s)) for item in focus_nearest]
        )
        return {
            "probe_count": len(by_probe),
            "candidate_count": sum(len(rows) for rows in by_probe.values()),
            "median_candidates_per_probe": float(
                np.median([len(rows) for rows in by_probe.values()])
            ),
            "best_glrt_margin_ge_0_05_probe_count": sum(item.margin >= 0.05 for item in best),
            "nearest_line_error_median_hz": float(np.median(errors)),
            "nearest_line_within_500_hz_probe_count": int(np.sum(errors <= 500.0)),
            "nearest_line_within_1000_hz_probe_count": int(np.sum(errors <= 1_000.0)),
            "focus_7_5_to_7_9": {
                "probe_count": len(focus_nearest),
                "nearest_line_error_median_hz": float(np.median(focus_errors)),
                "within_500_hz_probe_count": int(np.sum(focus_errors <= 500.0)),
                "within_1000_hz_probe_count": int(np.sum(focus_errors <= 1_000.0)),
                "nearest_candidate_ranks": [item.rank for item in focus_nearest],
                "nearest_candidate_margins": [item.margin for item in focus_nearest],
            },
        }

    return {
        "schema": "org.leo.research.dense-independent-glrt/v1",
        "session_id": args.session_id,
        "path": f"{args.stream}/RX{args.receiver}",
        "time_interval_s": [args.start_s, args.end_s],
        "candidate_only": True,
        "payload_decoded": False,
        "first_stage_independence": (
            "every probe performs a fresh full-range acquisition; no neighboring probe, "
            "trajectory, TLE, or expected-line value enters candidate generation or scoring"
        ),
        "configuration": {
            "probe_ms": args.probe_ms,
            "probe_spacing_ms": args.probe_spacing_ms,
            "cfo_search_hz": [-400_000.0, 400_000.0],
            "coarse_cfo_step_hz": args.coarse_cfo_step_hz,
            "coarse_hypothesis_count": int(800_000 / args.coarse_cfo_step_hz) + 1,
            "fine_cfo_radius_hz": args.fine_cfo_radius_hz,
            "fine_cfo_step_hz": args.fine_cfo_step_hz,
            "conditioned_cfo_radius_hz": args.conditioned_cfo_radius_hz,
            "conditioned_cfo_step_hz": args.conditioned_cfo_step_hz,
            "retained_and_scored_basin_count": args.candidate_count,
            "candidate_cfo_separation_hz": args.candidate_cfo_separation_hz,
            "candidate_epoch_separation_samples": args.candidate_epoch_separation_samples,
            "glrt_size": args.glrt_size,
            "glrt_residual_spacing_hz": 1.0 / (4.4e-6 * args.glrt_size),
        },
        "post_hoc_reference_line": {
            "rate_hz_s": args.line_rate_hz_s,
            "intercept_hz": args.line_intercept_hz,
            "reference_time_s": args.line_reference_s,
            "used_during_search": False,
        },
        "runtime_s": runtime_s,
        "dense": population(dense_by_probe),
        "standard_persisted": population(baseline_by_probe),
        "local_continuity": {
            "dense": _local_continuity(dense_by_probe),
            "standard_persisted": _local_continuity(baseline_by_probe),
        },
        "paired_best_glrt": _paired_best_comparison(dense_by_probe, baseline_by_probe),
        "dense_candidates": [asdict(item) for item in dense_rows],
    }


def _plot(
    path: Path,
    args: argparse.Namespace,
    dense_rows: tuple[CandidateRow, ...],
    baseline_rows: tuple[CandidateRow, ...],
    *,
    start_s: float,
    end_s: float,
    title: str,
) -> None:
    dense = tuple(item for item in dense_rows if start_s <= item.time_s < end_s)
    baseline = tuple(item for item in baseline_rows if start_s <= item.time_s < end_s)
    dense_grouped = _group(dense)
    baseline_grouped = _group(baseline)
    dense_best = tuple(_best_glrt(rows) for rows in dense_grouped.values())
    baseline_best = tuple(_best_glrt(rows) for rows in baseline_grouped.values())
    dense_nearest = tuple(_nearest_line(args, rows) for rows in dense_grouped.values())

    if end_s - start_s <= 3.0:
        line_source = tuple(item for item in dense_best if item.margin >= 0.05)
        reference_rate_hz_s, reference_intercept_hz = _theil_sen_line(line_source)

        def reference(value: float) -> float:
            return reference_rate_hz_s * value + reference_intercept_hz

        dense_nearest = tuple(
            min(
                rows,
                key=lambda item: (
                    abs(item.tracking_cfo_hz - reference(item.time_s)),
                    -item.margin,
                    item.rank,
                ),
            )
            for rows in dense_grouped.values()
        )
        reference_label = "post-hoc local Theil–Sen line"
    else:

        def reference(value: float) -> float:
            return _expected_cfo(args, value)

        reference_label = "post-hoc raw degree-1 reference"

    figure, axes = plt.subplots(
        3,
        1,
        figsize=(14.5, 9.5),
        sharex=True,
        gridspec_kw={"height_ratios": (2.2, 1.0, 1.0)},
    )
    cfo_axis, margin_axis, error_axis = axes
    cfo_axis.scatter(
        [item.time_s for item in dense],
        [item.tracking_cfo_hz / 1_000.0 for item in dense],
        s=2,
        color="#99a3ad",
        alpha=0.08,
        linewidths=0,
        rasterized=True,
        label="all dense-search candidates (up to 32/probe)",
    )
    cfo_axis.scatter(
        [item.time_s for item in baseline_best],
        [item.tracking_cfo_hz / 1_000.0 for item in baseline_best],
        s=11,
        facecolors="none",
        edgecolors="#e17c05",
        linewidths=0.55,
        alpha=0.75,
        label="best persisted Standard GLRT margin",
    )
    cfo_axis.scatter(
        [item.time_s for item in dense_best],
        [item.tracking_cfo_hz / 1_000.0 for item in dense_best],
        s=8,
        color="#277da1",
        alpha=0.8,
        linewidths=0,
        label="best dense-search GLRT margin",
    )
    cfo_axis.scatter(
        [item.time_s for item in dense_nearest],
        [item.tracking_cfo_hz / 1_000.0 for item in dense_nearest],
        s=13,
        marker="x",
        color="#d1495b",
        linewidths=0.55,
        alpha=0.85,
        label="dense candidate nearest post-hoc line",
    )
    times = np.linspace(start_s, end_s, 500)
    reference_khz = np.asarray([reference(value) for value in times]) / 1_000.0
    cfo_axis.plot(
        times,
        reference_khz,
        color="#111111",
        linewidth=0.8,
        linestyle="--",
        label=reference_label,
    )
    margin_axis.scatter(
        [item.time_s for item in baseline_best],
        [item.margin for item in baseline_best],
        s=10,
        facecolors="none",
        edgecolors="#e17c05",
        linewidths=0.5,
        label="persisted best",
    )
    margin_axis.scatter(
        [item.time_s for item in dense_best],
        [item.margin for item in dense_best],
        s=8,
        color="#277da1",
        linewidths=0,
        label="dense best",
    )
    margin_axis.axhline(0.05, color="#7a838c", linewidth=0.8, linestyle=":")
    nearest_error = [item.tracking_cfo_hz - reference(item.time_s) for item in dense_nearest]
    error_axis.scatter(
        [item.time_s for item in dense_nearest],
        np.asarray(nearest_error) / 1_000.0,
        s=9,
        color="#d1495b",
        linewidths=0,
    )
    error_axis.axhline(0.0, color="#111111", linewidth=0.7)
    error_axis.axhspan(-0.5, 0.5, color="#2a9d8f", alpha=0.08)
    for axis in axes:
        axis.grid(alpha=0.14)
        axis.set_xlim(start_s, end_s)
    cfo_axis.set_ylim(float(np.min(reference_khz) - 15.0), float(np.max(reference_khz) + 15.0))
    cfo_axis.set_ylabel("GLRT tracking CFO (kHz)")
    cfo_axis.set_title("A · independent per-probe CFO candidates", loc="left")
    cfo_axis.legend(fontsize=8, ncol=2, loc="best")
    margin_axis.set_ylabel("best GLRT margin")
    margin_axis.set_title("B · best exact-minus-control evidence in each probe", loc="left")
    margin_axis.legend(fontsize=8, ncol=2, loc="best")
    error_axis.set_ylabel("nearest-line error (kHz)")
    error_axis.set_xlabel("capture time (s)")
    error_axis.set_title(
        "C · post-hoc diagnostic only; reference line was not used by the search",
        loc="left",
    )
    figure.suptitle(
        f"{title} · {args.session_id} · {args.stream}/RX{args.receiver}\n"
        f"81 coarse CFO hypotheses · 32 scored basins/probe · GLRT-{args.glrt_size}",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.925))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _markdown(summary: dict[str, Any]) -> str:
    dense = summary["dense"]
    baseline = summary["standard_persisted"]
    dense_focus = dense["focus_7_5_to_7_9"]
    baseline_focus = baseline["focus_7_5_to_7_9"]
    dense_local = summary["local_continuity"]["dense"]["critical_7_5_to_7_9"]
    baseline_local = summary["local_continuity"]["standard_persisted"]["critical_7_5_to_7_9"]
    paired = summary["paired_best_glrt"]["critical_7_5_to_7_9"]
    config = summary["configuration"]
    return "\n".join(
        [
            f"# Dense independent GLRT audit: `{summary['session_id']}`",
            "",
            "## Method",
            "",
            "Every 20 ms probe is acquired and scored independently from the raw IQ. No "
            "neighboring probe, trajectory, TLE, or expected CFO line enters the search. The "
            "degree-1 line is used only afterward to ask whether any retained candidate landed "
            "near the previously visible signal.",
            "",
            "| Parameter | Standard | Dense audit |",
            "|---|---:|---:|",
            f"| Coarse CFO spacing | 80 kHz (11 hypotheses) | "
            f"{config['coarse_cfo_step_hz'] / 1_000:.0f} kHz "
            f"({config['coarse_hypothesis_count']} hypotheses) |",
            f"| Fine CFO spacing | 500 Hz | {config['fine_cfo_step_hz']:.0f} Hz |",
            f"| Conditioned CFO spacing | 100 Hz | {config['conditioned_cfo_step_hz']:.0f} Hz |",
            f"| Scored acquisition basins/probe | "
            f"{baseline['median_candidates_per_probe']:.0f} | "
            f"{config['retained_and_scored_basin_count']} |",
            f"| GLRT residual grid | 512 / 443.9 Hz | {config['glrt_size']} / "
            f"{config['glrt_residual_spacing_hz']:.1f} Hz |",
            "",
            "## Full T1 interval",
            "",
            "![Full dense independent GLRT audit](dense-independent-glrt-full.png)",
            "",
            "## P1 endpoint zoom",
            "",
            "![Dense independent GLRT P1 endpoint zoom](dense-independent-glrt-p1-zoom.png)",
            "",
            "## Numerical comparison",
            "",
            "| Population | Probes | Candidates | Median candidates/probe | "
            "Best margin ≥0.05 | Median nearest-line error | Within 500 Hz | Within 1 kHz |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
            f"| Persisted Standard | {baseline['probe_count']} | "
            f"{baseline['candidate_count']} | {baseline['median_candidates_per_probe']:.1f} | "
            f"{baseline['best_glrt_margin_ge_0_05_probe_count']} | "
            f"{baseline['nearest_line_error_median_hz']:.1f} Hz | "
            f"{baseline['nearest_line_within_500_hz_probe_count']} | "
            f"{baseline['nearest_line_within_1000_hz_probe_count']} |",
            f"| Dense independent | {dense['probe_count']} | {dense['candidate_count']} | "
            f"{dense['median_candidates_per_probe']:.1f} | "
            f"{dense['best_glrt_margin_ge_0_05_probe_count']} | "
            f"{dense['nearest_line_error_median_hz']:.1f} Hz | "
            f"{dense['nearest_line_within_500_hz_probe_count']} | "
            f"{dense['nearest_line_within_1000_hz_probe_count']} |",
            "",
            "### Critical 7.5–7.9 s interval",
            "",
            "| Population | Probes | Median nearest-line error | Within 500 Hz | Within 1 kHz |",
            "|---|---:|---:|---:|---:|",
            f"| Persisted Standard | {baseline_focus['probe_count']} | "
            f"{baseline_focus['nearest_line_error_median_hz']:.1f} Hz | "
            f"{baseline_focus['within_500_hz_probe_count']} | "
            f"{baseline_focus['within_1000_hz_probe_count']} |",
            f"| Dense independent | {dense_focus['probe_count']} | "
            f"{dense_focus['nearest_line_error_median_hz']:.1f} Hz | "
            f"{dense_focus['within_500_hz_probe_count']} | "
            f"{dense_focus['within_1000_hz_probe_count']} |",
            "",
            "The table above uses the old full-track degree-1 line, which does not model the "
            "local piecewise offset. A separate post-hoc Theil–Sen fit to the strongest "
            "independent detections in 6.5–8.5 s gives the continuity check below.",
            "",
            "| Population | Local rate | Critical probes within 500 Hz | Within 1 kHz | "
            "Median absolute residual |",
            "|---|---:|---:|---:|---:|",
            f"| Persisted Standard | "
            f"{summary['local_continuity']['standard_persisted']['rate_hz_s']:+.1f} Hz/s | "
            f"{baseline_local['within_500_hz_probe_count']} / "
            f"{baseline_local['probe_count']} | "
            f"{baseline_local['within_1000_hz_probe_count']} / "
            f"{baseline_local['probe_count']} | "
            f"{baseline_local['median_absolute_residual_hz']:.1f} Hz |",
            f"| Dense independent | "
            f"{summary['local_continuity']['dense']['rate_hz_s']:+.1f} Hz/s | "
            f"{dense_local['within_500_hz_probe_count']} / {dense_local['probe_count']} | "
            f"{dense_local['within_1000_hz_probe_count']} / {dense_local['probe_count']} | "
            f"{dense_local['median_absolute_residual_hz']:.1f} Hz |",
            "",
            f"Paired best-candidate comparison in the critical interval: median absolute "
            f"CFO change {paired['median_absolute_cfo_difference_hz']:.1f} Hz; "
            f"{paired['within_500_hz_probe_count']}/{paired['probe_count']} probes agree "
            "within 500 Hz. The remaining probes are ambiguity/basin changes, not a uniform "
            "frequency-resolution shift.",
            "",
            f"Runtime: {summary['runtime_s']:.1f} s. Candidate-only; no payload decoded.",
            "",
        ]
    )


def main() -> None:
    args = _arguments()
    if not (
        0 <= args.start_s < args.end_s
        and args.probe_ms > 0
        and args.probe_spacing_ms >= args.probe_ms
        and 1 <= args.candidate_count <= 64
        and 1 <= args.workers <= 16
        and args.glrt_size >= 512
        and args.glrt_size & (args.glrt_size - 1) == 0
    ):
        raise ValueError("time, probe, candidate, worker, or GLRT bounds are invalid")
    args.output_root.mkdir(parents=True, exist_ok=True)
    pinned = PinnedLocalRoot(args.bulk_root)
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(pinned)
        bundle = store.inspect(args.session_id)
        store.verify(bundle)
        reader = store.reader(bundle, args.stream, verify=True)
        if args.receiver not in reader.receiver_ids:
            raise ValueError("requested receiver is absent from the selected stream")
        sample_rate_hz = reader.sample_rate_hz
        probe_samples = round(args.probe_ms * sample_rate_hz / 1_000)
        spacing_samples = round(args.probe_spacing_ms * sample_rate_hz / 1_000)
        start_sample = math.ceil(args.start_s * sample_rate_hz / spacing_samples) * spacing_samples
        stop_sample = (
            math.floor((args.end_s * sample_rate_hz - probe_samples) / spacing_samples)
            * spacing_samples
        )
        starts = tuple(range(start_sample, stop_sample + 1, spacing_samples))
        calibration = ReceiverFrequencyCalibration(
            "dense-independent-baseband",
            0.0,
            canonical_digest(
                {
                    "session_id": args.session_id,
                    "stream": args.stream,
                    "receiver": args.receiver,
                    "frequency_reference": "uncalibrated-baseband",
                }
            ).removeprefix("sha256:"),
        )
        config = SymbolwiseAcquisitionConfig(
            residual_cfo_min_hz=-400_000.0,
            residual_cfo_max_hz=400_000.0,
            coarse_cfo_step_hz=args.coarse_cfo_step_hz,
            fine_cfo_radius_hz=args.fine_cfo_radius_hz,
            fine_cfo_step_hz=args.fine_cfo_step_hz,
            conditioned_cfo_radius_hz=args.conditioned_cfo_radius_hz,
            conditioned_cfo_step_hz=args.conditioned_cfo_step_hz,
            retained_candidate_count=args.candidate_count,
            candidate_epoch_separation_samples=args.candidate_epoch_separation_samples,
            candidate_cfo_separation_hz=args.candidate_cfo_separation_hz,
            maximum_probe_samples=probe_samples,
        )
        started = time.perf_counter()
        dense_rows: list[CandidateRow] = []
        by_second: dict[int, list[int]] = {}
        for sample_start in starts:
            by_second.setdefault(sample_start // sample_rate_hz, []).append(sample_start)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            for index, second in enumerate(sorted(by_second), start=1):
                second_starts = by_second[second]
                outer_start = min(second_starts)
                outer_stop = max(second_starts) + probe_samples
                outer = _complex_receiver(
                    reader.read(
                        outer_start,
                        outer_stop - outer_start,
                        receiver_ids=(args.receiver,),
                    )
                )
                requests = tuple(
                    (
                        sample_start,
                        np.ascontiguousarray(
                            outer[
                                sample_start - outer_start : sample_start
                                - outer_start
                                + probe_samples
                            ]
                        ),
                    )
                    for sample_start in second_starts
                )
                detected = executor.map(
                    lambda request: _detect_one(
                        request,
                        sample_rate_hz=sample_rate_hz,
                        calibration=calibration,
                        config=config,
                        edge=StarlinkEdge(args.edge),
                        candidate_count=args.candidate_count,
                        glrt_size=args.glrt_size,
                    ),
                    requests,
                )
                dense_rows.extend(item for rows in detected for item in rows)
                print(
                    f"completed second {second} ({index}/{len(by_second)}); "
                    f"candidates={len(dense_rows)}",
                    flush=True,
                )
        runtime_s = time.perf_counter() - started
    finally:
        if store is not None:
            store.close()
        pinned.close()

    dense = tuple(sorted(dense_rows, key=lambda item: (item.sample_start, item.rank)))
    candidate_path = args.output_root / "dense-independent-glrt-candidates.jsonl.gz"
    _write_candidates(candidate_path, dense)
    if args.candidate_output_only:
        run = _candidate_run_metadata(args, config, dense, runtime_s)
        run_path = args.output_root / "dense-independent-glrt-run.json"
        run_path.write_text(
            json.dumps(run, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(run_path)
        return

    baseline = _baseline_rows(args.baseline_pilot_scan, args.start_s, args.end_s)
    summary = _summarize(args, dense, baseline, runtime_s)
    summary.pop("dense_candidates")
    (args.output_root / "dense-independent-glrt-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _plot(
        args.output_root / "dense-independent-glrt-full.png",
        args,
        dense,
        baseline,
        start_s=args.start_s,
        end_s=args.end_s,
        title="Dense independent GLRT · full T1 interval",
    )
    _plot(
        args.output_root / "dense-independent-glrt-p1-zoom.png",
        args,
        dense,
        baseline,
        start_s=6.5,
        end_s=8.5,
        title="Dense independent GLRT · P1 endpoint zoom",
    )
    (args.output_root / "README.md").write_text(_markdown(summary), encoding="utf-8")
    print(args.output_root / "README.md")


if __name__ == "__main__":
    main()
