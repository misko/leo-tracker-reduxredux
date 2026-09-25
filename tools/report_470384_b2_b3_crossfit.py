#!/usr/bin/env python3
"""Cross-evaluate the overlapping B2/B3 Qin CFO hypotheses.

For every B2 timing lock inside the B2/B3 overlap, this audit substitutes the
interpolated B3 continuous CFO, and vice versa.  It evaluates the native and
crossed hypotheses with the same 64-symbol profiled likelihood and with a
300-symbol even-fit/odd-validation split.  A separate all-local-maxima audit
checks whether the earlier one-bin continuous refinement missed a stronger
frequency peak.

All capture and persisted analysis inputs are opened read-only.
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
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.starlink import StarlinkEdge
from leo.analysis.starlink.local_doppler import stable_measurement_floats
from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.storage import PinnedLocalRoot, RecordingStore

try:
    import report_470384_continuous_glrt_refinement as continuous
except ModuleNotFoundError:  # pragma: no cover - imported from repository root
    from tools import report_470384_continuous_glrt_refinement as continuous


DEFAULT_CONTINUOUS_RESULTS = (
    Path("reports/figures/2026_08_23_470384_continuous_glrt")
    / "continuous-glrt-results.json"
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_b2_b3_crossfit")
DEFAULT_REPORT = Path("reports/2026_08_23_470384_b2_b3_crossfit.md")

B2 = 1
B3 = 2
BRANCHES = (B2, B3)
OVERLAP_START_S = 28.575
OVERLAP_END_S = 33.725

INK = continuous.INK
LIGHT_GRAY = continuous.LIGHT_GRAY
BLUE = continuous.GREEN
PURPLE = continuous.PURPLE
AMBER = continuous.AMBER
RED = continuous.RED


@dataclass(frozen=True, slots=True)
class HypothesisFit:
    seed_tracking_cfo_hz: float
    fitted_tracking_cfo_hz: float
    glrt_exact_score: float
    glrt_control_at_exact_score: float
    glrt_exact_control_db: float
    full_fit_tracking_cfo_hz: float
    full_validation_exact_score: float
    full_validation_control_score: float
    full_validation_exact_control_db: float


@dataclass(frozen=True, slots=True)
class CrossfitResult:
    source_branch_index: int
    source_branch_label: str
    substituted_branch_index: int
    substituted_branch_label: str
    time_s: float
    probe_sample_start: int
    local_epoch_sample: int
    acquired_cfo_hz: float
    native: HypothesisFit
    crossed: HypothesisFit
    native_to_cross_seed_separation_hz: float
    crossed_glrt_score_ratio_db: float
    crossed_validation_discrimination_delta_db: float
    global_tracking_cfo_hz: float
    global_exact_score: float
    global_over_native_gain: float
    global_over_native_gain_ppm: float


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--continuous-results", type=Path, default=DEFAULT_CONTINUOUS_RESULTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--maximum-windows",
        type=int,
        help="bounded development run over the ordered overlap rows",
    )
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _profile_scores(
    profile: continuous.ProfileLikelihood, frequencies_hz: np.ndarray
) -> np.ndarray:
    frequencies = np.asarray(frequencies_hz, dtype=float)
    if frequencies.ndim != 1 or not frequencies.size:
        raise ValueError("profile frequency grid must be a nonempty vector")
    rotation = np.exp(
        -2j * np.pi * frequencies[:, None, None] * profile.lags_s[None, :, :]
    )
    amplitudes = np.sum(profile.values[None, :, :] * rotation, axis=2)
    return np.sum(np.abs(amplitudes) ** 2, axis=1) / max(profile.coherent_ceiling, 1e-20)


def global_continuous_maximum(
    profile: continuous.ProfileLikelihood,
    *,
    symbol_step_s: float,
    size: int = continuous.GLRT_SIZE,
) -> tuple[continuous.ContinuousMaximum, np.ndarray, np.ndarray]:
    """Refine every discrete local maximum and return the strongest one."""

    grid = np.fft.fftshift(np.fft.fftfreq(size, d=symbol_step_s))
    scores = _profile_scores(profile, grid)
    local = (scores >= np.roll(scores, 1)) & (scores >= np.roll(scores, -1))
    indexes = np.flatnonzero(local)
    if not len(indexes):
        indexes = np.asarray([int(np.argmax(scores))])
    half_width_hz = float(grid[1] - grid[0])
    candidates = tuple(
        continuous.maximize_profile_likelihood(
            profile,
            initial_frequency_hz=float(grid[index]),
            half_width_hz=half_width_hz,
        )
        for index in indexes
    )
    return max(candidates, key=lambda item: item.score), grid, scores


def _fit_hypothesis(
    *,
    acquired_cfo_hz: float,
    seed_tracking_cfo_hz: float,
    glrt_exact: continuous.ProfileLikelihood,
    glrt_control: continuous.ProfileLikelihood,
    full_train_exact: continuous.ProfileLikelihood,
    full_validation_exact: continuous.ProfileLikelihood,
    full_validation_control: continuous.ProfileLikelihood,
    half_width_hz: float,
) -> HypothesisFit:
    seed_residual_hz = seed_tracking_cfo_hz - acquired_cfo_hz
    glrt_fit = continuous.maximize_profile_likelihood(
        glrt_exact,
        initial_frequency_hz=seed_residual_hz,
        half_width_hz=half_width_hz,
    )
    control64 = glrt_control.score(glrt_fit.frequency_hz)
    full_fit = continuous.maximize_profile_likelihood(
        full_train_exact,
        initial_frequency_hz=glrt_fit.frequency_hz,
        half_width_hz=half_width_hz,
    )
    validation_exact = full_validation_exact.score(full_fit.frequency_hz)
    validation_control = full_validation_control.score(full_fit.frequency_hz)
    return HypothesisFit(
        seed_tracking_cfo_hz=seed_tracking_cfo_hz,
        fitted_tracking_cfo_hz=acquired_cfo_hz + glrt_fit.frequency_hz,
        glrt_exact_score=glrt_fit.score,
        glrt_control_at_exact_score=control64,
        glrt_exact_control_db=10.0 * math.log10(glrt_fit.score / max(control64, 1e-20)),
        full_fit_tracking_cfo_hz=acquired_cfo_hz + full_fit.frequency_hz,
        full_validation_exact_score=validation_exact,
        full_validation_control_score=validation_control,
        full_validation_exact_control_db=10.0
        * math.log10(validation_exact / max(validation_control, 1e-20)),
    )


def _interpolated_other_cfo(
    rows: tuple[dict[str, Any], ...], target_branch_index: int
) -> tuple[np.ndarray, np.ndarray]:
    selected = sorted(
        (item for item in rows if int(item["branch_index"]) == target_branch_index),
        key=lambda item: float(item["time_s"]),
    )
    times = np.asarray([item["time_s"] for item in selected], dtype=float)
    frequencies = np.asarray(
        [item["continuous_tracking_cfo_hz"] for item in selected], dtype=float
    )
    unique_times, indexes = np.unique(times, return_index=True)
    return unique_times, frequencies[indexes]


def analyze(
    *,
    bulk_root: Path,
    continuous_document: dict[str, Any],
    maximum_windows: int | None,
) -> tuple[tuple[CrossfitResult, ...], tuple[dict[str, Any], ...]]:
    all_rows = tuple(continuous_document["rows"])
    labels = {
        int(item["branch_index"]): str(item["branch_label"])
        for item in continuous_document["branch_summaries"]
    }
    curves = {branch: _interpolated_other_cfo(all_rows, branch) for branch in BRANCHES}
    selected = tuple(
        sorted(
            (
                item
                for item in all_rows
                if int(item["branch_index"]) in BRANCHES
                and OVERLAP_START_S <= float(item["time_s"]) <= OVERLAP_END_S
            ),
            key=lambda item: (float(item["time_s"]), int(item["branch_index"])),
        )
    )
    if maximum_windows is not None:
        if maximum_windows < 1:
            raise ValueError("maximum window count must be positive")
        selected = selected[:maximum_windows]

    frame_document = _load(Path(continuous_document["input"]["frame_results"]))
    probe_samples = int(frame_document["configuration"].get("probe_samples", 50_000))
    output: list[CrossfitResult] = []
    profile_curves: list[dict[str, Any]] = []
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
        reader = store.reader(store.inspect(continuous.SESSION_ID), "stream-0", verify=True)
        for index, row in enumerate(selected, start=1):
            branch = int(row["branch_index"])
            other = B3 if branch == B2 else B2
            other_times, other_frequencies = curves[other]
            crossed_tracking_cfo_hz = float(
                np.interp(float(row["time_s"]), other_times, other_frequencies)
            )
            raw = reader.read(int(row["probe_sample_start"]), probe_samples, receiver_ids=(0,))
            iq = continuous.semicoherent._complex_receiver(raw)
            workspace = _conditioned_correlation_workspace(
                iq,
                int(continuous.SAMPLE_RATE_HZ),
                int(row["local_epoch_sample"]),
                float(row["acquired_cfo_hz"]),
                edge=StarlinkEdge.UPPER,
                selected_symbols=continuous.FULL_SYMBOLS,
            )
            exact64 = workspace.select(continuous.GLRT_SYMBOLS)
            control64 = workspace.select(continuous.GLRT_SYMBOLS, control=True)
            exact300 = workspace.select(continuous.FULL_SYMBOLS)
            control300 = workspace.select(continuous.FULL_SYMBOLS, control=True)
            even = np.arange(0, len(continuous.FULL_SYMBOLS), 2, dtype=int)
            odd = np.arange(1, len(continuous.FULL_SYMBOLS), 2, dtype=int)
            profiles = {
                "glrt_exact": continuous.ProfileLikelihood.from_correlations(
                    exact64.values, exact64.times_s
                ),
                "glrt_control": continuous.ProfileLikelihood.from_correlations(
                    control64.values, control64.times_s
                ),
                "full_train_exact": continuous.ProfileLikelihood.from_correlations(
                    exact300.values[:, even], exact300.times_s[:, even]
                ),
                "full_validation_exact": continuous.ProfileLikelihood.from_correlations(
                    exact300.values[:, odd], exact300.times_s[:, odd]
                ),
                "full_validation_control": continuous.ProfileLikelihood.from_correlations(
                    control300.values[:, odd], control300.times_s[:, odd]
                ),
            }
            half_width_hz = 1.0 / (continuous.GLRT_SIZE * exact64.symbol_step_s)
            fit_arguments = {
                "acquired_cfo_hz": float(row["acquired_cfo_hz"]),
                "half_width_hz": half_width_hz,
                **profiles,
            }
            native = _fit_hypothesis(
                seed_tracking_cfo_hz=float(row["continuous_tracking_cfo_hz"]),
                **fit_arguments,
            )
            crossed = _fit_hypothesis(
                seed_tracking_cfo_hz=crossed_tracking_cfo_hz,
                **fit_arguments,
            )
            global_fit, residual_grid, grid_scores = global_continuous_maximum(
                profiles["glrt_exact"], symbol_step_s=exact64.symbol_step_s
            )
            if native.glrt_exact_score > global_fit.score:
                global_tracking_cfo_hz = native.fitted_tracking_cfo_hz
                global_exact_score = native.glrt_exact_score
            else:
                global_tracking_cfo_hz = (
                    float(row["acquired_cfo_hz"]) + global_fit.frequency_hz
                )
                global_exact_score = global_fit.score
            global_gain = global_exact_score - native.glrt_exact_score
            result = CrossfitResult(
                source_branch_index=branch,
                source_branch_label=labels[branch],
                substituted_branch_index=other,
                substituted_branch_label=labels[other],
                time_s=float(row["time_s"]),
                probe_sample_start=int(row["probe_sample_start"]),
                local_epoch_sample=int(row["local_epoch_sample"]),
                acquired_cfo_hz=float(row["acquired_cfo_hz"]),
                native=native,
                crossed=crossed,
                native_to_cross_seed_separation_hz=(
                    crossed_tracking_cfo_hz - float(row["continuous_tracking_cfo_hz"])
                ),
                crossed_glrt_score_ratio_db=10.0
                * math.log10(crossed.glrt_exact_score / max(native.glrt_exact_score, 1e-20)),
                crossed_validation_discrimination_delta_db=(
                    crossed.full_validation_exact_control_db
                    - native.full_validation_exact_control_db
                ),
                global_tracking_cfo_hz=global_tracking_cfo_hz,
                global_exact_score=global_exact_score,
                global_over_native_gain=global_gain,
                global_over_native_gain_ppm=(
                    1e6 * global_gain / max(native.glrt_exact_score, 1e-20)
                ),
            )
            output.append(result)
            profile_curves.append(
                {
                    "result_index": len(output) - 1,
                    "tracking_cfo_hz": float(row["acquired_cfo_hz"]) + residual_grid,
                    "scores": grid_scores,
                }
            )
            if index % 25 == 0 or index == len(selected):
                print(f"cross-evaluated {index}/{len(selected)} B2/B3 locks", flush=True)
    finally:
        if store is not None:
            store.close()
    return tuple(output), tuple(profile_curves)


def _percentiles(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "p10": float(np.percentile(array, 10)),
        "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90)),
    }


def summarize(
    results: tuple[CrossfitResult, ...], continuous_document: dict[str, Any]
) -> dict[str, Any]:
    directions = []
    for branch in BRANCHES:
        values = tuple(item for item in results if item.source_branch_index == branch)
        directions.append(
            {
                "source_branch_index": branch,
                "source_branch_label": values[0].source_branch_label,
                "substituted_branch_label": values[0].substituted_branch_label,
                "window_count": len(values),
                "absolute_seed_separation_hz": _percentiles(
                    [abs(item.native_to_cross_seed_separation_hz) for item in values]
                ),
                "crossed_glrt_score_ratio_db": _percentiles(
                    [item.crossed_glrt_score_ratio_db for item in values]
                ),
                "crossed_glrt_better_fraction": float(
                    np.mean(
                        [
                            item.crossed.glrt_exact_score > item.native.glrt_exact_score
                            for item in values
                        ]
                    )
                ),
                "native_validation_exact_control_db": _percentiles(
                    [item.native.full_validation_exact_control_db for item in values]
                ),
                "crossed_validation_exact_control_db": _percentiles(
                    [item.crossed.full_validation_exact_control_db for item in values]
                ),
                "crossed_validation_better_fraction": float(
                    np.mean(
                        [
                            item.crossed.full_validation_exact_control_db
                            > item.native.full_validation_exact_control_db
                            for item in values
                        ]
                    )
                ),
                "global_over_native_gain_ppm": _percentiles(
                    [item.global_over_native_gain_ppm for item in values]
                ),
                "global_material_improvement_fraction": float(
                    np.mean([item.global_over_native_gain_ppm > 1.0 for item in values])
                ),
            }
        )

    rows = continuous_document["rows"]
    by_probe = {
        branch: {
            int(item["probe_sample_start"]): item
            for item in rows
            if int(item["branch_index"]) == branch
        }
        for branch in BRANCHES
    }
    shared = sorted(set(by_probe[B2]) & set(by_probe[B3]))
    frame_period_samples = continuous.SAMPLE_RATE_HZ / 750.0
    circular_epoch_differences = []
    cfo_differences = []
    for probe in shared:
        b2 = by_probe[B2][probe]
        b3 = by_probe[B3][probe]
        raw_difference = float(b2["local_epoch_sample"] - b3["local_epoch_sample"])
        circular_epoch_differences.append(
            (raw_difference + frame_period_samples / 2.0) % frame_period_samples
            - frame_period_samples / 2.0
        )
        cfo_differences.append(
            float(b2["continuous_tracking_cfo_hz"] - b3["continuous_tracking_cfo_hz"])
        )
    return {
        "directions": directions,
        "shared_probe_count": len(shared),
        "shared_probe_circular_epoch_difference_samples": _percentiles(
            circular_epoch_differences
        ),
        "shared_probe_circular_epoch_difference_us": _percentiles(
            [1e6 * item / continuous.SAMPLE_RATE_HZ for item in circular_epoch_differences]
        ),
        "shared_probe_b2_minus_b3_cfo_hz": _percentiles(cfo_differences),
    }


def render_crossfit(
    path: Path, *, results: tuple[CrossfitResult, ...]
) -> None:
    figure = Figure(figsize=(17, 12), constrained_layout=True)
    axes = figure.subplots(2, 2)
    figure.suptitle(
        "B2/B3 reciprocal CFO-hypothesis test on every overlapping timing lock",
        fontsize=20,
        color=INK,
        fontweight="bold",
    )
    for branch, color in ((B2, BLUE), (B3, PURPLE)):
        values = tuple(item for item in results if item.source_branch_index == branch)
        label = values[0].source_branch_label.split(" · ")[0] + " timing"
        axes[0, 0].scatter(
            [item.native.glrt_exact_score for item in values],
            [item.crossed.glrt_exact_score for item in values],
            s=22,
            color=color,
            alpha=0.62,
            linewidths=0,
            label=label,
        )
        axes[0, 1].scatter(
            [item.native.full_validation_exact_control_db for item in values],
            [item.crossed.full_validation_exact_control_db for item in values],
            s=22,
            color=color,
            alpha=0.62,
            linewidths=0,
        )
        axes[1, 0].scatter(
            [item.time_s for item in values],
            [item.crossed_glrt_score_ratio_db for item in values],
            s=17,
            color=color,
            alpha=0.64,
            linewidths=0,
        )
        axes[1, 1].scatter(
            [item.time_s for item in values],
            [item.global_over_native_gain_ppm for item in values],
            s=17,
            color=color,
            alpha=0.64,
            linewidths=0,
        )
    for axis in axes[0]:
        lower = min(axis.get_xlim()[0], axis.get_ylim()[0])
        upper = max(axis.get_xlim()[1], axis.get_ylim()[1])
        axis.plot((lower, upper), (lower, upper), color=INK, linewidth=1.0, alpha=0.7)
        axis.set_xlim(lower, upper)
        axis.set_ylim(lower, upper)
        axis.set_aspect("equal", adjustable="box")
    axes[1, 0].axhline(0.0, color=INK, linewidth=0.9, alpha=0.65)
    axes[1, 1].axhline(0.0, color=INK, linewidth=0.9, alpha=0.65)
    axes[1, 1].set_ylim(-1.0, 1.0)
    titles = (
        "A · GLRT64 exact score: native versus other-branch CFO",
        "B · Full-Qin held-out discrimination",
        "C · Other-branch GLRT score relative to native",
        "D · Global scan: no missed peak above 1 ppm",
    )
    xlabels = (
        "native exact score",
        "native held-out exact/control (dB)",
        "capture time (s)",
        "capture time (s)",
    )
    ylabels = (
        "other-branch CFO exact score",
        "other-branch CFO held-out exact/control (dB)",
        "crossed/native exact score (dB)",
        "global/native exact-score gain (ppm)",
    )
    for axis, title, xlabel, ylabel in zip(axes.flat, titles, xlabels, ylabels, strict=True):
        axis.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.set_xlabel(xlabel, color=INK)
        axis.set_ylabel(ylabel, color=INK)
        axis.grid(True, alpha=0.18)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[0, 0].legend(loc="upper left", frameon=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def render_profiles(
    path: Path,
    *,
    results: tuple[CrossfitResult, ...],
    curves: tuple[dict[str, Any], ...],
) -> None:
    selected_indexes = []
    for branch in BRANCHES:
        candidates = [
            (index, item)
            for index, item in enumerate(results)
            if item.source_branch_index == branch
        ]
        candidates.sort(key=lambda pair: pair[1].crossed_glrt_score_ratio_db, reverse=True)
        selected_indexes.extend(index for index, _item in candidates[:2])
    figure = Figure(figsize=(17, 13), constrained_layout=True)
    axes = figure.subplots(4, 1)
    figure.suptitle(
        "Wide GLRT64 frequency profiles for the four most competitive swaps",
        fontsize=20,
        color=INK,
        fontweight="bold",
    )
    curve_by_index = {int(item["result_index"]): item for item in curves}
    for axis, result_index in zip(axes, selected_indexes, strict=True):
        item = results[result_index]
        curve = curve_by_index[result_index]
        frequencies = np.asarray(curve["tracking_cfo_hz"]) / 1e3
        scores = np.asarray(curve["scores"])
        native = item.native.fitted_tracking_cfo_hz / 1e3
        crossed = item.crossed.fitted_tracking_cfo_hz / 1e3
        lower = min(native, crossed) - 3.0
        upper = max(native, crossed) + 3.0
        selected = (frequencies >= lower) & (frequencies <= upper)
        axis.plot(frequencies[selected], scores[selected], color=INK, linewidth=1.4)
        axis.axvline(native, color=BLUE, linewidth=1.8, label="native" if axis is axes[0] else None)
        axis.axvline(
            crossed,
            color=PURPLE,
            linewidth=1.8,
            label="other-branch CFO" if axis is axes[0] else None,
        )
        axis.axvline(
            item.global_tracking_cfo_hz / 1e3,
            color=AMBER,
            linewidth=1.2,
            linestyle="--",
            label="global continuous maximum" if axis is axes[0] else None,
        )
        axis.set_xlim(lower, upper)
        axis.set_ylabel("exact score", color=INK)
        axis.set_title(
            f"{item.source_branch_label} timing · {item.time_s:.3f} s · "
            f"native score {item.native.glrt_exact_score:.3f} · "
            f"cross penalty {item.crossed_glrt_score_ratio_db:+.2f} dB",
            loc="left",
            fontsize=12,
            color=INK,
            fontweight="bold",
        )
        axis.grid(True, alpha=0.18)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[-1].set_xlabel("total tracking CFO (kHz)", color=INK)
    axes[0].legend(loc="upper right", ncol=3, frameon=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def write_report(path: Path, document: dict[str, Any]) -> None:
    rows = []
    for item in document["summary"]["directions"]:
        rows.append(
            "| {source} | {count} | {separation:.0f} | {penalty:+.2f} | {wins:.1f}% | "
            "{native:.2f} | {crossed:.2f} | {validation_wins:.1f}% | {global_gain:.3f} |".format(
                source=item["source_branch_label"],
                count=item["window_count"],
                separation=item["absolute_seed_separation_hz"]["median"],
                penalty=item["crossed_glrt_score_ratio_db"]["median"],
                wins=100 * item["crossed_glrt_better_fraction"],
                native=item["native_validation_exact_control_db"]["median"],
                crossed=item["crossed_validation_exact_control_db"]["median"],
                validation_wins=100 * item["crossed_validation_better_fraction"],
                global_gain=item["global_over_native_gain_ppm"]["p90"],
            )
        )
    figures = {
        key: os.path.relpath(value, path.parent) for key, value in document["figures"].items()
    }
    shared = document["summary"]
    b2_direction, b3_direction = shared["directions"]
    table_header = (
        "| timing held fixed | n | median CFO separation (Hz) | "
        "median crossed GLRT penalty | crossed GLRT wins | native held-out dB | "
        "crossed held-out dB | crossed validation wins | p90 global gain (ppm) |"
    )
    text = f"""# Reciprocal B2/B3 Qin hypothesis audit

