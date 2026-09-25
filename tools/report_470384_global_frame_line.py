#!/usr/bin/env python3
"""Fit all 1.333 ms Qin frames in 33.7–37.7 s to one linear CFO trajectory."""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.starlink.local_doppler import stable_measurement_floats

try:
    import report_470384_semicoherent_recovery as semicoherent
except ModuleNotFoundError:  # pragma: no cover - imported from repository root
    from tools import report_470384_semicoherent_recovery as semicoherent


START_S = 33.7
END_S = 37.7
BRANCH_INDEX = 3
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_global_frame_line")
DEFAULT_REPORT = Path("reports/2026_08_23_470384_global_frame_line.md")

INK = "#17354a"
GRAY = "#9aa6ae"
LIGHT_GRAY = "#d4dade"
AMBER = "#d9881f"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
RED = "#bd5b52"


@dataclass(frozen=True, slots=True)
class LinearFit:
    reference_time_s: float
    frequency_at_reference_hz: float
    slope_hz_s: float
    train_exact_score: float
    train_control_score: float
    train_exact_control_db: float
    validation_exact_score: float
    validation_control_score: float
    validation_exact_control_db: float

    def frequency_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        value = self.frequency_at_reference_hz + self.slope_hz_s * (
            np.asarray(time_s, dtype=float) - self.reference_time_s
        )
        return float(value) if np.ndim(value) == 0 else value


@dataclass(frozen=True, slots=True)
class ProbeFit:
    association_index: int
    detection_time_s: float
    reference_time_s: float
    frequency_at_reference_hz: float
    frame_count: int
    train_exact_score: float
    validation_exact_score: float
    validation_control_score: float
    validation_exact_control_db: float
    validation_exact_gain_db_vs_global: float


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--frame-results", type=Path, default=semicoherent.DEFAULT_FRAME_RESULTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--start-s", type=float, default=START_S)
    parser.add_argument("--end-s", type=float, default=END_S)
    parser.add_argument(
        "--maximum-windows",
        type=int,
        help="bounded development run over ordered probe windows",
    )
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _curve_denominator(
    frames: tuple[semicoherent.FrameLikelihood, ...],
    *,
    split: Literal["even", "odd"],
    sequence: Literal["exact", "control"],
) -> float:
    _power_field, ceiling_field = semicoherent._curve_fields(split, sequence)
    return float(sum(getattr(frame, ceiling_field) for frame in frames))


def trajectory_score(
    frames: tuple[semicoherent.FrameLikelihood, ...],
    frequencies_hz: np.ndarray,
    *,
    split: Literal["even", "odd"],
    sequence: Literal["exact", "control"],
) -> float:
    if not frames:
        raise ValueError("trajectory score requires at least one frame")
    predictions = np.asarray(frequencies_hz, dtype=float)
    if predictions.shape != (len(frames),):
        raise ValueError("trajectory frequencies must contain one value per frame")
    power_field, ceiling_field = semicoherent._curve_fields(split, sequence)
    curves = np.stack([getattr(frame, power_field) for frame in frames])
    targets = predictions - np.asarray([frame.nco_cfo_hz for frame in frames])
    sampled = semicoherent._sample_uniform_curves(curves, targets[:, None])[:, 0]
    denominator = float(sum(getattr(frame, ceiling_field) for frame in frames))
    return float(np.sum(sampled) / max(denominator, 1e-20))


def _evaluate_linear_fit(
    frames: tuple[semicoherent.FrameLikelihood, ...],
    *,
    reference_time_s: float,
    frequency_at_reference_hz: float,
    slope_hz_s: float,
) -> LinearFit:
    times = np.asarray([frame.time_s for frame in frames])
    predictions = frequency_at_reference_hz + slope_hz_s * (times - reference_time_s)
    scores = {
        (split, sequence): trajectory_score(
            frames,
            predictions,
            split=split,
            sequence=sequence,
        )
        for split in ("even", "odd")
        for sequence in ("exact", "control")
    }
    return LinearFit(
        reference_time_s=reference_time_s,
        frequency_at_reference_hz=frequency_at_reference_hz,
        slope_hz_s=slope_hz_s,
        train_exact_score=scores[("even", "exact")],
        train_control_score=scores[("even", "control")],
        train_exact_control_db=10.0
        * math.log10(scores[("even", "exact")] / max(scores[("even", "control")], 1e-20)),
        validation_exact_score=scores[("odd", "exact")],
        validation_control_score=scores[("odd", "control")],
        validation_exact_control_db=10.0
        * math.log10(scores[("odd", "exact")] / max(scores[("odd", "control")], 1e-20)),
    )


