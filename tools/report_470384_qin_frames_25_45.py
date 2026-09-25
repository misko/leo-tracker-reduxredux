#!/usr/bin/env python3
"""Score and fit every branch-conditioned pilot frame in the 25--45 s dwell.

The persisted pilot scan exposes one 20 ms timing-lock window every 25 ms and
eight CFO/timing candidates per probe.  For every frozen dealiased trajectory
branch intersecting the requested interval, this tool selects the candidate
nearest that branch without applying a Qin-score threshold, then evaluates all
complete 1.333 ms known-pilot frames in the window.  A later, explicit fit gate
requires both trajectory proximity and direct exact-versus-rolled-control Qin
support.  The recording and analysis corpus are opened read-only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from leo.analysis.qam import analyze_pilot_phase_slope
from leo.analysis.starlink import StarlinkEdge
from leo.analysis.starlink.local_doppler import stable_measurement_floats
from leo.storage import PinnedLocalRoot, RecordingStore

try:
    import report_470384_sawtooth_methods as sawtooth
except ModuleNotFoundError:  # pragma: no cover - used when imported from the repo root
    from tools import report_470384_sawtooth_methods as sawtooth


SESSION_ID = "cap-20260821T140820-470384cc9284"
ANALYSIS_SCOPE = "sha256:ccdc4b152617f6e99b23044948cea7be040905cf1e7dd074bb36668b36dc0963"
DEFAULT_ANALYSIS_ROOT = Path(
    "/srv/bulk/leo/analysis/cap-20260821T140820-470384cc9284/"
    "capture-438ad263e01048ef82f660975ec55a08/scientific/path-standard/" + ANALYSIS_SCOPE
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_qin_frames_25_45")
DEFAULT_REPORT_PATH = Path("reports/2026_08_23_470384_qin_frames_25_45.md")
SAMPLE_RATE_HZ = 2_500_000.0
MINIMUM_EXACT_COHERENCE = 0.02
MINIMUM_COHERENCE_MARGIN = 0.0
MAXIMUM_FIT_MODEL_ERROR_HZ = 2_500.0
INK = "#17354a"
GRAY = "#98a4ad"
AMBER = "#d9881f"
BRANCH_COLORS = ("#2f83b7", "#3f8f67", "#7b65a8", "#bd5b52", "#4e91a8")


@dataclass(frozen=True, slots=True)
class Branch:
    index: int
    label: str
    branch_id: str
    model_id: str
    start_s: float
    end_s: float
    reference_time_s: float
    coefficients_hz: tuple[float, ...]

    def frequency_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        value = np.polyval(
            self.coefficients_hz,
            np.asarray(time_s, dtype=float) - self.reference_time_s,
        )
        return float(value) if np.ndim(value) == 0 else value


@dataclass(frozen=True, slots=True)
class CandidateWindow:
    association_index: int
    branch_index: int
    detection_time_s: float
    probe_sample_start: int
    aligned_sample_start: int
    candidate_rank: int
    local_epoch_sample: int
    initial_cfo_hz: float
    glrt_exact_score: float
    glrt_control_score: float
    glrt_margin: float
    selection_model_error_hz: float

    @property
    def analysis_key(self) -> tuple[int, int, float]:
        return (
            self.probe_sample_start,
            self.local_epoch_sample,
            self.initial_cfo_hz,
        )


@dataclass(frozen=True, slots=True)
class FrameRow:
    row_index: int
    association_index: int
    branch_index: int
    frame_index: int
    reference_time_s: float
    absolute_cfo_hz: float
    model_cfo_hz: float
    residual_cfo_hz: float
    residual_from_initial_hz: float
    frequency_uncertainty_hz: float
    exact_coherence: float
    control_coherence: float
    coherence_margin: float
    phase_residual_rms_rad: float
    model_proximate_window: bool
    direct_qin_match: bool
    fit_eligible: bool


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--analysis-root", type=Path, default=DEFAULT_ANALYSIS_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--start-s", type=float, default=25.0)
    parser.add_argument("--end-s", type=float, default=45.0)
    parser.add_argument(
        "--maximum-fit-model-error-hz",
        type=float,
        default=MAXIMUM_FIT_MODEL_ERROR_HZ,
    )
    parser.add_argument("--maximum-residual-cfo-hz", type=float, default=4_000.0)
    parser.add_argument(
        "--reuse-frame-results",
        type=Path,
        help="reuse frame/window rows from an earlier result and rerun only fits/plots",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def selected_branches(
    bank: dict[str, Any], *, start_s: float, end_s: float
) -> tuple[Branch, ...]:
    """Return selected cubic branch models intersecting the requested interval."""

    values: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for item in bank["branches"]:
        clipped_start = max(start_s, float(item["start_s"]))
        clipped_end = min(end_s, float(item["end_s"]))
        if clipped_start > clipped_end:
            continue
        matches = [
            model
            for model in item["models"]
            if model["model_id"] == item["selected_model_id"]
        ]
        if len(matches) != 1:
            raise ValueError(f"branch {item['branch_id']} does not have one selected model")
        values.append((clipped_start, item, matches[0]))
    values.sort(key=lambda entry: (entry[0], float(entry[1]["end_s"])))
    return tuple(
        Branch(
            index=index,
            label=f"B{index + 1} · {str(item['branch_id']).split(':')[-1][:8]}",
            branch_id=str(item["branch_id"]),
            model_id=str(model["model_id"]),
            start_s=max(start_s, float(item["start_s"])),
            end_s=min(end_s, float(item["end_s"])),
            reference_time_s=float(model["reference_time_s"]),
            coefficients_hz=tuple(float(value) for value in model["coefficients_hz"]),
        )
        for index, (_start, item, model) in enumerate(values)
    )


def _glrt_score(candidate: dict[str, Any]) -> dict[str, Any]:
    matches = [score for score in candidate["scores"] if score["method"] == "glrt64"]
    if len(matches) != 1:
        raise ValueError("candidate does not contain exactly one GLRT64 score")
    return matches[0]


def nearest_candidate_windows(
    scan: dict[str, Any], branches: tuple[Branch, ...]
) -> tuple[CandidateWindow, ...]:
    """Choose by branch-model distance only; do not prefilter on Qin score."""

    windows: list[CandidateWindow] = []
    for branch in branches:
        for detection in scan["detections"]:
            time_s = float(detection["time_s"])
            if not branch.start_s <= time_s <= branch.end_s:
                continue
            model_hz = float(branch.frequency_hz(time_s))
            candidates = []
            for candidate in detection["candidates"]:
                score = _glrt_score(candidate)
                error_hz = abs(float(score["tracking_cfo_hz"]) - model_hz)
                candidates.append((error_hz, int(candidate["rank"]), candidate, score))
            if not candidates:
                continue
            error_hz, _rank, candidate, score = min(
                candidates, key=lambda value: (value[0], value[1])
            )
            epoch = int(candidate["local_epoch_sample"])
            windows.append(
                CandidateWindow(
                    association_index=len(windows),
                    branch_index=branch.index,
                    detection_time_s=time_s,
                    probe_sample_start=int(detection["sample_start"]),
                    aligned_sample_start=int(detection["sample_start"]) + epoch,
                    candidate_rank=int(candidate["rank"]),
                    local_epoch_sample=epoch,
                    initial_cfo_hz=float(score["tracking_cfo_hz"]),
                    glrt_exact_score=float(score["exact_score"]),
                    glrt_control_score=float(score["control_score"]),
                    glrt_margin=float(score["margin"]),
                    selection_model_error_hz=error_hz,
                )
            )
    return tuple(windows)


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 data must have shape (samples, 1, 2)")
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / (
        2**15
    )


def analyze_windows(
    *,
    bulk_root: Path,
    scan: dict[str, Any],
    branches: tuple[Branch, ...],
    windows: tuple[CandidateWindow, ...],
    maximum_fit_model_error_hz: float,
    maximum_residual_cfo_hz: float,
) -> tuple[FrameRow, ...]:
    """Read each unique candidate once and expand it into branch-associated rows."""

    probe_samples = int(scan["probe_samples"])
    frame_cache: dict[tuple[int, int, float], tuple[Any, ...]] = {}
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
        bundle = store.inspect(SESSION_ID)
        reader = store.reader(bundle, "stream-0", verify=True)
        for position, window in enumerate(windows):
            key = window.analysis_key
            if key in frame_cache:
                continue
            if window.aligned_sample_start + probe_samples > reader.sample_count:
                raise ValueError(f"window at {window.detection_time_s:.3f} s exceeds recording")
            raw = reader.read(
                window.aligned_sample_start,
                probe_samples,
                receiver_ids=(0,),
            )
            iq = _complex_receiver(raw)
            result = analyze_pilot_phase_slope(
                iq,
                SAMPLE_RATE_HZ,
                epoch_sample=0,
                absolute_cfo_hz=window.initial_cfo_hz,
                edge=StarlinkEdge.UPPER,
                maximum_residual_cfo_hz=maximum_residual_cfo_hz,
            )
            if not result.frames:
                raise ValueError(
                    f"phase-slope analysis returned no frames at {window.detection_time_s:.3f} s"
                )
            frame_cache[key] = result.frames
            if len(frame_cache) % 100 == 0:
                print(
                    f"computed {len(frame_cache)} unique timing locks "
                    f"({position + 1}/{len(windows)} branch associations)",
                    flush=True,
                )
    finally:
        if store is not None:
            store.close()

    rows: list[FrameRow] = []
    for window in windows:
        branch = branches[window.branch_index]
        model_proximate = window.selection_model_error_hz <= maximum_fit_model_error_hz
        for frame in frame_cache[window.analysis_key]:
            time_s = (window.aligned_sample_start + float(frame.reference_sample)) / SAMPLE_RATE_HZ
            model_hz = float(branch.frequency_hz(time_s))
            direct_match = bool(
                frame.exact_coherence >= MINIMUM_EXACT_COHERENCE
                and frame.coherence_margin >= MINIMUM_COHERENCE_MARGIN
            )
            rows.append(
                FrameRow(
                    row_index=len(rows),
                    association_index=window.association_index,
                    branch_index=window.branch_index,
                    frame_index=int(frame.frame_index),
                    reference_time_s=time_s,
                    absolute_cfo_hz=float(frame.absolute_cfo_hz),
                    model_cfo_hz=model_hz,
                    residual_cfo_hz=float(frame.absolute_cfo_hz) - model_hz,
                    residual_from_initial_hz=float(frame.residual_cfo_hz),
                    frequency_uncertainty_hz=float(frame.frequency_uncertainty_hz),
                    exact_coherence=float(frame.exact_coherence),
                    control_coherence=float(frame.control_coherence),
                    coherence_margin=float(frame.coherence_margin),
                    phase_residual_rms_rad=float(frame.phase_residual_rms_rad),
                    model_proximate_window=model_proximate,
                    direct_qin_match=direct_match,
                    fit_eligible=bool(model_proximate and direct_match),
                )
            )
    return tuple(rows)


def _segment_dict(segment: Any) -> dict[str, Any]:
    return asdict(segment)


def fit_branch(
    branch: Branch, rows: tuple[FrameRow, ...]
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    eligible = tuple(row for row in rows if row.branch_index == branch.index and row.fit_eligible)
    observations = tuple(
        sawtooth.FrameObservation(
            row_index=row.row_index,
            time_s=row.reference_time_s,
            absolute_cfo_hz=row.absolute_cfo_hz,
            model_cfo_hz=row.model_cfo_hz,
            source_window_index=row.association_index,
            exact_coherence=row.exact_coherence,
            coherence_margin=row.coherence_margin,
            frequency_uncertainty_hz=row.frequency_uncertainty_hz,
            frequency_update_applied=False,
        )
        for row in eligible
    )
    lock_fits = sawtooth.independent_lock_fits(observations)
    if not lock_fits:
        return ({"status": "no-fit", "reason": "no timing lock has six eligible frames"}, ())
    robust_rms = np.asarray([fit.robust_rms_hz for fit in lock_fits], dtype=float)
    noise_scale_hz = max(5.0, float(np.percentile(robust_rms, 90)))
    segment_penalty = float(2.0 * math.log(max(2, len(observations))))
    partition = sawtooth.batch_joined_segments(
        observations,
        lock_fits,
        noise_scale_hz=noise_scale_hz,
        segment_penalty=segment_penalty,
    )
    coherent = tuple(segment for segment in partition if segment.coherent)
    result: dict[str, Any] = {
        "status": "complete",
        "eligible_frame_count": len(observations),
        "independent_lock_fit_count": len(lock_fits),
        "partition_segment_count": len(partition),
        "coherent_segment_count": len(coherent),
        "coherent_frame_count": sum(segment.frame_count for segment in coherent),
        "noise_scale_hz": noise_scale_hz,
        "segment_penalty": segment_penalty,
        "segments": [_segment_dict(segment) for segment in partition],
    }
    if len(coherent) >= 3:
        common = sawtooth.joint_varying_intercept_fit(
            observations, coherent, slope_progression=False
        )
        progression = sawtooth.joint_varying_intercept_fit(
            observations, coherent, slope_progression=True
        )
        result["joint_common_slope"] = asdict(common)
        result["joint_slope_progression"] = asdict(progression)
        result["progression_minus_common_bic"] = progression.bic - common.bic
        first_center_s = coherent[0].center_time_s
        last_center_s = coherent[-1].center_time_s
        center_span_s = last_center_s - first_center_s
        result["progression_over_coherent_span"] = {
            "first_center_time_s": first_center_s,
            "last_center_time_s": last_center_s,
            "span_s": center_span_s,
            "slope_change_hz_s": progression.slope_progression_hz_s2 * center_span_s,
            "slope_change_sigma_hz_s": (
                progression.slope_progression_sigma_hz_s2 * center_span_s
            ),
        }
        result["in_sample_model_error"] = sawtooth.in_sample_model_error_comparison(
            observations,
            coherent,
            common,
            progression,
        )
        result["leave_one_probe_out_model_error"] = (
            sawtooth.leave_one_probe_out_model_error_comparison(observations, coherent)
        )
    return result, coherent


def _margin_norm(rows: tuple[FrameRow, ...]) -> TwoSlopeNorm:
    margins = np.asarray([row.coherence_margin for row in rows], dtype=float)
    lower = min(-0.02, float(np.percentile(margins, 2)))
    upper = max(0.05, float(np.percentile(margins, 98)))
    return TwoSlopeNorm(vmin=lower, vcenter=0.0, vmax=upper)


def _save_figure(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def render_overview(
    path: Path,
    *,
    branches: tuple[Branch, ...],
    windows: tuple[CandidateWindow, ...],
    rows: tuple[FrameRow, ...],
    start_s: float,
    end_s: float,
) -> None:
    norm = _margin_norm(rows)
    figure, axes = plt.subplots(
        2,
        1,
        figsize=(16, 9),
        sharex=True,
        gridspec_kw={"height_ratios": (3.2, 1.25)},
        constrained_layout=True,
    )
    figure.suptitle(
        "All 1.333 ms branch-conditioned frame CFOs, colored by direct Qin evidence",
        color=INK,
        fontsize=18,
        fontweight="bold",
    )
    time = np.asarray([row.reference_time_s for row in rows])
    cfo_khz = np.asarray([row.absolute_cfo_hz for row in rows]) / 1_000
    margin = np.asarray([row.coherence_margin for row in rows])
    scatter = axes[0].scatter(
        time,
        cfo_khz,
        c=margin,
        norm=norm,
        cmap="coolwarm",
        s=4,
        alpha=0.55,
        linewidths=0,
        rasterized=True,
    )
    for branch, color in zip(branches, BRANCH_COLORS[: len(branches)], strict=True):
        x = np.linspace(branch.start_s, branch.end_s, 400)
        axes[0].plot(
            x,
            np.asarray(branch.frequency_hz(x)) / 1_000,
            color=color,
            linewidth=1.8,
            label=branch.label,
        )
    axes[0].set_ylabel("absolute CFO (kHz)")
    axes[0].set_title(
        "A · Every nearest lock candidate; no Qin threshold was applied before frame scoring",
        loc="left",
        color=INK,
    )
    axes[0].grid(alpha=0.18)
    axes[0].legend(ncol=3, loc="lower left", fontsize=9)
    colorbar = figure.colorbar(scatter, ax=axes, pad=0.012, shrink=0.88)
    colorbar.set_label("Qin margin = exact coherence − 17-symbol-roll control")

    by_window: dict[int, list[FrameRow]] = {}
    for row in rows:
        by_window.setdefault(row.association_index, []).append(row)
    for branch, color in zip(branches, BRANCH_COLORS[: len(branches)], strict=True):
        branch_windows = [window for window in windows if window.branch_index == branch.index]
        fractions = [
            np.mean([row.direct_qin_match for row in by_window[window.association_index]])
            for window in branch_windows
        ]
        axes[1].scatter(
            [window.detection_time_s for window in branch_windows],
            fractions,
            color=color,
            s=8,
            alpha=0.7,
            linewidths=0,
            label=branch.label,
        )
    axes[1].set_title(
        "B · Fraction passing exact ≥ 0.02 and beating the rolled-Qin control",
        loc="left",
        color=INK,
    )
    axes[1].set_ylabel("direct Qin-match fraction")
    axes[1].set_xlabel("capture time (s)")
    axes[1].set_ylim(-0.04, 1.04)
    axes[1].set_xlim(start_s, end_s)
    axes[1].grid(alpha=0.18)
    _save_figure(figure, path)


def render_raster(
    path: Path,
    *,
    branches: tuple[Branch, ...],
    windows: tuple[CandidateWindow, ...],
    rows: tuple[FrameRow, ...],
    start_s: float,
    end_s: float,
) -> None:
    norm = _margin_norm(rows)
    figure, axes = plt.subplots(
        len(branches),
        1,
        figsize=(16, 12),
        sharex=True,
        constrained_layout=True,
    )
    figure.suptitle(
        "Frame-by-frame Qin match: every 25 ms probe and every complete pilot frame",
        color=INK,
        fontsize=18,
        fontweight="bold",
    )
    axes = np.atleast_1d(axes)
    row_map = {(row.association_index, row.frame_index): row for row in rows}
    image = None
    for axis, branch in zip(axes, branches, strict=True):
        branch_windows = [window for window in windows if window.branch_index == branch.index]
        maximum_frame = max(
            row.frame_index for row in rows if row.branch_index == branch.index
        )
        matrix = np.full((maximum_frame + 1, len(branch_windows)), np.nan)
        for column, window in enumerate(branch_windows):
            for frame_index in range(maximum_frame + 1):
                row = row_map.get((window.association_index, frame_index))
                if row is not None:
                    matrix[frame_index, column] = row.coherence_margin
        image = axis.imshow(
            matrix,
            origin="lower",
            aspect="auto",
            interpolation="nearest",
            extent=(branch.start_s, branch.end_s, -0.5, maximum_frame + 0.5),
            cmap="coolwarm",
            norm=norm,
        )
        axis.set_ylabel("frame index")
        axis.set_title(
            f"{branch.label} · valid {branch.start_s:.3f}–{branch.end_s:.3f} s",
            loc="left",
            color=INK,
        )
        axis.set_yticks((0, 5, 10, maximum_frame))
    axes[-1].set_xlabel("capture time (s)")
    axes[-1].set_xlim(start_s, end_s)
    if image is not None:
        colorbar = figure.colorbar(image, ax=axes, pad=0.012, shrink=0.88)
        colorbar.set_label("exact Qin coherence − rolled-control coherence")
    _save_figure(figure, path)


def render_fits(
    path: Path,
    *,
    branches: tuple[Branch, ...],
    rows: tuple[FrameRow, ...],
    coherent_by_branch: dict[int, tuple[Any, ...]],
    start_s: float,
    end_s: float,
) -> None:
    norm = _margin_norm(rows)
    figure, axes = plt.subplots(
        len(branches),
        1,
        figsize=(16, 12),
        sharex=True,
        constrained_layout=True,
    )
    figure.suptitle(
        "Offline batch fits on direct-Qin, model-proximate frames",
        color=INK,
        fontsize=18,
        fontweight="bold",
    )
    axes = np.atleast_1d(axes)
    scatter = None
    for axis, branch in zip(axes, branches, strict=True):
        branch_rows = tuple(
            row
            for row in rows
            if row.branch_index == branch.index and row.model_proximate_window
        )
        scatter = axis.scatter(
            [row.reference_time_s for row in branch_rows],
            [row.residual_cfo_hz for row in branch_rows],
            c=[row.coherence_margin for row in branch_rows],
            cmap="coolwarm",
            norm=norm,
            s=5,
            alpha=0.55,
            linewidths=0,
            rasterized=True,
        )
        for segment in coherent_by_branch.get(branch.index, ()):
            x = np.linspace(segment.start_time_s, segment.end_time_s, 20)
            residual = np.asarray(segment.frequency_hz(x)) - np.asarray(branch.frequency_hz(x))
            axis.plot(x, residual, color=AMBER, linewidth=2.0)
        axis.axhline(0, color=INK, linewidth=0.8, alpha=0.7)
        axis.set_ylabel("CFO − branch (Hz)")
        axis.set_title(
            f"{branch.label} · {len(coherent_by_branch.get(branch.index, ()))} coherent ramps",
            loc="left",
            color=INK,
        )
        axis.grid(alpha=0.16)
    axes[-1].set_xlabel("capture time (s)")
    axes[-1].set_xlim(start_s, end_s)
    handles = [
        Line2D([0], [0], color=AMBER, linewidth=2, label="batch-joined coherent ramp"),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=GRAY,
            label="all model-proximate frames",
        ),
    ]
    axes[0].legend(handles=handles, loc="lower left", fontsize=9)
    if scatter is not None:
        colorbar = figure.colorbar(scatter, ax=axes, pad=0.012, shrink=0.88)
        colorbar.set_label("exact Qin coherence − rolled-control coherence")
    _save_figure(figure, path)


def _branch_summary(
    branch: Branch,
    windows: tuple[CandidateWindow, ...],
    rows: tuple[FrameRow, ...],
    fit: dict[str, Any],
    maximum_fit_model_error_hz: float,
) -> dict[str, Any]:
    branch_windows = tuple(window for window in windows if window.branch_index == branch.index)
    branch_rows = tuple(row for row in rows if row.branch_index == branch.index)
    proximate = tuple(
        window
        for window in branch_windows
        if window.selection_model_error_hz <= maximum_fit_model_error_hz
    )
    direct = tuple(row for row in branch_rows if row.direct_qin_match)
    return {
        "branch": asdict(branch),
        "candidate_window_count": len(branch_windows),
        "model_proximate_window_count": len(proximate),
        "frame_count": len(branch_rows),
        "strong_direct_qin_gate_frame_count": len(direct),
        "strong_direct_qin_gate_fraction": len(direct) / len(branch_rows),
        "fit_eligible_frame_count": sum(row.fit_eligible for row in branch_rows),
        "median_frame_exact_coherence": float(
            np.median([row.exact_coherence for row in branch_rows])
        ),
        "median_frame_control_coherence": float(
            np.median([row.control_coherence for row in branch_rows])
        ),
        "median_frame_coherence_margin": float(
            np.median([row.coherence_margin for row in branch_rows])
        ),
        "fit": fit,
    }


def shared_candidate_windows(
    branches: tuple[Branch, ...], windows: tuple[CandidateWindow, ...]
) -> tuple[dict[str, Any], ...]:
    """Count branch associations that reuse the exact same candidate lock."""

    keys_by_branch = {
        branch.index: {
            window.analysis_key for window in windows if window.branch_index == branch.index
        }
        for branch in branches
    }
    overlaps = []
    for left_index, left in enumerate(branches):
        for right in branches[left_index + 1 :]:
            count = len(keys_by_branch[left.index] & keys_by_branch[right.index])
            if count:
                overlaps.append(
                    {
                        "left_branch_index": left.index,
                        "left_label": left.label,
                        "right_branch_index": right.index,
                        "right_label": right.label,
                        "shared_candidate_window_count": count,
                    }
                )
    return tuple(overlaps)


def write_report(path: Path, results: dict[str, Any]) -> None:
    summaries = results["branches"]
    rows = []
    fit_notes = []
    for summary in summaries:
        branch = summary["branch"]
        fit = summary["fit"]
        common = fit.get("joint_common_slope", {})
        progression = fit.get("joint_slope_progression", {})
        rows.append(
            "| {label} | {start:.3f}–{end:.3f} | {windows} / {proximate} | "
            "{frames} | {direct:.1f}% | {ramps} | {slope} | {progression} | {bic} |".format(
                label=branch["label"],
                start=branch["start_s"],
                end=branch["end_s"],
                windows=summary["candidate_window_count"],
                proximate=summary["model_proximate_window_count"],
                frames=summary["frame_count"],
                direct=100 * summary["strong_direct_qin_gate_fraction"],
                ramps=fit.get("coherent_segment_count", 0),
                slope=(
                    f"{common['shared_slope_hz_s'] / 1_000:.3f}"
                    if common
                    else "—"
                ),
                progression=(
                    f"{progression['slope_progression_hz_s2']:+.1f}"
                    if progression
                    else "—"
                ),
                bic=(
                    f"{fit['progression_minus_common_bic']:+.1f}"
                    if "progression_minus_common_bic" in fit
                    else "—"
                ),
            )
        )
        if common and progression:
            span = fit["progression_over_coherent_span"]
            holdout = fit["leave_one_probe_out_model_error"]
            holdout_common = holdout["overall"]["joint_common_slope"]["rms_hz"]
            holdout_progression = holdout["overall"]["joint_slope_progression"]["rms_hz"]
            comparison = holdout["progression_minus_common"]
            fit_notes.append(
                "- **{label}:** progression {accel:+.2f} ± {accel_sigma:.2f} Hz/s²; "
                "the fitted rate changes by {change:+.1f} ± {change_sigma:.1f} Hz/s "
                "over {span:.3f} s. Leave-one-probe-out RMS changes from "
                "{common:.3f} to {progression:.3f} Hz ({relative:+.2f}%).".format(
                    label=branch["label"],
                    accel=progression["slope_progression_hz_s2"],
                    accel_sigma=progression["slope_progression_sigma_hz_s2"],
                    change=span["slope_change_hz_s"],
                    change_sigma=span["slope_change_sigma_hz_s"],
                    span=span["span_s"],
                    common=holdout_common,
                    progression=holdout_progression,
                    relative=comparison["overall_rms_relative_percent"],
                )
            )
    inventory = results["inventory"]
    overview_figure = os.path.relpath(results["figures"]["overview"], path.parent)
    raster_figure = os.path.relpath(results["figures"]["raster"], path.parent)
    fits_figure = os.path.relpath(results["figures"]["fits"], path.parent)
    overlap_notes = "\n".join(
        "- {left} and {right}: {count} shared candidate windows.".format(
            left=item["left_label"],
            right=item["right_label"],
            count=item["shared_candidate_window_count"],
        )
        for item in results["shared_candidate_windows"]
    )
    text = f"""# Qin frame evidence and offline fits, 25–45 s

