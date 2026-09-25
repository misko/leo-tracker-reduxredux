#!/usr/bin/env python3
"""Fit one CFO line to all 1.333 ms Qin-frame likelihoods in one joint search."""

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
    import report_470384_global_frame_line as frame_line
    import report_470384_semicoherent_recovery as semicoherent
except ModuleNotFoundError:  # pragma: no cover - imported from repository root
    from tools import report_470384_global_frame_line as frame_line
    from tools import report_470384_semicoherent_recovery as semicoherent


START_S = 33.7
END_S = 37.7
BRANCH_INDEX = 3
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_joint_frame_surface")
DEFAULT_REPORT = Path("reports/2026_08_23_470384_joint_frame_surface.md")
DEFAULT_PRIOR_RESULTS = frame_line.DEFAULT_OUTPUT_ROOT / "global-frame-linear-cfo-results.json"

INK = "#17354a"
GRAY = "#9aa6ae"
LIGHT_GRAY = "#d4dade"
AMBER = "#d9881f"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
RED = "#bd5b52"


@dataclass(frozen=True, slots=True)
class JointSearch:
    fit: frame_line.LinearFit
    coarse_intercepts_hz: np.ndarray
    coarse_slopes_hz_s: np.ndarray
    train_surface: np.ndarray
    validation_surface: np.ndarray
    validation_best_frequency_hz: float
    validation_best_slope_hz_s: float
    validation_best_score: float
    frame_coverage_fraction: float


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--frame-results", type=Path, default=semicoherent.DEFAULT_FRAME_RESULTS)
    parser.add_argument("--prior-results", type=Path, default=DEFAULT_PRIOR_RESULTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--start-s", type=float, default=START_S)
    parser.add_argument("--end-s", type=float, default=END_S)
    parser.add_argument("--minimum-frequency-hz", type=float, default=410_000.0)
    parser.add_argument("--maximum-frequency-hz", type=float, default=450_000.0)
    parser.add_argument("--minimum-slope-hz-s", type=float, default=-15_000.0)
    parser.add_argument("--maximum-slope-hz-s", type=float, default=2_000.0)
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


def score_surface(
    frames: tuple[semicoherent.FrameLikelihood, ...],
    *,
    reference_time_s: float,
    intercepts_hz: np.ndarray,
    slopes_hz_s: np.ndarray,
    split: Literal["even", "odd"],
) -> np.ndarray:
    """Evaluate one absolute CFO line per surface cell against every frame."""

    intercepts = np.asarray(intercepts_hz, dtype=float)
    slopes = np.asarray(slopes_hz_s, dtype=float)
    if not frames or intercepts.ndim != 1 or slopes.ndim != 1:
        raise ValueError("joint surface requires frames and one-dimensional parameter grids")
    return np.stack(
        [
            semicoherent.line_score(
                frames,
                split=split,
                sequence="exact",
                reference_time_s=reference_time_s,
                frequencies_at_reference_hz=intercepts,
                slope_hz_s=float(slope),
            )
            for slope in slopes
        ]
    )


def _surface_maximum(
    surface: np.ndarray,
    intercepts_hz: np.ndarray,
    slopes_hz_s: np.ndarray,
) -> tuple[float, float, float]:
    position = np.unravel_index(int(np.argmax(surface)), surface.shape)
    return (
        float(surface[position]),
        float(intercepts_hz[position[1]]),
        float(slopes_hz_s[position[0]]),
    )


def fit_joint_line(
    frames: tuple[semicoherent.FrameLikelihood, ...],
    *,
    frequency_bounds_hz: tuple[float, float],
    slope_bounds_hz_s: tuple[float, float],
    coarse_frequency_step_hz: float = 100.0,
    coarse_slope_step_hz_s: float = 250.0,
) -> JointSearch:
    """Run an unseeded two-parameter search over the complete absolute box."""

    if frequency_bounds_hz[1] <= frequency_bounds_hz[0]:
        raise ValueError("frequency bounds must be increasing")
    if slope_bounds_hz_s[1] <= slope_bounds_hz_s[0]:
        raise ValueError("slope bounds must be increasing")
    reference_time_s = float(np.mean([frame.time_s for frame in frames]))
    intercepts = np.arange(
        frequency_bounds_hz[0],
        frequency_bounds_hz[1] + 0.5 * coarse_frequency_step_hz,
        coarse_frequency_step_hz,
    )
    slopes = np.arange(
        slope_bounds_hz_s[0],
        slope_bounds_hz_s[1] + 0.5 * coarse_slope_step_hz_s,
        coarse_slope_step_hz_s,
    )
    train_surface = score_surface(
        frames,
        reference_time_s=reference_time_s,
        intercepts_hz=intercepts,
        slopes_hz_s=slopes,
        split="even",
    )
    validation_surface = score_surface(
        frames,
        reference_time_s=reference_time_s,
        intercepts_hz=intercepts,
        slopes_hz_s=slopes,
        split="odd",
    )
    _coarse_score, coarse_frequency, coarse_slope = _surface_maximum(
        train_surface, intercepts, slopes
    )
    fine_intercepts = np.arange(coarse_frequency - 150.0, coarse_frequency + 150.01, 1.0)
    fine_slopes = np.arange(coarse_slope - 300.0, coarse_slope + 300.01, 10.0)
    fine_train = score_surface(
        frames,
        reference_time_s=reference_time_s,
        intercepts_hz=fine_intercepts,
        slopes_hz_s=fine_slopes,
        split="even",
    )
    _fine_score, frequency, slope = _surface_maximum(
        fine_train, fine_intercepts, fine_slopes
    )
    fit = frame_line._evaluate_linear_fit(
        frames,
        reference_time_s=reference_time_s,
        frequency_at_reference_hz=frequency,
        slope_hz_s=slope,
    )
    validation_score, validation_frequency, validation_slope = _surface_maximum(
        validation_surface, intercepts, slopes
    )
    times = np.asarray([frame.time_s for frame in frames])
    ncos = np.asarray([frame.nco_cfo_hz for frame in frames])
    residuals = np.asarray(fit.frequency_hz(times)) - ncos
    limit = float(np.max(np.abs(semicoherent.RESIDUAL_GRID_HZ)))
    return JointSearch(
        fit=fit,
        coarse_intercepts_hz=intercepts,
        coarse_slopes_hz_s=slopes,
        train_surface=train_surface,
        validation_surface=validation_surface,
        validation_best_frequency_hz=validation_frequency,
        validation_best_slope_hz_s=validation_slope,
        validation_best_score=validation_score,
        frame_coverage_fraction=float(np.mean(np.abs(residuals) <= limit)),
    )


def _relative_db(surface: np.ndarray) -> np.ndarray:
    return 10.0 * np.log10(np.maximum(surface, 1e-20) / max(float(np.max(surface)), 1e-20))


def render(
    path: Path,
    *,
    branch: semicoherent.Branch,
    groups: tuple[tuple[semicoherent.Window, tuple[semicoherent.FrameLikelihood, ...]], ...],
    joint: JointSearch,
    prior_fit: frame_line.LinearFit | None,
    start_s: float,
    end_s: float,
) -> None:
    frames = tuple(frame for _window, members in groups for frame in members)
    times = np.asarray([frame.time_s for frame in frames])
    frame_cfos, heldout_margins = frame_line.independent_frame_cfos(frames)
    model = np.asarray(branch.frequency_hz(times))
    figure = Figure(figsize=(18, 13), constrained_layout=True)
    axes = figure.subplots(3, 1, gridspec_kw={"height_ratios": (1, 1, 1.25)})
    figure.suptitle(
        "One joint CFO-line adjustment of all 1,860 Qin frames",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    extent = (
        float(joint.coarse_intercepts_hz[0] / 1e3),
        float(joint.coarse_intercepts_hz[-1] / 1e3),
        float(joint.coarse_slopes_hz_s[0] / 1e3),
        float(joint.coarse_slopes_hz_s[-1] / 1e3),
    )
    for axis, surface, title in (
        (axes[0], joint.train_surface, "A · Joint training objective · even Qin symbols"),
        (axes[1], joint.validation_surface, "B · Disjoint validation objective · odd Qin symbols"),
    ):
        image = axis.imshow(
            np.maximum(_relative_db(surface), -20.0),
            origin="lower",
            aspect="auto",
            extent=extent,
            cmap="viridis",
            vmin=-20.0,
            vmax=0.0,
            interpolation="nearest",
        )
        axis.scatter(
            joint.fit.frequency_at_reference_hz / 1e3,
            joint.fit.slope_hz_s / 1e3,
            s=90,
            marker="x",
            color="white",
            linewidths=2.2,
            label="joint train optimum",
        )
        if prior_fit is not None:
            axis.scatter(
                prior_fit.frequency_at_reference_hz / 1e3,
                prior_fit.slope_hz_s / 1e3,
                s=70,
                marker="+",
                color=RED,
                linewidths=2.0,
                label="prior bounded optimum",
            )
        axis.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.set_ylabel("CFO rate (kHz/s)", color=INK)
        axis.set_xlabel(
            f"absolute CFO at t₀={joint.fit.reference_time_s:.6f} s (kHz)", color=INK
        )
        axis.legend(loc="lower right", ncol=2, frameon=True)
        colorbar = figure.colorbar(image, ax=axis, pad=0.01)
        colorbar.set_label("score relative to panel maximum (dB)", color=INK)

    positive = heldout_margins >= 0.0
    axes[2].scatter(
        times[~positive],
        frame_cfos[~positive] - model[~positive],
        s=8,
        color=GRAY,
        alpha=0.18,
        linewidths=0,
        rasterized=True,
        label=f"independent frame maximum, Qin≤control ({np.count_nonzero(~positive)})",
    )
    axes[2].scatter(
        times[positive],
        frame_cfos[positive] - model[positive],
        s=10,
        color=BLUE,
        alpha=0.62,
        linewidths=0,
        rasterized=True,
        label=f"independent frame maximum, Qin>control ({np.count_nonzero(positive)})",
    )
    line_times = np.linspace(start_s, end_s, 800)
    line_model = np.asarray(branch.frequency_hz(line_times))
    axes[2].plot(
        line_times,
        np.asarray(joint.fit.frequency_hz(line_times)) - line_model,
        color=AMBER,
        linewidth=2.5,
        label=(
            f"all-frame joint line · {joint.fit.slope_hz_s / 1e3:.3f} kHz/s"
        ),
    )
    for window, _members in groups:
        axes[2].axvline(
            window.detection_time_s,
            color=RED,
            linewidth=0.55,
            linestyle=(0, (3, 3)),
            alpha=0.16,
            zorder=0,
        )
    axes[2].axhline(0.0, color=INK, linewidth=0.8, alpha=0.55)
    axes[2].set_title(
        "C · The same two-parameter optimum evaluated across every frame",
        loc="left",
        fontsize=13,
        color=INK,
        fontweight="bold",
    )
    axes[2].set_ylabel("CFO − frozen B4 model (Hz)", color=INK)
    axes[2].set_xlabel("capture time (s)", color=INK)
    axes[2].set_xlim(start_s, end_s)
    axes[2].legend(loc="lower left", ncol=2, frameon=True)
    for axis in axes:
        axis.grid(True, alpha=0.14)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def write_report(path: Path, document: dict[str, Any]) -> None:
    figure = os.path.relpath(document["figure"], path.parent)
    joint = document["joint_fit"]
    comparison = document["comparison"]
    reference_row = (
        f"| CFO at reference time {joint['reference_time_s']:.6f} s | "
        f"{joint['frequency_at_reference_hz']:.1f} Hz |"
    )
    coverage_row = (
        "| frames inside their computed likelihood support | "
        f"{comparison['frame_coverage_fraction'] * 100:.1f}% |"
    )
    text = f"""# Unseeded joint CFO-line fit of all 1.333 ms Qin frames

## Result

The frequency optimizer evaluates one absolute intercept and one slope against
all {document['inventory']['frame_count']} frame likelihoods simultaneously.  It does not first
choose a CFO for each 20 ms probe or regress independent frame maxima.  The
20 ms results contribute timing epochs and a numerically convenient NCO origin
only; the broad joint search spans the complete configured absolute box.

![Unseeded all-frame joint likelihood]({figure})

| quantity | result |
| --- | ---: |
{reference_row}
| global CFO rate | {joint['slope_hz_s'] / 1e3:.3f} kHz/s |
| train exact/control | {joint['train_exact_control_db']:.2f} dB |
| held-out exact/control | {joint['validation_exact_control_db']:.2f} dB |
{coverage_row}

The unseeded optimum differs from the earlier bounded joint fit by
{comparison['frequency_difference_hz']:+.1f} Hz in intercept and
{comparison['slope_difference_hz_s']:+.1f} Hz/s in rate.  Its held-out exact
score changes by {comparison['heldout_exact_score_change_db']:+.4f} dB.

## Interpretation

The local NCO values do not act as fitted per-probe corrections in this
objective.  Each stored curve is sampled at `absolute line CFO - local NCO`, so
changing the NCO origin only changes coordinates while the complete line stays
inside curve support.  Timing acquisition remains inherited from the 20 ms
locks; a fully joint timing-and-frequency search would be a separate, much
larger problem.
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
    joint = fit_joint_line(
        frames,
        frequency_bounds_hz=(arguments.minimum_frequency_hz, arguments.maximum_frequency_hz),
        slope_bounds_hz_s=(arguments.minimum_slope_hz_s, arguments.maximum_slope_hz_s),
    )
    prior_document = _load(arguments.prior_results) if arguments.prior_results.exists() else None
    prior_fit = (
        frame_line.LinearFit(**prior_document["global_line"])
        if prior_document is not None
        else None
    )
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    figure_path = arguments.output_root / "joint-all-frame-cfo-surface.png"
    render(
        figure_path,
        branch=branch,
        groups=groups,
        joint=joint,
        prior_fit=prior_fit,
        start_s=arguments.start_s,
        end_s=arguments.end_s,
    )
    prior_validation = prior_fit.validation_exact_score if prior_fit is not None else math.nan
    document = stable_measurement_floats(
        {
            "schema_version": 1,
            "algorithm": "470384-unseeded-joint-all-frame-qin-line-v1",
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
                "frequency_bounds_hz": [
                    arguments.minimum_frequency_hz,
                    arguments.maximum_frequency_hz,
                ],
                "slope_bounds_hz_s": [
                    arguments.minimum_slope_hz_s,
                    arguments.maximum_slope_hz_s,
                ],
                "train_split": "even Qin symbols",
                "validation_split": "odd Qin symbols",
                "frame_phase_policy": "independent nuisance phase per frame",
                "fit_parameters": "one absolute CFO intercept plus one rate",
            },
            "inventory": {
                "probe_count": len(groups),
                "frame_count": len(frames),
                "frame_duration_ms": 4.0 / 3.0,
            },
            "joint_fit": asdict(joint.fit),
            "coarse_validation_maximum": {
                "frequency_at_reference_hz": joint.validation_best_frequency_hz,
                "slope_hz_s": joint.validation_best_slope_hz_s,
                "score": joint.validation_best_score,
            },
            "comparison": {
                "frame_coverage_fraction": joint.frame_coverage_fraction,
                "frequency_difference_hz": (
                    joint.fit.frequency_at_reference_hz - prior_fit.frequency_at_reference_hz
                    if prior_fit is not None
                    else math.nan
                ),
                "slope_difference_hz_s": (
                    joint.fit.slope_hz_s - prior_fit.slope_hz_s
                    if prior_fit is not None
                    else math.nan
                ),
                "heldout_exact_score_change_db": (
                    10.0
                    * math.log10(joint.fit.validation_exact_score / prior_validation)
                    if prior_fit is not None
                    else math.nan
                ),
            },
            "figure": str(figure_path),
        }
    )
    results_path = arguments.output_root / "joint-all-frame-cfo-results.json"
    results_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(arguments.report_path, document)
    print(
        json.dumps(
            {
                "inventory": document["inventory"],
                "joint_fit": document["joint_fit"],
                "coarse_validation_maximum": document["coarse_validation_maximum"],
                "comparison": document["comparison"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