def fit_global_line(
    frames: tuple[semicoherent.FrameLikelihood, ...],
    *,
    initial_frequency_hz: float,
    initial_slope_hz_s: float,
) -> LinearFit:
    reference_time_s = float(np.mean([frame.time_s for frame in frames]))

    def search(intercepts: np.ndarray, slopes: np.ndarray) -> tuple[float, float, float]:
        best = (-math.inf, math.nan, math.nan)
        for slope in slopes:
            scores = semicoherent.line_score(
                frames,
                split="even",
                sequence="exact",
                reference_time_s=reference_time_s,
                frequencies_at_reference_hz=intercepts,
                slope_hz_s=float(slope),
            )
            position = int(np.argmax(scores))
            candidate = (float(scores[position]), float(intercepts[position]), float(slope))
            if candidate[0] > best[0]:
                best = candidate
        return best

    coarse = search(
        np.arange(initial_frequency_hz - 2_000.0, initial_frequency_hz + 2_000.1, 25.0),
        np.arange(initial_slope_hz_s - 2_000.0, initial_slope_hz_s + 2_000.1, 100.0),
    )
    refined = search(
        np.arange(coarse[1] - 50.0, coarse[1] + 50.01, 1.0),
        np.arange(coarse[2] - 100.0, coarse[2] + 100.01, 10.0),
    )
    return _evaluate_linear_fit(
        frames,
        reference_time_s=reference_time_s,
        frequency_at_reference_hz=refined[1],
        slope_hz_s=refined[2],
    )


def _probe_best_intercept(
    frames: tuple[semicoherent.FrameLikelihood, ...],
    *,
    reference_time_s: float,
    slope_hz_s: float,
    intercepts_hz: np.ndarray,
) -> tuple[float, float]:
    scores = semicoherent.line_score(
        frames,
        split="even",
        sequence="exact",
        reference_time_s=reference_time_s,
        frequencies_at_reference_hz=intercepts_hz,
        slope_hz_s=slope_hz_s,
    )
    position = int(np.argmax(scores))
    return float(intercepts_hz[position]), float(scores[position])