## Result

This pass computes every complete 1.333 ms frame exposed by the nearest
persisted timing-lock candidate for each frozen GLRT branch intersecting
25–45 s.  The computation is deliberately **not** gated by Qin score.  Frames
are colored by the direct discriminant
`exact Qin coherence − 17-symbol-rolled control coherence`.

There are {inventory['branch_candidate_window_count']} branch/window associations,
{inventory['unique_candidate_window_count']} unique IQ windows, and
{inventory['branch_frame_count']} branch-associated frame rows
({inventory['unique_computed_frame_count']} distinct computed frames).  The
branches overlap, so the association count is intentionally larger than the
number of distinct IQ windows.

![All frame CFOs colored by Qin evidence]({overview_figure})

![Frame-level Qin evidence raster]({raster_figure})

## Fit gate and result by frozen branch

The offline sawtooth fit uses a frame only when its parent lock is within
{results['configuration']['maximum_fit_model_error_hz']:.0f} Hz of that frozen
branch, exact coherence is at least {MINIMUM_EXACT_COHERENCE:.2f}, and the exact
sequence beats the rolled control.  This fit gate is separate from frame
computation and visualization.

![Batch-joined coherent ramps]({fits_figure})

| branch | span | locks | frames | strong gate | ramps | rate | acceleration | ΔBIC |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