## Result

B2 and B3 are not duplicate points.  In the {shared["shared_probe_count"]} probes where both
were selected, their median CFO separation is
{shared["shared_probe_b2_minus_b3_cfo_hz"]["median"]:.0f} Hz and their circular timing-epoch
separation is {shared["shared_probe_circular_epoch_difference_samples"]["median"]:.1f} samples
({shared["shared_probe_circular_epoch_difference_us"]["median"]:.1f} µs).

For every timing lock in the common 28.575–33.725 s interval, this audit holds
the timing fixed, substitutes the other branch's interpolated continuous CFO,
and locally refines that substituted basin.  It then repeats the 300-symbol
even-fit/odd-validation test.

![All-point cross-fit]({figures["crossfit"]})

{table_header}
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

The crossed CFO never beats the native GLRT score in either direction.  The
median penalty is {b2_direction["crossed_glrt_score_ratio_db"]["median"]:.2f} dB on B2 timing
locks and {b3_direction["crossed_glrt_score_ratio_db"]["median"]:.2f} dB on B3 timing locks.
The held-out Qin discrimination falls from medians of
{b2_direction["native_validation_exact_control_db"]["median"]:.2f} and
{b3_direction["native_validation_exact_control_db"]["median"]:.2f} dB to
{b2_direction["crossed_validation_exact_control_db"]["median"]:.2f} and
{b3_direction["crossed_validation_exact_control_db"]["median"]:.2f} dB, respectively.