def fit_probe_family(
    groups: tuple[tuple[semicoherent.Window, tuple[semicoherent.FrameLikelihood, ...]], ...],
    *,
    global_fit: LinearFit,
) -> tuple[LinearFit, tuple[ProbeFit, ...]]:
    all_frames = tuple(frame for _window, frames in groups for frame in frames)

    def optimize_intercepts(slope_hz_s: float, step_hz: float) -> tuple[float, list[float]]:
        total_power = 0.0
        total_ceiling = 0.0
        intercepts = []
        for _window, frames in groups:
            reference = float(np.mean([frame.time_s for frame in frames]))
            center = float(global_fit.frequency_hz(reference))
            candidates = np.arange(center - 2_500.0, center + 2_500.1, step_hz)
            intercept, score = _probe_best_intercept(
                frames,
                reference_time_s=reference,
                slope_hz_s=slope_hz_s,
                intercepts_hz=candidates,
            )
            ceiling = _curve_denominator(frames, split="even", sequence="exact")
            total_power += score * ceiling
            total_ceiling += ceiling
            intercepts.append(intercept)
        return total_power / max(total_ceiling, 1e-20), intercepts

    coarse_best = (-math.inf, math.nan, [])
    for slope in np.arange(-12_000.0, 2_000.1, 100.0):
        score, intercepts = optimize_intercepts(float(slope), 25.0)
        if score > coarse_best[0]:
            coarse_best = (score, float(slope), intercepts)
    refined_best = (-math.inf, math.nan, [])
    for slope in np.arange(coarse_best[1] - 100.0, coarse_best[1] + 100.01, 10.0):
        score, intercepts = optimize_intercepts(float(slope), 25.0)
        if score > refined_best[0]:
            refined_best = (score, float(slope), intercepts)

    slope = refined_best[1]
    final_intercepts = []
    for (_window, frames), coarse_intercept in zip(groups, refined_best[2], strict=True):
        reference = float(np.mean([frame.time_s for frame in frames]))
        intercept, _score = _probe_best_intercept(
            frames,
            reference_time_s=reference,
            slope_hz_s=slope,
            intercepts_hz=np.arange(coarse_intercept - 25.0, coarse_intercept + 25.01, 1.0),
        )
        final_intercepts.append(intercept)

    predictions = []
    probe_fits = []
    for (window, frames), intercept in zip(groups, final_intercepts, strict=True):
        reference = float(np.mean([frame.time_s for frame in frames]))
        times = np.asarray([frame.time_s for frame in frames])
        predicted = intercept + slope * (times - reference)
        predictions.extend(predicted)
        train_exact = trajectory_score(frames, predicted, split="even", sequence="exact")
        validation_exact = trajectory_score(frames, predicted, split="odd", sequence="exact")
        validation_control = trajectory_score(frames, predicted, split="odd", sequence="control")
        global_predicted = np.asarray(global_fit.frequency_hz(times))
        global_validation_exact = trajectory_score(
            frames,
            global_predicted,
            split="odd",
            sequence="exact",
        )
        probe_fits.append(
            ProbeFit(
                association_index=window.association_index,
                detection_time_s=window.detection_time_s,
                reference_time_s=reference,
                frequency_at_reference_hz=intercept,
                frame_count=len(frames),
                train_exact_score=train_exact,
                validation_exact_score=validation_exact,
                validation_control_score=validation_control,
                validation_exact_control_db=10.0
                * math.log10(validation_exact / max(validation_control, 1e-20)),
                validation_exact_gain_db_vs_global=10.0
                * math.log10(validation_exact / max(global_validation_exact, 1e-20)),
            )
        )
    predictions_array = np.asarray(predictions)
    scores = {
        (split, sequence): trajectory_score(
            all_frames,
            predictions_array,
            split=split,
            sequence=sequence,
        )
        for split in ("even", "odd")
        for sequence in ("exact", "control")
    }
    family = LinearFit(
        reference_time_s=global_fit.reference_time_s,
        frequency_at_reference_hz=float(global_fit.frequency_at_reference_hz),
        slope_hz_s=slope,
        train_exact_score=scores[("even", "exact")],
        train_control_score=scores[("even", "control")],
        train_exact_control_db=10.0
        * math.log10(scores[("even", "exact")] / max(scores[("even", "control")], 1e-20)),
        validation_exact_score=scores[("odd", "exact")],
        validation_control_score=scores[("odd", "control")],
        validation_exact_control_db=10.0
        * math.log10(scores[("odd", "exact")] / max(scores[("odd", "control")], 1e-20)),
    )
    return family, tuple(probe_fits)


def independent_frame_cfos(
    frames: tuple[semicoherent.FrameLikelihood, ...],
) -> tuple[np.ndarray, np.ndarray]:
    frequencies = []
    margins = []
    for frame in frames:
        exact_position = int(np.argmax(frame.even_exact_power))
        frequency = frame.nco_cfo_hz + semicoherent.RESIDUAL_GRID_HZ[exact_position]
        frequencies.append(frequency)
        exact = frame.odd_exact_power[exact_position] / max(frame.odd_exact_ceiling, 1e-20)
        control = frame.odd_control_power[exact_position] / max(frame.odd_control_ceiling, 1e-20)
        margins.append(exact - control)
    return np.asarray(frequencies), np.asarray(margins)


def _model_frequency(branch: semicoherent.Branch, times_s: np.ndarray) -> np.ndarray:
    return np.asarray(branch.frequency_hz(times_s), dtype=float)