The table's rate is kHz/s, acceleration is Hz/s², and `ΔBIC` is
progression-minus-common.  The same fitted progression also survives complete
probe holdout, although the predictive improvement is modest:

{chr(10).join(fit_notes)}

Positive ΔBIC means the extra linear slope-progression term is disfavored.  The
five rows must not be combined into one Doppler history: the frozen branches
overlap in time and are not statistically independent.  In particular, exact
candidate reuse is:

{overlap_notes}

Within a row, each recovered ramp has its own arbitrary CFO intercept, so the
fit is not assuming a known LNB offset or assigned Starlink carrier frequency.

## What “all frames” means here

The persisted scan does not provide one verified carrier/timing lattice for all
20 seconds.  It provides 20 ms windows on a 25 ms probe schedule, with eight
candidate locks per probe.  For each frozen branch, this report takes the
nearest candidate by CFO-model distance and evaluates all 15 complete frames in
that candidate window.  It does not claim that the uncovered 5 ms between
probes, or the seven unselected candidates in each probe, belong to that branch.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    if not arguments.start_s < arguments.end_s:
        raise ValueError("start time must precede end time")
    scan = _load_json(arguments.analysis_root / "standard.pilot-scan.v3.json")
    bank = _load_json(arguments.analysis_root / "standard.dealiased-trajectory-bank.v3.json")
    if arguments.reuse_frame_results is not None:
        reused = _load_json(arguments.reuse_frame_results)
        reused_input = reused["input"]
        if (
            reused_input["session_id"] != SESSION_ID
            or float(reused_input["start_s"]) != arguments.start_s
            or float(reused_input["end_s"]) != arguments.end_s
        ):
            raise ValueError("reused frame evidence has a different capture interval")
        branches = tuple(
            Branch(
                **{
                    **summary["branch"],
                    "coefficients_hz": tuple(summary["branch"]["coefficients_hz"]),
                }
            )
            for summary in reused["branches"]
        )
        windows = tuple(CandidateWindow(**item) for item in reused["candidate_windows"])
        frames = tuple(FrameRow(**item) for item in reused["frames"])
    else:
        branches = selected_branches(bank, start_s=arguments.start_s, end_s=arguments.end_s)
        windows = nearest_candidate_windows(scan, branches)
        frames = analyze_windows(
            bulk_root=arguments.bulk_root,
            scan=scan,
            branches=branches,
            windows=windows,
            maximum_fit_model_error_hz=arguments.maximum_fit_model_error_hz,
            maximum_residual_cfo_hz=arguments.maximum_residual_cfo_hz,
        )

    fits: dict[int, dict[str, Any]] = {}
    coherent_by_branch: dict[int, tuple[Any, ...]] = {}
    for branch in branches:
        fit, coherent = fit_branch(branch, frames)
        fits[branch.index] = fit
        coherent_by_branch[branch.index] = coherent

    arguments.output_root.mkdir(parents=True, exist_ok=True)
    overview_path = arguments.output_root / "all-frame-qin-match-25-45.png"
    raster_path = arguments.output_root / "qin-frame-raster-25-45.png"
    fits_path = arguments.output_root / "qin-supported-batch-fits-25-45.png"
    render_overview(
        overview_path,
        branches=branches,
        windows=windows,
        rows=frames,
        start_s=arguments.start_s,
        end_s=arguments.end_s,
    )
    render_raster(
        raster_path,
        branches=branches,
        windows=windows,
        rows=frames,
        start_s=arguments.start_s,
        end_s=arguments.end_s,
    )
    render_fits(
        fits_path,
        branches=branches,
        rows=frames,
        coherent_by_branch=coherent_by_branch,
        start_s=arguments.start_s,
        end_s=arguments.end_s,
    )

    unique_keys = {window.analysis_key for window in windows}
    frames_per_key: dict[tuple[int, int, float], int] = {}
    for window in windows:
        frames_per_key.setdefault(
            window.analysis_key,
            sum(
                row.association_index == window.association_index
                for row in frames
            ),
        )
    results = stable_measurement_floats(
        {
            "schema_version": 1,
            "algorithm": "470384-qin-frames-25-45-v1",
            "input": {
                "session_id": SESSION_ID,
                "analysis_scope": ANALYSIS_SCOPE,
                "stream_id": "stream-0",
                "receiver_id": 0,
                "edge": "upper",
                "start_s": arguments.start_s,
                "end_s": arguments.end_s,
                "pilot_scan": str(arguments.analysis_root / "standard.pilot-scan.v3.json"),
                "trajectory_bank": str(
                    arguments.analysis_root / "standard.dealiased-trajectory-bank.v3.json"
                ),
            },
            "configuration": {
                "candidate_selection": (
                    "nearest GLRT64 CFO to selected frozen branch model; "
                    "no Qin threshold"
                ),
                "probe_samples": int(scan["probe_samples"]),
                "sample_rate_hz": SAMPLE_RATE_HZ,
                "minimum_exact_coherence": MINIMUM_EXACT_COHERENCE,
                "minimum_coherence_margin": MINIMUM_COHERENCE_MARGIN,
                "maximum_fit_model_error_hz": arguments.maximum_fit_model_error_hz,
                "maximum_residual_cfo_hz": arguments.maximum_residual_cfo_hz,
            },
            "inventory": {
                "branch_count": len(branches),
                "branch_candidate_window_count": len(windows),
                "unique_candidate_window_count": len(unique_keys),
                "branch_frame_count": len(frames),
                "unique_computed_frame_count": sum(frames_per_key.values()),
                "strong_direct_qin_gate_frame_count": sum(
                    row.direct_qin_match for row in frames
                ),
                "fit_eligible_frame_count": sum(row.fit_eligible for row in frames),
            },
            "branches": [
                _branch_summary(
                    branch,
                    windows,
                    frames,
                    fits[branch.index],
                    arguments.maximum_fit_model_error_hz,
                )
                for branch in branches
            ],
            "shared_candidate_windows": shared_candidate_windows(branches, windows),
            "candidate_windows": [asdict(window) for window in windows],
            "frames": [asdict(row) for row in frames],
            "figures": {
                "overview": str(overview_path),
                "raster": str(raster_path),
                "fits": str(fits_path),
            },
        }
    )
    results_path = arguments.output_root / "qin-frame-results.json"
    results_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(arguments.report_path, results)
    print(json.dumps(results["inventory"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
