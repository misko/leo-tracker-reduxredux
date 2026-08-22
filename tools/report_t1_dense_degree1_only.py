#!/usr/bin/env python3
"""Build a strict degree-1 audit from T1 independent GLRT candidates.

This is a report-only analysis.  It deliberately does not read the published
trajectory or replay membership, because that membership may have been selected
by a higher-order representative.  Every fitted radio model in this module has
exactly an intercept and one slope.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DEFAULT_DENSE = Path(
    "reports/figures/2026_08_21_dense_independent_glrt/dense-independent-glrt-candidates.jsonl.gz"
)
DEFAULT_ABLATION = Path(
    "reports/figures/2026_08_21_dense_independent_glrt/dense-independent-glrt-ablation.json"
)
DEFAULT_OUTPUT = Path("reports/figures/2026_08_21_t1_dense_degree1_only")
DEFAULT_REPORT = Path("reports/2026_08_21_t1_dense_degree1_only.md")
SESSION_ID = "cap-20260821T201522-841b2a20e151"
PATH_LABEL = "stream-0/RX1"

# Seed windows stay away from the three visually suspected transition regions.
# They are declared up front; transition times are then selected from candidates.
SEED_WINDOWS = ((0.0, 6.5), (7.2, 13.2), (13.8, 19.9), (20.6, 27.25))
TRANSITION_WINDOWS = ((6.4, 7.2), (13.2, 13.9), (19.9, 20.6))


@dataclass(frozen=True, slots=True)
class Candidate:
    time_s: float
    sample_start: int
    rank: int
    frequency_hz: float
    margin: float
    exact_score: float
    control_score: float


@dataclass(frozen=True, slots=True)
class LineFit:
    start_s: float
    end_s: float
    slope_hz_s: float
    intercept_hz: float
    support_count: int
    available_probe_count: int
    residual_rms_hz: float
    median_absolute_residual_hz: float
    margin_sum: float
    selected: tuple[Candidate, ...]

    def predict(self, time_s: np.ndarray | float) -> np.ndarray:
        return self.slope_hz_s * np.asarray(time_s, dtype=float) + self.intercept_hz


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dense-candidates", type=Path, default=DEFAULT_DENSE)
    parser.add_argument("--ablation", type=Path, default=DEFAULT_ABLATION)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--trials", type=int, default=24_000)
    parser.add_argument("--null-repeats", type=int, default=80)
    parser.add_argument("--seed", type=int, default=20260821)
    return parser.parse_args()


def _dense_candidates(path: Path) -> tuple[Candidate, ...]:
    result = []
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            result.append(
                Candidate(
                    time_s=float(row["time_s"]),
                    sample_start=int(row["sample_start"]),
                    rank=int(row["rank"]),
                    frequency_hz=float(row["tracking_cfo_hz"]),
                    margin=float(row["margin"]),
                    exact_score=float(row["exact_score"]),
                    control_score=float(row["control_score"]),
                )
            )
    return tuple(result)


def group_candidates(
    candidates: Iterable[Candidate], *, margin_gate: float = 0.05
) -> dict[float, tuple[Candidate, ...]]:
    grouped: dict[float, list[Candidate]] = {}
    for item in candidates:
        if item.margin >= margin_gate:
            grouped.setdefault(item.time_s, []).append(item)
    return {
        time_s: tuple(sorted(rows, key=lambda item: item.rank))
        for time_s, rows in sorted(grouped.items())
    }


def huber_line(
    times_s: np.ndarray, frequencies_hz: np.ndarray, *, iterations: int = 30
) -> tuple[float, float, np.ndarray]:
    """Return a robust straight line; the returned coefficient count is always two."""

    times = np.asarray(times_s, dtype=float)
    values = np.asarray(frequencies_hz, dtype=float)
    if times.ndim != 1 or values.shape != times.shape or len(times) < 2:
        raise ValueError("a straight-line fit requires paired one-dimensional samples")
    center = float(np.mean(times))
    design = np.column_stack((times - center, np.ones(len(times))))
    coefficients = np.linalg.lstsq(design, values, rcond=None)[0]
    weights = np.ones(len(times), dtype=float)
    for _ in range(iterations):
        residual = values - design @ coefficients
        median = float(np.median(residual))
        scale = 1.4826 * float(np.median(np.abs(residual - median)))
        scale = max(scale, 25.0)
        cutoff = 1.345 * scale
        absolute = np.abs(residual)
        weights = np.minimum(1.0, cutoff / np.maximum(absolute, np.finfo(float).eps))
        weighted = design * np.sqrt(weights)[:, None]
        target = values * np.sqrt(weights)
        updated = np.linalg.lstsq(weighted, target, rcond=None)[0]
        if np.allclose(updated, coefficients, rtol=1e-10, atol=1e-7):
            coefficients = updated
            break
        coefficients = updated
    slope = float(coefficients[0])
    intercept = float(coefficients[1] - slope * center)
    return slope, intercept, weights


def _candidate_matrices(
    grouped: dict[float, tuple[Candidate, ...]], start_s: float, end_s: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[tuple[Candidate, ...]]]:
    times = np.asarray([time_s for time_s in grouped if start_s <= time_s < end_s])
    pools = [grouped[float(time_s)] for time_s in times]
    if len(times) < 2:
        raise ValueError("line interval has fewer than two evidence-bearing probes")
    maximum = max(len(pool) for pool in pools)
    frequency = np.full((len(times), maximum), np.nan)
    margin = np.full_like(frequency, np.nan)
    for row_index, pool in enumerate(pools):
        for column_index, item in enumerate(pool):
            frequency[row_index, column_index] = item.frequency_hz
            margin[row_index, column_index] = item.margin
    return times, frequency, margin, pools


def _associate(
    times: np.ndarray,
    pools: list[tuple[Candidate, ...]],
    slope_hz_s: float,
    intercept_hz: float,
    residual_gate_hz: float,
) -> tuple[tuple[Candidate, ...], np.ndarray]:
    selected = []
    errors = []
    for time_s, pool in zip(times, pools, strict=True):
        prediction = slope_hz_s * time_s + intercept_hz
        item = min(
            pool,
            key=lambda row: (
                abs(row.frequency_hz - prediction),
                -row.margin,
                row.rank,
            ),
        )
        error = abs(item.frequency_hz - prediction)
        if error <= residual_gate_hz:
            selected.append(item)
            errors.append(error)
    return tuple(selected), np.asarray(errors)


def fit_candidate_line(
    grouped: dict[float, tuple[Candidate, ...]],
    start_s: float,
    end_s: float,
    *,
    trials: int = 12_000,
    seed: int = 0,
    residual_gate_hz: float = 750.0,
    maximum_absolute_slope_hz_s: float = 30_000.0,
) -> LineFit:
    """RANSAC-select one candidate per probe, then Huber-refit one straight line."""

    times, frequency, margins, pools = _candidate_matrices(grouped, start_s, end_s)
    random = np.random.default_rng(seed)
    left_limit = max(1, len(times) // 3)
    right_start = max(left_limit, 2 * len(times) // 3)
    left_index = random.integers(0, left_limit, trials)
    right_index = random.integers(right_start, len(times), trials)
    left_candidate = np.asarray([random.integers(len(pools[index])) for index in left_index])
    right_candidate = np.asarray([random.integers(len(pools[index])) for index in right_index])
    left_value = np.asarray(
        [
            pools[index][candidate].frequency_hz
            for index, candidate in zip(left_index, left_candidate, strict=True)
        ]
    )
    right_value = np.asarray(
        [
            pools[index][candidate].frequency_hz
            for index, candidate in zip(right_index, right_candidate, strict=True)
        ]
    )
    slopes = (right_value - left_value) / (times[right_index] - times[left_index])
    intercepts = left_value - slopes * times[left_index]
    valid = np.abs(slopes) <= maximum_absolute_slope_hz_s
    slopes = slopes[valid]
    intercepts = intercepts[valid]
    if not len(slopes):
        raise ValueError("RANSAC generated no slope inside the configured bound")

    best_key: tuple[int, float, float] | None = None
    best_model: tuple[float, float] | None = None
    for offset in range(0, len(slopes), 256):
        batch_slopes = slopes[offset : offset + 256]
        batch_intercepts = intercepts[offset : offset + 256]
        prediction = (
            batch_slopes[:, None, None] * times[None, :, None] + batch_intercepts[:, None, None]
        )
        error = np.abs(frequency[None, :, :] - prediction)
        nearest_index = np.nanargmin(error, axis=2)
        nearest_error = np.take_along_axis(error, nearest_index[:, :, None], axis=2)[:, :, 0]
        expanded_margin = np.broadcast_to(margins, (len(batch_slopes),) + margins.shape)
        nearest_margin = np.take_along_axis(expanded_margin, nearest_index[:, :, None], axis=2)[
            :, :, 0
        ]
        inlier = nearest_error <= residual_gate_hz
        counts = np.sum(inlier, axis=1)
        weights = np.sum(np.where(inlier, nearest_margin, 0.0), axis=1)
        for local_index in range(len(batch_slopes)):
            residuals = nearest_error[local_index][inlier[local_index]]
            median_error = float(np.median(residuals)) if len(residuals) else math.inf
            key = (
                int(counts[local_index]),
                float(weights[local_index]),
                -median_error,
            )
            if best_key is None or key > best_key:
                best_key = key
                best_model = (
                    float(batch_slopes[local_index]),
                    float(batch_intercepts[local_index]),
                )
    assert best_model is not None
    slope, intercept = best_model
    for _ in range(12):
        selected, _ = _associate(times, pools, slope, intercept, residual_gate_hz)
        if len(selected) < 2:
            break
        updated_slope, updated_intercept, _ = huber_line(
            np.asarray([item.time_s for item in selected]),
            np.asarray([item.frequency_hz for item in selected]),
        )
        if np.allclose(
            (updated_slope, updated_intercept),
            (slope, intercept),
            rtol=1e-10,
            atol=1e-7,
        ):
            slope, intercept = updated_slope, updated_intercept
            break
        slope, intercept = updated_slope, updated_intercept
    selected, _ = _associate(times, pools, slope, intercept, residual_gate_hz)
    residuals = np.asarray(
        [item.frequency_hz - (slope * item.time_s + intercept) for item in selected]
    )
    return LineFit(
        start_s=start_s,
        end_s=end_s,
        slope_hz_s=slope,
        intercept_hz=intercept,
        support_count=len(selected),
        available_probe_count=len(times),
        residual_rms_hz=float(np.sqrt(np.mean(residuals**2))),
        median_absolute_residual_hz=float(np.median(np.abs(residuals))),
        margin_sum=float(sum(item.margin for item in selected)),
        selected=selected,
    )


def _transition_time(
    grouped: dict[float, tuple[Candidate, ...]],
    left: LineFit,
    right: LineFit,
    bounds: tuple[float, float],
    *,
    residual_gate_hz: float = 750.0,
) -> float:
    times = np.asarray([time_s for time_s in grouped if bounds[0] <= time_s < bounds[1]])
    if len(times) < 3:
        raise ValueError("transition interval has insufficient probes")
    best = None
    for cut in times[1:]:
        support = 0
        margin = 0.0
        errors = []
        for time_s in times:
            model = left if time_s < cut else right
            prediction = float(model.predict(time_s))
            item = min(grouped[float(time_s)], key=lambda row: abs(row.frequency_hz - prediction))
            error = abs(item.frequency_hz - prediction)
            if error <= residual_gate_hz:
                support += 1
                margin += item.margin
                errors.append(error)
        key = (support, margin, -float(np.median(errors)) if errors else -math.inf)
        if best is None or key > best[0]:
            best = key, float(cut)
    assert best is not None
    return best[1]


def fit_four_lines(
    grouped: dict[float, tuple[Candidate, ...]],
    *,
    trials: int,
    seed: int,
) -> tuple[tuple[LineFit, ...], tuple[float, ...]]:
    initial = tuple(
        fit_candidate_line(grouped, start, end, trials=trials, seed=seed + index)
        for index, (start, end) in enumerate(SEED_WINDOWS)
    )
    transitions = tuple(
        _transition_time(grouped, initial[index], initial[index + 1], bounds)
        for index, bounds in enumerate(TRANSITION_WINDOWS)
    )
    bounds = (0.0, *transitions, 27.25)
    fitted = tuple(
        fit_candidate_line(
            grouped,
            bounds[index],
            bounds[index + 1],
            trials=trials,
            seed=seed + 100 + index,
        )
        for index in range(4)
    )
    return fitted, transitions


def _scrambled(
    grouped: dict[float, tuple[Candidate, ...]], random: np.random.Generator
) -> dict[float, tuple[Candidate, ...]]:
    times = np.asarray(list(grouped))
    shifted = random.permutation(times)
    result = {}
    for target, source in zip(times, shifted, strict=True):
        result[float(target)] = tuple(
            Candidate(
                time_s=float(target),
                sample_start=item.sample_start,
                rank=item.rank,
                frequency_hz=item.frequency_hz,
                margin=item.margin,
                exact_score=item.exact_score,
                control_score=item.control_score,
            )
            for item in grouped[float(source)]
        )
    return result


def _null_supports(
    grouped: dict[float, tuple[Candidate, ...]],
    actual: tuple[LineFit, ...],
    transitions: tuple[float, ...],
    *,
    repeats: int,
    seed: int,
) -> np.ndarray:
    random = np.random.default_rng(seed)
    bounds = (0.0, *transitions, 27.25)
    result = []
    # The null reruns the same four RANSAC+Huber searches after permuting complete
    # candidate inventories among probe times. It preserves basin count, ranks,
    # CFO distribution, and margins while breaking temporal line coherence.
    for repeat in range(repeats):
        null = _scrambled(grouped, random)
        fits = tuple(
            fit_candidate_line(
                null,
                bounds[index],
                bounds[index + 1],
                trials=1_500,
                seed=seed + 10_000 + repeat * 4 + index,
            )
            for index in range(4)
        )
        result.append(sum(item.support_count for item in fits))
    return np.asarray(result, dtype=int)


def _line_summary(lines: tuple[LineFit, ...], transitions: tuple[float, ...]) -> list[dict]:
    result = []
    for index, line in enumerate(lines):
        step = None
        if index:
            transition = transitions[index - 1]
            step = float(line.predict(transition) - lines[index - 1].predict(transition))
        result.append(
            {
                "piece": index + 1,
                "interval_s": [line.start_s, line.end_s],
                "slope_hz_s": line.slope_hz_s,
                "intercept_hz": line.intercept_hz,
                "step_entering_hz": step,
                "support_count": line.support_count,
                "available_probe_count": line.available_probe_count,
                "residual_rms_hz": line.residual_rms_hz,
                "median_absolute_residual_hz": line.median_absolute_residual_hz,
                "margin_sum": line.margin_sum,
                "selected_rank_zero_count": sum(item.rank == 0 for item in line.selected),
            }
        )
    return result


def _plot_lines(
    path: Path,
    candidates: tuple[Candidate, ...],
    lines: tuple[LineFit, ...],
    transitions: tuple[float, ...],
) -> None:
    strong = tuple(item for item in candidates if item.margin >= 0.05)
    selected = tuple(item for line in lines for item in line.selected)
    figure, (axis, residual_axis) = plt.subplots(
        2, 1, figsize=(15.2, 7.8), sharex=True, gridspec_kw={"height_ratios": (2.2, 1.0)}
    )
    axis.scatter(
        [item.time_s for item in strong],
        [item.frequency_hz / 1_000 for item in strong],
        s=2,
        color="#aab2bb",
        alpha=0.10,
        linewidths=0,
        rasterized=True,
        label="all independent dense candidates, margin ≥ 0.05",
    )
    axis.scatter(
        [item.time_s for item in selected],
        [item.frequency_hz / 1_000 for item in selected],
        s=10,
        facecolors="none",
        edgecolors="#e17c05",
        linewidths=0.55,
        alpha=0.82,
        label="one associated candidate/probe",
    )
    for index, line in enumerate(lines):
        times = np.linspace(line.start_s, line.end_s, 200)
        axis.plot(
            times,
            line.predict(times) / 1_000,
            color="#111111",
            linewidth=0.85,
            label="RANSAC + Huber straight epochs" if index == 0 else None,
        )
        residuals = [item.frequency_hz - float(line.predict(item.time_s)) for item in line.selected]
        residual_axis.scatter(
            [item.time_s for item in line.selected],
            np.asarray(residuals) / 1_000,
            s=9,
            facecolors="none",
            edgecolors="#e17c05",
            linewidths=0.5,
        )
        midpoint = (line.start_s + line.end_s) / 2
        axis.annotate(
            f"P{index + 1}: {line.slope_hz_s / 1_000:+.3f} kHz/s",
            (midpoint, float(line.predict(midpoint)) / 1_000),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )
    for transition in transitions:
        axis.axvline(transition, color="#d1495b", linewidth=0.75, linestyle=":")
        residual_axis.axvline(transition, color="#d1495b", linewidth=0.75, linestyle=":")
    residual_axis.axhline(0, color="#111111", linewidth=0.6)
    residual_axis.axhspan(-0.75, 0.75, color="#2a9d8f", alpha=0.07)
    axis.set_ylim(-140, 65)
    axis.set_ylabel("baseband tracking CFO (kHz)")
    residual_axis.set_ylabel("line residual (kHz)")
    residual_axis.set_xlabel("capture time (s)")
    axis.set_title("A · independent candidates and four strict straight-line epochs", loc="left")
    residual_axis.set_title("B · associated-point residuals; no curved radio term", loc="left")
    axis.legend(fontsize=8, ncol=3, loc="lower left")
    for item in (axis, residual_axis):
        item.grid(alpha=0.14)
        item.set_xlim(0, 27.25)
    figure.suptitle(
        f"Strict degree-1 T1 association · {SESSION_ID} · {PATH_LABEL}\n"
        "raw-IQ independent GLRT candidates · 32 basins/probe · GLRT-4096",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.92))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _plot_basin_comparison(
    path: Path,
    ablation: dict,
    dense: tuple[Candidate, ...],
    dense_lines: tuple[LineFit, ...],
    dense_transitions: tuple[float, ...],
) -> None:
    figure, (timeline_axis, bar_axis) = plt.subplots(2, 1, figsize=(14.5, 8.0))
    visible = tuple(item for item in dense if 6.3 <= item.time_s < 8.1 and item.margin >= 0.05)
    selected = tuple(
        item for line in dense_lines[:2] for item in line.selected if 6.3 <= item.time_s < 8.1
    )
    timeline_axis.scatter(
        [item.time_s for item in visible],
        [item.frequency_hz / 1_000 for item in visible],
        s=5,
        color="#9aa4ad",
        alpha=0.18,
        linewidths=0,
        label="all margin-positive dense candidates",
    )
    timeline_axis.scatter(
        [item.time_s for item in selected],
        [item.frequency_hz / 1_000 for item in selected],
        s=15,
        facecolors="none",
        edgecolors="#e17c05",
        linewidths=0.65,
        label="strict-linear association",
    )
    for line in dense_lines[:2]:
        times = np.linspace(6.3, 8.1, 100)
        timeline_axis.plot(times, line.predict(times) / 1_000, color="#111111", linewidth=0.8)
    timeline_axis.axvline(dense_transitions[0], color="#d1495b", linestyle=":", linewidth=0.8)
    timeline_axis.axvspan(7.5, 7.9, color="#277da1", alpha=0.06)
    timeline_axis.set_title(
        "A · dense candidates across the first transition and P1 endpoint", loc="left"
    )
    timeline_axis.set_ylabel("tracking CFO (kHz)")
    timeline_axis.set_xlabel("capture time (s)")
    timeline_axis.set_xlim(6.3, 8.1)
    timeline_axis.set_ylim(-5, 18)
    timeline_axis.grid(alpha=0.15)
    timeline_axis.legend(fontsize=8, ncol=2, loc="best")

    populations = ablation["populations"]
    labels = (
        "8 basins\ncoarse grid",
        "8 basins\nfine grid",
        "32 basins\ncoarse grid",
        "32 basins\nfine grid",
    )
    counts = [item["critical_within_500_hz"] for item in populations]
    positions = np.arange(len(labels))
    bars = bar_axis.bar(
        positions,
        counts,
        color=("#8d99a6", "#277da1", "#2a9d8f", "#e17c05"),
    )
    for bar, item in zip(bars, populations, strict=True):
        bar_axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.2,
            f"{item['critical_maximum_absolute_residual_hz'] / 1_000:.2f} kHz max",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    bar_axis.set_xticks(positions, labels)
    bar_axis.set_ylim(0, 18)
    bar_axis.set_ylabel("7.5–7.9 s probes within 500 Hz (of 16)")
    bar_axis.set_title(
        "B · ablation separates basin retention from frequency-grid refinement",
        loc="left",
    )
    bar_axis.grid(axis="y", alpha=0.15)
    figure.suptitle(
        "Impact of acquisition-basin count and CFO refinement\n"
        "independent probes; post-hoc line diagnostics use intercept + slope only",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.91))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _plot_null(path: Path, actual_support: int, null_supports: np.ndarray) -> None:
    bins = np.arange(int(null_supports.min()) - 0.5, int(null_supports.max()) + 1.5)
    figure, axis = plt.subplots(figsize=(10.5, 4.8))
    axis.hist(
        null_supports,
        bins=bins,
        color="#8d99a6",
        alpha=0.75,
        label="time-permuted candidate inventories",
    )
    axis.axvline(
        actual_support,
        color="#d1495b",
        linewidth=1.2,
        label=f"recorded order: {actual_support}",
    )
    axis.set_xlabel("total inlier probes across four straight epochs")
    axis.set_ylabel("null repeats")
    axis.set_title("Matched candidate-inventory time-permutation control", loc="left")
    axis.grid(axis="y", alpha=0.15)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _report(summary: dict) -> str:
    dense = summary["dense"]
    standard = summary["standard"]
    rows = []
    for item in dense["pieces"]:
        interval = item["interval_s"]
        step = (
            "—"
            if item["step_entering_hz"] is None
            else f"{item['step_entering_hz'] / 1_000:+.2f} kHz"
        )
        rows.append(
            f"| {item['piece']} | {interval[0]:.3f}–{interval[1]:.3f} s | "
            f"{item['slope_hz_s']:+.1f} Hz/s | {step} | "
            f"{item['support_count']}/{item['available_probe_count']} | "
            f"{item['median_absolute_residual_hz']:.1f} Hz |"
        )
    return "\n".join(
        [
            "# Strict degree-1 T1 candidate association",
            "",
            f"Capture: `{SESSION_ID}`",
            f"Path: `{PATH_LABEL}`",
            "",
            "## Result",
            "",
            "The independently searched raw-IQ candidate inventory supports four straight "
            "frequency epochs separated by downward frequency steps. No order-2 or order-3 "
            "radio model, published final-trajectory membership, neighboring-probe seed, or "
            "TLE prediction is used. Candidate association is RANSAC followed by Huber "
            "straight-line refitting, with at most one candidate retained per probe.",
            "",
            "![Strict degree-1 T1 association]"
            "(figures/2026_08_21_t1_dense_degree1_only/"
            "t1-dense-degree1-only.png)",
            "",
            "| Piece | Candidate-selected interval | Constant Doppler rate | "
            "Step entering | Supported probes | Median absolute residual |",
            "|---:|---:|---:|---:|---:|---:|",
            *rows,
            "",
            "The first transition is selected at "
            f"**{dense['transitions_s'][0]:.3f} s**, not at the earlier plot's ≈7.9 s "
            "quarter boundary. That earlier boundary divided the retained trajectory into "
            "four equal-duration audit regions; it was not a fitted changepoint. The dense "
            "independent candidates instead show the first approximately 5 kHz downward "
            "frequency step around 6.8 s, followed by another straight epoch.",
            "",
            "None of the three transition times is inherited from a published polynomial "
            "trajectory. Four seed windows were placed post hoc away from the visually "
            "suspected transitions; straight lines were fitted there, and each transition "
            "time was then chosen by maximum one-line-per-side support in its disclosed "
            "transition window. The four-piece count and those windows are therefore "
            "exploratory choices, not pre-registered changepoint detections.",
            "",
            "## What candidate retention and the finer CFO search change",
            "",
            "An acquisition basin is one local timing/CFO maximum for one independently "
            "searched 20 ms probe. Retaining 32 rather than eight does not create more time "
            "samples and does not make probes dependent. It gives the association stage more "
            "alternate synchronization hypotheses to choose from after every probe has been "
            "scored independently.",
            "",
            "![Basin impact around the first transition]"
            "(figures/2026_08_21_t1_dense_degree1_only/"
            "t1-basin-impact-degree1-only.png)",
            "",
            f"With the dense inventory, the four straight epochs support "
            f"**{dense['total_support_count']}** evidence-bearing probes. At the previously "
            "suspicious 7.5–7.9 s endpoint, the controlled hyperparameter ablation recovered "
            "16/16 probes within 500 Hz with 32 basins, versus "
            f"{standard['critical_within_500_hz']}/16 with the persisted eight-basin search. "
            "That first comparison bundled several candidate-retention choices and used a "
            "locally refitted line. A later fixed-reference one-factor rerun found 15/16 for "
            "a finer coarse grid, 14/16 for 32 basins with the original broad separation, "
            "and 16/16 when only CFO/epoch nonmaximum-suppression separation was narrowed. "
            "Candidate-retention geometry—especially separation policy—is therefore the "
            "best-supported local mechanism; count alone is not sufficient. See the "
            "[full parameter study](2026_08_22_t1_glrt_search_parameter_study.md).",
            "",
            "This changes the earlier conclusion: the apparent loss at the end of the first "
            "plotted region is not evidence that the RF line vanished. The line is present in "
            "independent raw-IQ searches. What was brittle was which ambiguity basin survived "
            "candidate truncation and later association. It does **not** prove that every "
            "selected point is Starlink or that the four epochs belong to one spacecraft.",
            "",
            "## Look-elsewhere control",
            "",
            "![Time-permutation null]"
            "(figures/2026_08_21_t1_dense_degree1_only/"
            "t1-degree1-time-permutation-null.png)",
            "",
            f"The recorded ordering has {dense['total_support_count']} supported probes. "
            f"Across {dense['null_repeat_count']} controls that permute complete 32-basin "
            f"inventories among probe times and rerun all four straight-line searches, the "
            f"largest null support is {dense['null_max_support_count']}; the empirical "
            f"one-sided p-value is {dense['null_empirical_p']:.4f}. This control preserves "
            "candidate counts, ranks, CFO and score distributions while breaking temporal "
            "coherence. It covers the per-epoch line search but not the earlier human choice "
            "to inspect this capture or the transition-window placement, so it is evidence of "
            "line coherence—not a satellite-identification p-value.",
            "",
            "## Raw scan versus replay",
            "",
            "These orange points are from the **dense first scan of raw IQ**, not from replay. "
            "The published replay points are intentionally absent: their membership was "
            "seed-preserving from a representative selected from a mixed-order family, so "
            "reusing them would not be a strict degree-1 rerun. A valid replay comparison must "
            "start from these degree-1 associations, dechirp each epoch with its own straight "
            "line, and rerun the held-out pilot/control score on the same IQ probes. Until that "
            "bounded replay exists, the strongest defensible result is the independent raw-IQ "
            "candidate association shown here.",
            "",
            "## Reproduction and limitations",
            "",
            "- Tool: `tools/report_t1_dense_degree1_only.py`",
            "- Machine-readable summary: "
            "`figures/2026_08_21_t1_dense_degree1_only/"
            "t1-dense-degree1-summary.json`",
            "- Input candidate inventory: "
            "`figures/2026_08_21_dense_independent_glrt/"
            "dense-independent-glrt-candidates.jsonl.gz`",
            "- Candidate-only; no payload decoded and no new RF collected.",
            "- The 0.05 margin and 750 Hz residual gates were fixed for this audit "
            "but are not a corpus-calibrated detection threshold.",
            "- Thirty-two alternatives increase the comparison count. The matched "
            "time-permutation control is therefore essential, and wrong-code/wrong-edge "
            "controls remain required before attribution.",
            "",
        ]
    )


def main() -> int:
    args = _arguments()
    if args.trials < 1_000 or args.null_repeats < 10:
        raise ValueError("trial and null budgets are too small for this audit")
    dense_candidates = _dense_candidates(args.dense_candidates)
    ablation = json.loads(args.ablation.read_text(encoding="utf-8"))
    dense_grouped = group_candidates(dense_candidates)
    dense_lines, dense_transitions = fit_four_lines(
        dense_grouped, trials=args.trials, seed=args.seed
    )
    null_supports = _null_supports(
        dense_grouped,
        dense_lines,
        dense_transitions,
        repeats=args.null_repeats,
        seed=args.seed + 2_000,
    )
    actual_support = sum(item.support_count for item in dense_lines)
    empirical_p = float((1 + np.sum(null_supports >= actual_support)) / (len(null_supports) + 1))
    summary = {
        "schema": "org.leo.research.t1-dense-degree1-only/v1",
        "session_id": SESSION_ID,
        "path": PATH_LABEL,
        "radio_model": "intercept_plus_constant_slope_only",
        "candidate_only": True,
        "published_replay_membership_used": False,
        "configuration": {
            "margin_gate": 0.05,
            "residual_gate_hz": 750.0,
            "ransac_trials": args.trials,
            "seed_windows_s": SEED_WINDOWS,
            "transition_windows_s": TRANSITION_WINDOWS,
        },
        "dense": {
            "candidate_source": str(args.dense_candidates),
            "retained_basins_per_probe": 32,
            "pieces": _line_summary(dense_lines, dense_transitions),
            "transitions_s": dense_transitions,
            "total_support_count": actual_support,
            "null_repeat_count": len(null_supports),
            "null_support_counts": null_supports.tolist(),
            "null_max_support_count": int(null_supports.max()),
            "null_empirical_p": empirical_p,
        },
        "standard": ablation["populations"][0],
        "hyperparameter_ablation": ablation,
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    _plot_lines(
        args.output_root / "t1-dense-degree1-only.png",
        dense_candidates,
        dense_lines,
        dense_transitions,
    )
    _plot_basin_comparison(
        args.output_root / "t1-basin-impact-degree1-only.png",
        ablation,
        dense_candidates,
        dense_lines,
        dense_transitions,
    )
    _plot_null(
        args.output_root / "t1-degree1-time-permutation-null.png",
        actual_support,
        null_supports,
    )
    (args.output_root / "t1-dense-degree1-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.report.write_text(_report(summary), encoding="utf-8")
    print(json.dumps({"report": str(args.report), "output_root": str(args.output_root)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