def render(
    path: Path,
    *,
    branch: semicoherent.Branch,
    groups: tuple[tuple[semicoherent.Window, tuple[semicoherent.FrameLikelihood, ...]], ...],
    global_fit: LinearFit,
    family_fit: LinearFit,
    probe_fits: tuple[ProbeFit, ...],
    start_s: float,
    end_s: float,
) -> None:
    frames = tuple(frame for _window, members in groups for frame in members)
    times = np.asarray([frame.time_s for frame in frames])
    frame_cfos, heldout_margins = independent_frame_cfos(frames)
    model = _model_frequency(branch, times)
    figure = Figure(figsize=(18, 15), constrained_layout=True)
    axes = figure.subplots(4, 1, sharex=True, gridspec_kw={"height_ratios": (1.35, 1, 0.9, 0.9)})
    figure.suptitle(
        "Joint full-Qin fit of every 1.333 ms frame · 33.7–37.7 s",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    probe_starts = [window.detection_time_s for window, _members in groups]
    for time_s in probe_starts:
        for axis in axes:
            axis.axvline(
                time_s,
                color=RED,
                linewidth=0.55,
                linestyle=(0, (3, 3)),
                alpha=0.16,
                zorder=0,
            )

    positive = heldout_margins >= 0.0
    axes[0].scatter(
        times[~positive],
        frame_cfos[~positive] - model[~positive],
        s=8,
        color=GRAY,
        alpha=0.20,
        linewidths=0,
        rasterized=True,
        label=f"frame maximum, held-out Qin≤control ({np.count_nonzero(~positive)})",
    )
    axes[0].scatter(
        times[positive],
        frame_cfos[positive] - model[positive],
        s=10,
        color=BLUE,
        alpha=0.64,
        linewidths=0,
        rasterized=True,
        label=f"frame maximum, held-out Qin>control ({np.count_nonzero(positive)})",
    )
    line_times = np.linspace(start_s, end_s, 800)
    axes[0].plot(
        line_times,
        np.asarray(global_fit.frequency_hz(line_times)) - _model_frequency(branch, line_times),
        color=INK,
        linewidth=2.4,
        label=f"one global line ({global_fit.slope_hz_s / 1e3:.3f} kHz/s)",
    )
    for index, ((_window, members), fit) in enumerate(zip(groups, probe_fits, strict=True)):
        member_times = np.asarray([frame.time_s for frame in members])
        prediction = fit.frequency_at_reference_hz + family_fit.slope_hz_s * (
            member_times - fit.reference_time_s
        )
        axes[0].plot(
            member_times,
            prediction - _model_frequency(branch, member_times),
            color=AMBER,
            linewidth=1.25,
            alpha=0.82,
            label=(
                f"per-probe intercept, shared slope ({family_fit.slope_hz_s / 1e3:.3f} kHz/s)"
                if index == 0
                else None
            ),
        )
    axes[0].axhline(0.0, color=INK, linewidth=0.75, alpha=0.5)

    global_predictions = np.asarray(global_fit.frequency_hz(times))
    axes[1].scatter(
        times,
        frame_cfos - global_predictions,
        s=9,
        color=BLUE,
        alpha=0.48,
        linewidths=0,
        rasterized=True,
    )
    axes[1].axhline(0.0, color=INK, linewidth=0.85, alpha=0.65)

    probe_times = np.asarray([item.reference_time_s for item in probe_fits])
    probe_validation = np.asarray([item.validation_exact_control_db for item in probe_fits])
    global_probe_validation = []
    for _window, members in groups:
        member_times = np.asarray([frame.time_s for frame in members])
        prediction = np.asarray(global_fit.frequency_hz(member_times))
        exact = trajectory_score(members, prediction, split="odd", sequence="exact")
        control = trajectory_score(members, prediction, split="odd", sequence="control")
        global_probe_validation.append(10.0 * math.log10(exact / max(control, 1e-20)))
    axes[2].scatter(
        probe_times,
        global_probe_validation,
        s=23,
        color=INK,
        alpha=0.58,
        linewidths=0,
        label="one global line",
    )
    axes[2].scatter(
        probe_times,
        probe_validation,
        s=23,
        color=AMBER,
        alpha=0.72,
        linewidths=0,
        label="per-probe intercept/shared slope",
    )
    axes[2].axhline(0.0, color=INK, linewidth=0.85, alpha=0.65)

    gains = np.asarray([item.validation_exact_gain_db_vs_global for item in probe_fits])
    improved = gains > 0.0
    axes[3].scatter(
        probe_times[~improved],
        gains[~improved],
        s=23,
        color=GRAY,
        alpha=0.58,
        linewidths=0,
        label="global line has higher held-out exact score",
    )
    axes[3].scatter(
        probe_times[improved],
        gains[improved],
        s=23,
        color=GREEN,
        alpha=0.72,
        linewidths=0,
        label="per-probe model has higher held-out exact score",
    )
    axes[3].axhline(0.0, color=INK, linewidth=0.85, alpha=0.65)

    titles = (
        "A · Independent frame maxima and trajectories, displayed against frozen B4",
        "B · Independent frame maximum minus the fitted global line",
        "C · Per-probe held-out odd-symbol exact/control discrimination",
        "D · Held-out exact-score gain from allowing one intercept per probe",
    )
    ylabels = (
        "CFO − B4 model (Hz)",
        "frame CFO − global line (Hz)",
        "held-out exact/control (dB)",
        "per-probe/global exact (dB)",
    )
    for axis, title, ylabel in zip(axes, titles, ylabels, strict=True):
        axis.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.set_ylabel(ylabel, color=INK)
        axis.grid(True, alpha=0.18)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[-1].set_xlabel("capture time (s)", color=INK)
    axes[-1].set_xlim(start_s, end_s)
    axes[0].legend(loc="lower left", ncol=2, frameon=True)
    axes[2].legend(loc="lower left", ncol=2, frameon=True)
    axes[3].legend(loc="lower left", ncol=2, frameon=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def _percentiles(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "p10": float(np.percentile(array, 10)),
        "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90)),
    }


def write_report(path: Path, document: dict[str, Any]) -> None:
    figure = os.path.relpath(document["figure"], path.parent)
    global_fit = document["global_line"]
    family = document["probe_intercept_family"]
    comparison = document["comparison"]
    table_rows = (
        "| one global line | "
        f"{global_fit['slope_hz_s'] / 1e3:.3f} kHz/s | "
        f"{global_fit['train_exact_control_db']:.2f} dB | "
        f"{global_fit['validation_exact_control_db']:.2f} dB | "
        f"{global_fit['validation_exact_score']:.5f} |\n"
        "| per-probe intercept/shared slope | "
        f"{family['slope_hz_s'] / 1e3:.3f} kHz/s | "
        f"{family['train_exact_control_db']:.2f} dB | "
        f"{family['validation_exact_control_db']:.2f} dB | "
        f"{family['validation_exact_score']:.5f} |"
    )
    text = f"""# Joint linear CFO fit of every 1.333 ms Qin frame

## Result

This analysis uses all {document["inventory"]["frame_count"]} complete frames from
{document["inventory"]["probe_count"]} 20 ms probes in the strict
{document["configuration"]["start_s"]:.1f}–{document["configuration"]["end_s"]:.1f} s interval.
Even Qin symbols fit the model; disjoint odd symbols validate it.  Every frame
has an independent nuisance phase, so no phase continuity across probe gaps is
assumed.

![Joint frame-line fit]({figure})

| model | CFO rate | train exact/control | held-out exact/control | held-out exact score |
| --- | ---: | ---: | ---: | ---: |
{table_rows}

Allowing one intercept per probe changes the aggregate held-out exact score by
{comparison["heldout_exact_gain_db"]:+.2f} dB.  It improves
{comparison["improved_probe_count"]} of {comparison["probe_count"]} probe holdouts;
the median per-probe gain is
{comparison["per_probe_heldout_exact_gain_db"]["median"]:+.2f} dB.

## Interpretation

The global line is fit directly to the Qin likelihood, not to accepted tracker
updates or to preselected frame-CFO points.  The per-probe model uses the same
shared slope but permits every artificial 20 ms analysis window to choose its
own intercept.  Its held-out advantage therefore measures how much frequency
structure the single smooth line cannot explain, while protecting against
within-frame symbol overfit.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    frame_document = _load(arguments.frame_results)
    branches, windows = semicoherent.parse_inputs(frame_document)
    branch = next(item for item in branches if item.index == BRANCH_INDEX)
    selected_windows = tuple(
        item
        for item in windows
        if item.branch_index == BRANCH_INDEX
        and arguments.start_s <= item.detection_time_s < arguments.end_s
    )
    if arguments.maximum_windows is not None:
        if arguments.maximum_windows < 1:
            raise ValueError("maximum window count must be positive")
        selected_windows = selected_windows[: arguments.maximum_windows]
    likelihoods = semicoherent.analyze_unique_windows(
        bulk_root=arguments.bulk_root,
        probe_samples=int(frame_document["configuration"].get("probe_samples", 50_000)),
        windows=selected_windows,
        maximum_unique_windows=None,
    )
    groups = tuple(
        (
            window,
            tuple(
                frame
                for frame in likelihoods[window.analysis_key]
                if arguments.start_s <= frame.time_s <= arguments.end_s
            ),
        )
        for window in selected_windows
    )
    groups = tuple((window, frames) for window, frames in groups if frames)
    frames = tuple(frame for _window, members in groups for frame in members)
    reference_time_s = float(np.mean([frame.time_s for frame in frames]))
    initial_frequency_hz = float(branch.frequency_hz(reference_time_s))
    derivative = np.polyder(np.asarray(branch.coefficients_hz, dtype=float))
    initial_slope_hz_s = float(np.polyval(derivative, reference_time_s - branch.reference_time_s))
    global_fit = fit_global_line(
        frames,
        initial_frequency_hz=initial_frequency_hz,
        initial_slope_hz_s=initial_slope_hz_s,
    )
    family_fit, probe_fits = fit_probe_family(groups, global_fit=global_fit)
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    figure_path = arguments.output_root / "global-frame-linear-cfo-fit.png"
    render(
        figure_path,
        branch=branch,
        groups=groups,
        global_fit=global_fit,
        family_fit=family_fit,
        probe_fits=probe_fits,
        start_s=arguments.start_s,
        end_s=arguments.end_s,
    )
    gains = [item.validation_exact_gain_db_vs_global for item in probe_fits]
    document = stable_measurement_floats(
        {
            "schema_version": 1,
            "algorithm": "470384-all-frame-global-linear-qin-likelihood-v1",
            "input": {
                "session_id": semicoherent.SESSION_ID,
                "frame_results": str(arguments.frame_results),
                "stream_id": "stream-0",
                "receiver_id": 0,
                "edge": "upper",
                "branch_label": branch.label,
            },
            "configuration": {
                "start_s": arguments.start_s,
                "end_s": arguments.end_s,
                "train_split": "even Qin symbols",
                "validation_split": "odd Qin symbols",
                "frame_phase_policy": "independent nuisance phase per frame",
                "global_model": "frequency intercept plus one shared linear rate",
                "comparison_model": "one intercept per probe plus one shared linear rate",
            },
            "inventory": {
                "probe_count": len(groups),
                "frame_count": len(frames),
                "frame_duration_ms": 4.0 / 3.0,
            },
            "global_line": asdict(global_fit),
            "probe_intercept_family": asdict(family_fit),
            "probe_fits": [asdict(item) for item in probe_fits],
            "comparison": {
                "heldout_exact_gain_db": 10.0
                * math.log10(
                    family_fit.validation_exact_score
                    / max(global_fit.validation_exact_score, 1e-20)
                ),
                "heldout_discrimination_gain_db": (
                    family_fit.validation_exact_control_db
                    - global_fit.validation_exact_control_db
                ),
                "probe_count": len(probe_fits),
                "improved_probe_count": sum(item > 0.0 for item in gains),
                "per_probe_heldout_exact_gain_db": _percentiles(gains),
            },
            "figure": str(figure_path),
        }
    )
    results_path = arguments.output_root / "global-frame-linear-cfo-results.json"
    results_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(arguments.report_path, document)
    summary = {
        "inventory": document["inventory"],
        "global_line": document["global_line"],
        "probe_intercept_family": document["probe_intercept_family"],
        "comparison": document["comparison"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