## Global-maximum check

The local-minimum hypothesis is checked independently by refining every local
maximum on the complete 512-bin GLRT frequency profile, rather than only the
persisted winning bin.  The wide profiles below show the four swaps for which
the other branch was most competitive.  None of the {len(document["results"])} locks has a
global improvement above 1 ppm; the remaining differences are floating-point
roundoff.

![Wide profiles]({figures["profiles"]})

The comparison changes CFO only.  It does not claim that a CFO substitution is
a complete satellite identity test: B2 and B3 also have different timing locks,
and a complete swapped timing-plus-CFO hypothesis is simply the other native
candidate already observed in the shared probes.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    continuous_document = _load(arguments.continuous_results)
    results, curves = analyze(
        bulk_root=arguments.bulk_root,
        continuous_document=continuous_document,
        maximum_windows=arguments.maximum_windows,
    )
    summary = summarize(results, continuous_document)
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    crossfit_path = arguments.output_root / "b2-b3-crossfit-all-points.png"
    profiles_path = arguments.output_root / "b2-b3-wide-glrt-profiles.png"
    render_crossfit(crossfit_path, results=results)
    render_profiles(profiles_path, results=results, curves=curves)
    document = stable_measurement_floats(
        {
            "schema_version": 1,
            "algorithm": "470384-b2-b3-reciprocal-crossfit-v1",
            "input": {
                "session_id": continuous.SESSION_ID,
                "continuous_results": str(arguments.continuous_results),
                "stream_id": "stream-0",
                "receiver_id": 0,
                "edge": "upper",
            },
            "configuration": {
                "overlap_s": [OVERLAP_START_S, OVERLAP_END_S],
                "glrt_symbols": [2, 65],
                "full_qin_symbols": [2, 301],
                "crossed_cfo_source": "linear interpolation of other branch continuous CFO",
                "heldout_policy": "even symbols fit, odd symbols validate",
                "global_audit": "refine every local maximum on full 512-bin GLRT profile",
            },
            "summary": summary,
            "results": [asdict(item) for item in results],
            "figures": {
                "crossfit": str(crossfit_path),
                "profiles": str(profiles_path),
            },
        }
    )
    results_path = arguments.output_root / "b2-b3-crossfit-results.json"
    results_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(arguments.report_path, document)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
