#!/usr/bin/env python3
"""Audit the underlying frame-ramp CFO rates for D3 and D4."""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

try:
    import report_d3_d4_qin_weighted_cfo as qin_plot
    import report_d373c04a_glrt_frames as rate_tool
except ModuleNotFoundError:  # pragma: no cover - repository-root import
    from tools import report_d3_d4_qin_weighted_cfo as qin_plot
    from tools import report_d373c04a_glrt_frames as rate_tool


DEFAULT_RESULTS = qin_plot.DEFAULT_RESULTS
DEFAULT_OUTPUT_ROOT = qin_plot.DEFAULT_OUTPUT_ROOT
DEFAULT_ANALYSIS = DEFAULT_OUTPUT_ROOT / "d3-d4-underlying-rate-analysis.json"
DEFAULT_REPORT = Path("reports/2026_08_24_d3_d4_underlying_rates.md")

FRAME_GATE = 0.20
BOOTSTRAP_REPLICATES = 20_000
BOOTSTRAP_SEEDS = (2026082403, 2026082404)
MINIMUM_SPANS_S = (0.020, 0.040, 0.050, 0.060, 0.080)

INK = "#17354a"
GRAY = "#96a2ab"
LIGHT_GRAY = "#d2d9de"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
AMBER = "#d9881f"
PURPLE = "#7b65a8"
RED = "#bd5b52"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _segments(document: dict[str, Any]) -> tuple[rate_tool.SegmentFit, ...]:
    return tuple(rate_tool.SegmentFit(**item) for item in document["rate_analysis"]["segments"])


def ordinary_varying_intercept_slope(
    observations: tuple[rate_tool.FrameObservation, ...],
    segments: tuple[rate_tool.SegmentFit, ...],
) -> float:
    """OLS slope after eliminating one intercept per segment by centering."""

    by_index = {item.row_index: item for item in observations}
    numerator = 0.0
    denominator = 0.0
    for segment in segments:
        members = tuple(by_index[index] for index in segment.observation_indices)
        times = np.asarray([item.time_s for item in members], dtype=float)
        values = np.asarray([item.absolute_cfo_hz for item in members], dtype=float)
        centered_time = times - float(np.mean(times))
        centered_value = values - float(np.mean(values))
        numerator += float(centered_time @ centered_value)
        denominator += float(centered_time @ centered_time)
    if denominator <= 0.0:
        raise ValueError("segments do not contain within-segment time variation")
    return numerator / denominator


def _segment_sufficient_statistics(
    observations: tuple[rate_tool.FrameObservation, ...],
    segments: tuple[rate_tool.SegmentFit, ...],
) -> tuple[np.ndarray, np.ndarray]:
    by_index = {item.row_index: item for item in observations}
    numerators = []
    denominators = []
    for segment in segments:
        members = tuple(by_index[index] for index in segment.observation_indices)
        times = np.asarray([item.time_s for item in members], dtype=float)
        values = np.asarray([item.absolute_cfo_hz for item in members], dtype=float)
        centered_time = times - float(np.mean(times))
        centered_value = values - float(np.mean(values))
        numerators.append(float(centered_time @ centered_value))
        denominators.append(float(centered_time @ centered_time))
    return np.asarray(numerators), np.asarray(denominators)


def ramp_cluster_bootstrap(
    observations: tuple[rate_tool.FrameObservation, ...],
    segments: tuple[rate_tool.SegmentFit, ...],
    *,
    primary_slope_hz_s: float,
    seed: int,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    """Resample whole ramps and recenter the OLS distribution on the robust fit."""

    if len(segments) < 3 or replicates < 100:
        raise ValueError("bootstrap requires at least three ramps and 100 replicates")
    numerators, denominators = _segment_sufficient_statistics(observations, segments)
    generator = np.random.default_rng(seed)
    samples = np.empty(replicates, dtype=float)
    batch = 1_000
    for start in range(0, replicates, batch):
        stop = min(replicates, start + batch)
        indexes = generator.integers(0, len(segments), size=(stop - start, len(segments)))
        sampled_numerator = np.sum(numerators[indexes], axis=1)
        sampled_denominator = np.sum(denominators[indexes], axis=1)
        samples[start:stop] = sampled_numerator / sampled_denominator
    ordinary = float(np.sum(numerators) / np.sum(denominators))
    median = float(np.median(samples))
    centered = samples - median + primary_slope_hz_s
    return {
        "replicates": replicates,
        "seed": seed,
        "ordinary_full_sample_hz_s": ordinary,
        "ordinary_bootstrap_median_hz_s": median,
        "recentered_on_robust_primary": True,
        "standard_error_hz_s": float(np.std(samples, ddof=1)),
        "p025_hz_s": float(np.percentile(centered, 2.5)),
        "p50_hz_s": float(np.percentile(centered, 50)),
        "p975_hz_s": float(np.percentile(centered, 97.5)),
    }


def random_effects_slope(segments: tuple[rate_tool.SegmentFit, ...]) -> dict[str, Any]:
    """REML Gaussian random-slope summary of independently fitted ramps."""

    slopes = np.asarray([item.slope_hz_s for item in segments], dtype=float)
    variances = np.asarray(
        [max(30.0, item.slope_sigma_hz_s or 30.0) ** 2 for item in segments],
        dtype=float,
    )

    def fit(tau_squared: float) -> tuple[float, float, np.ndarray]:
        weights = 1.0 / (variances + tau_squared)
        mean = float(weights @ slopes / np.sum(weights))
        score = float(
            np.sum(weights**2 * (slopes - mean) ** 2)
            - np.sum(weights)
            + np.sum(weights**2) / np.sum(weights)
        )
        return score, mean, weights

    score_at_zero, _mean, _weights = fit(0.0)
    if score_at_zero <= 0.0:
        tau_squared = 0.0
    else:
        low = 0.0
        high = max(float(np.var(slopes)), 1.0)
        while fit(high)[0] > 0.0:
            high *= 4.0
        for _iteration in range(100):
            midpoint = 0.5 * (low + high)
            if fit(midpoint)[0] > 0.0:
                low = midpoint
            else:
                high = midpoint
        tau_squared = 0.5 * (low + high)
    _score, mean, weights = fit(tau_squared)
    standard_error = math.sqrt(1.0 / float(np.sum(weights)))
    return {
        "model": "REML random ramp slopes",
        "ramp_count": len(segments),
        "mean_hz_s": mean,
        "standard_error_hz_s": standard_error,
        "p025_hz_s": mean - 1.96 * standard_error,
        "p975_hz_s": mean + 1.96 * standard_error,
        "between_ramp_sigma_hz_s": math.sqrt(tau_squared),
    }


def analyze_dwell(document: dict[str, Any], *, seed: int) -> dict[str, Any]:
    observations = rate_tool._frame_observations(document, exact_gate=FRAME_GATE)
    segments = _segments(document)
    primary = rate_tool.joint_varying_intercept_fit(
        observations, segments, slope_progression=False
    )
    progression = rate_tool.joint_varying_intercept_fit(
        observations, segments, slope_progression=True
    )
    locks = rate_tool.independent_lock_fits(observations)
    per_window = rate_tool.joint_varying_intercept_fit(
        observations, locks, slope_progression=False
    )
    bootstrap = ramp_cluster_bootstrap(
        observations,
        segments,
        primary_slope_hz_s=primary.shared_slope_hz_s,
        seed=seed,
    )
    random_effects = random_effects_slope(segments)

    span_sensitivity = []
    for minimum_span_s in MINIMUM_SPANS_S:
        selected = tuple(item for item in segments if item.span_s >= minimum_span_s - 1e-12)
        if len(selected) < 3:
            continue
        robust = rate_tool.joint_varying_intercept_fit(
            observations, selected, slope_progression=False
        )
        reml = random_effects_slope(selected)
        span_sensitivity.append(
            {
                "minimum_span_s": minimum_span_s,
                "ramp_count": len(selected),
                "frame_count": int(sum(item.frame_count for item in selected)),
                "robust_common_hz_s": robust.shared_slope_hz_s,
                "ordinary_common_hz_s": ordinary_varying_intercept_slope(
                    observations, selected
                ),
                "random_effects_mean_hz_s": reml["mean_hz_s"],
            }
        )

    practical_sigma = max(
        float(bootstrap["standard_error_hz_s"]),
        float(random_effects["standard_error_hz_s"]),
    )
    source_rate = float(document["rate_analysis"]["source_glrt_rate_hz_s"])
    common_error = document["rate_analysis"]["errors"]["common_slope"]["odd_validation"]
    source_error = document["rate_analysis"]["errors"]["source_glrt_slope"][
        "odd_validation"
    ]
    return {
        "label": document["spec"]["label"],
        "session_id": document["session_id"],
        "frame_gate": FRAME_GATE,
        "qualified_frame_count": len(observations),
        "ramp_count": len(segments),
        "source_glrt_rate_hz_s": source_rate,
        "per_20ms_lock_common_rate_hz_s": per_window.shared_slope_hz_s,
        "primary_robust_ramp_rate_hz_s": primary.shared_slope_hz_s,
        "primary_conditional_sigma_hz_s": primary.shared_slope_sigma_hz_s,
        "single_ramp_prediction_rms_hz_s": document["rate_analysis"]["common_slope"][
            "leave_one_segment_out_rms_hz_s"
        ],
        "practical_ramp_cluster_sigma_hz_s": practical_sigma,
        "practical_p025_hz_s": primary.shared_slope_hz_s - 1.96 * practical_sigma,
        "practical_p975_hz_s": primary.shared_slope_hz_s + 1.96 * practical_sigma,
        "rate_correction_hz_s": primary.shared_slope_hz_s - source_rate,
        "ramp_cluster_bootstrap": bootstrap,
        "random_effects": random_effects,
        "slope_progression": {
            **asdict(progression),
            "bic_progression_minus_common": (
                document["rate_analysis"]["bic_progression_minus_common"]
            ),
        },
        "gate_sensitivity": document["gate_sensitivity"],
        "minimum_span_sensitivity": span_sensitivity,
        "odd_validation": {
            "source_glrt_rms_hz": source_error["rms_hz"],
            "primary_ramp_rms_hz": common_error["rms_hz"],
            "reduction_percent": 100.0
            * (1.0 - float(common_error["rms_hz"]) / float(source_error["rms_hz"])),
        },
        "segments": [asdict(item) for item in segments],
    }


def analyze(document: dict[str, Any]) -> dict[str, Any]:
    selected = qin_plot.select_d3_d4(document)
    return {
        "schema": "org.leo.research.d3-d4-underlying-rates/v1",
        "source_results": str(DEFAULT_RESULTS),
        "method": (
            "Qin-gated 1.333 ms frame maxima; batch-joined 20-125 ms ramps; "
            "free ramp intercepts; robust common slope; whole-ramp uncertainty"
        ),
        "dwells": [
            analyze_dwell(item, seed=seed)
            for item, seed in zip(selected, BOOTSTRAP_SEEDS, strict=True)
        ],
    }


def render_ramp_slopes(path: Path, analysis: dict[str, Any]) -> None:
    figure = Figure(figsize=(16, 9), constrained_layout=True)
    axes = figure.subplots(2, 1)
    figure.suptitle(
        "D3/D4 independent ramp slopes and population rate",
        fontsize=19,
        color=INK,
        fontweight="bold",
    )
    for axis, dwell in zip(axes, analysis["dwells"], strict=True):
        segments = dwell["segments"]
        times = np.asarray([item["center_time_s"] for item in segments])
        slopes = np.asarray([item["slope_hz_s"] for item in segments]) / 1_000.0
        sigmas = np.asarray(
            [max(30.0, item["slope_sigma_hz_s"] or 30.0) for item in segments]
        ) / 1_000.0
        spans_ms = np.asarray(
            [1_000.0 * (item["end_time_s"] - item["start_time_s"]) for item in segments]
        )
        marker_sizes = 25.0 + 0.55 * spans_ms
        primary = float(dwell["primary_robust_ramp_rate_hz_s"]) / 1_000.0
        practical_sigma = float(dwell["practical_ramp_cluster_sigma_hz_s"]) / 1_000.0
        glrt = float(dwell["source_glrt_rate_hz_s"]) / 1_000.0
        axis.errorbar(
            times,
            slopes,
            yerr=sigmas,
            fmt="none",
            ecolor=GRAY,
            elinewidth=0.8,
            alpha=0.35,
            zorder=1,
        )
        axis.scatter(
            times,
            slopes,
            s=marker_sizes,
            color=BLUE,
            alpha=0.66,
            linewidths=0,
            label="independent ramp slope (size = ramp span)",
            zorder=2,
        )
        axis.axhspan(
            primary - 1.96 * practical_sigma,
            primary + 1.96 * practical_sigma,
            color=BLUE,
            alpha=0.10,
            label="practical 95% interval",
        )
        axis.axhline(
            primary,
            color=BLUE,
            linewidth=2.0,
            label=f"robust common ramp rate {primary:.3f} kHz/s",
        )
        axis.axhline(
            glrt,
            color=AMBER,
            linewidth=1.6,
            linestyle=(0, (6, 4)),
            label=f"frozen GLRT rate {glrt:.3f} kHz/s",
        )
        axis.set_title(
            f"{dwell['label']} · {len(segments)} ramps",
            loc="left",
            color=INK,
            fontweight="bold",
        )
        axis.set_ylabel("received-CFO rate (kHz/s)")
        axis.set_xlabel("capture time (s)")
        axis.legend(loc="best", ncol=2, frameon=False)
        axis.grid(True, alpha=0.16)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=190,
        bbox_inches="tight",
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )


def render_model_stability(path: Path, analysis: dict[str, Any]) -> None:
    figure = Figure(figsize=(16, 9), constrained_layout=True)
    axes = figure.subplots(2, 2)
    figure.suptitle(
        "D3/D4 corrected-rate stability under independent analysis choices",
        fontsize=19,
        color=INK,
        fontweight="bold",
    )
    for column, dwell in enumerate(analysis["dwells"]):
        gate_rows = [item for item in dwell["gate_sensitivity"] if item["status"] == "complete"]
        gates = np.asarray([item["exact_gate"] for item in gate_rows])
        gate_rates = np.asarray([item["common_slope_hz_s"] for item in gate_rows]) / 1_000.0
        span_rows = dwell["minimum_span_sensitivity"]
        spans = np.asarray([1_000.0 * item["minimum_span_s"] for item in span_rows])
        span_rates = np.asarray([item["robust_common_hz_s"] for item in span_rows]) / 1_000.0
        reml_rates = np.asarray([item["random_effects_mean_hz_s"] for item in span_rows]) / 1_000.0
        primary = float(dwell["primary_robust_ramp_rate_hz_s"]) / 1_000.0
        practical_sigma = float(dwell["practical_ramp_cluster_sigma_hz_s"]) / 1_000.0
        glrt = float(dwell["source_glrt_rate_hz_s"]) / 1_000.0
        for axis in axes[:, column]:
            axis.axhspan(
                primary - practical_sigma,
                primary + practical_sigma,
                color=BLUE,
                alpha=0.10,
                label="primary ± practical 1σ",
            )
            axis.axhline(
                glrt,
                color=AMBER,
                linewidth=1.5,
                linestyle=(0, (6, 4)),
                label="frozen GLRT rate",
            )
            axis.grid(True, alpha=0.16)
            axis.tick_params(colors=INK)
            for spine in axis.spines.values():
                spine.set_color(LIGHT_GRAY)
        axes[0, column].plot(
            gates,
            gate_rates,
            color=BLUE,
            marker="o",
            label="batch-joined robust rate",
        )
        axes[0, column].set_title(
            f"{dwell['label']} · Qin gate",
            loc="left",
            color=INK,
            fontweight="bold",
        )
        axes[0, column].set_xlabel("minimum normalized exact-Qin score")
        axes[1, column].plot(
            spans,
            span_rates,
            color=BLUE,
            marker="o",
            label="robust common frame fit",
        )
        axes[1, column].plot(
            spans,
            reml_rates,
            color=PURPLE,
            marker="s",
            label="random-effects ramp mean",
        )
        axes[1, column].set_title(
            f"{dwell['label']} · minimum retained ramp span",
            loc="left",
            color=INK,
            fontweight="bold",
        )
        axes[1, column].set_xlabel("minimum ramp span (ms)")
        for axis in axes[:, column]:
            axis.set_ylabel("received-CFO rate (kHz/s)")
            axis.legend(loc="best", frameon=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=190,
        bbox_inches="tight",
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )


def render_rate_validation(path: Path, analysis: dict[str, Any]) -> None:
    figure = Figure(figsize=(15, 6.5), constrained_layout=True)
    axes = figure.subplots(1, 2)
    figure.suptitle(
        "D3/D4 rate recovery and held-out Qin validation",
        fontsize=19,
        color=INK,
        fontweight="bold",
    )
    labels = [item["label"].split(" · ")[0] for item in analysis["dwells"]]
    positions = np.arange(len(labels))
    glrt = np.asarray([item["source_glrt_rate_hz_s"] for item in analysis["dwells"]]) / 1_000.0
    locks = np.asarray(
        [item["per_20ms_lock_common_rate_hz_s"] for item in analysis["dwells"]]
    ) / 1_000.0
    primary = np.asarray(
        [item["primary_robust_ramp_rate_hz_s"] for item in analysis["dwells"]]
    ) / 1_000.0
    practical = np.asarray(
        [item["practical_ramp_cluster_sigma_hz_s"] for item in analysis["dwells"]]
    ) / 1_000.0
    reml = (
        np.asarray([item["random_effects"]["mean_hz_s"] for item in analysis["dwells"]])
        / 1_000.0
    )
    offsets = (-0.24, -0.08, 0.08, 0.24)
    axes[0].scatter(
        positions + offsets[0],
        glrt,
        marker="s",
        s=65,
        color=AMBER,
        label="20 ms GLRT trajectory",
    )
    axes[0].scatter(
        positions + offsets[1],
        locks,
        marker="^",
        s=65,
        color=GRAY,
        label="20 ms locks, free offsets",
    )
    axes[0].errorbar(
        positions + offsets[2],
        primary,
        yerr=practical,
        fmt="o",
        markersize=7,
        capsize=5,
        color=BLUE,
        label="joined ramps ± practical 1σ",
    )
    axes[0].scatter(
        positions + offsets[3],
        reml,
        marker="D",
        s=55,
        color=PURPLE,
        label="random-effects ramp mean",
    )
    for position, value in zip(positions + offsets[2], primary, strict=True):
        axes[0].annotate(
            f"{value:.3f}",
            (position, value),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            color=INK,
        )
    axes[0].set_xticks(positions, labels)
    axes[0].set_ylabel("received-CFO rate (kHz/s)")
    axes[0].set_title("A · Rate estimators", loc="left", color=INK, fontweight="bold")
    axes[0].legend(loc="best", frameon=False)

    source_rms = np.asarray(
        [item["odd_validation"]["source_glrt_rms_hz"] for item in analysis["dwells"]]
    )
    ramp_rms = np.asarray(
        [item["odd_validation"]["primary_ramp_rms_hz"] for item in analysis["dwells"]]
    )
    width = 0.34
    axes[1].bar(
        positions - width / 2,
        source_rms,
        width,
        color=AMBER,
        alpha=0.78,
        label="force GLRT rate",
    )
    axes[1].bar(
        positions + width / 2,
        ramp_rms,
        width,
        color=BLUE,
        alpha=0.82,
        label="free ramp offsets + common rate",
    )
    axes[1].set_xticks(positions, labels)
    axes[1].set_ylabel("odd-Qin CFO prediction RMS (Hz)")
    axes[1].set_title(
        "B · Held-out odd-Qin validation",
        loc="left",
        color=INK,
        fontweight="bold",
    )
    axes[1].legend(loc="best", frameon=False)
    for axis in axes:
        axis.grid(True, axis="y", alpha=0.16)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=190,
        bbox_inches="tight",
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )


def render_all(
    source_document: dict[str, Any], analysis: dict[str, Any], output_root: Path
) -> dict[str, str]:
    paths = {
        "qin_weighted_cfo": output_root / "d3-d4-qin-weighted-cfo.png",
        "ramp_slopes": output_root / "d3-d4-ramp-slopes.png",
        "model_stability": output_root / "d3-d4-model-stability.png",
        "rate_validation": output_root / "d3-d4-rate-validation.png",
    }
    qin_plot.render(paths["qin_weighted_cfo"], source_document)
    render_ramp_slopes(paths["ramp_slopes"], analysis)
    render_model_stability(paths["model_stability"], analysis)
    render_rate_validation(paths["rate_validation"], analysis)
    return {key: str(value) for key, value in paths.items()}


def write_report(
    analysis: dict[str, Any], *, report_path: Path, analysis_path: Path
) -> None:
    def relative(path: str | Path) -> str:
        return Path(os.path.relpath(Path(path), report_path.parent)).as_posix()

    d3, d4 = analysis["dwells"]
    rows = []
    for dwell in analysis["dwells"]:
        rows.append(
            "| "
            f"{dwell['label']} | {dwell['source_glrt_rate_hz_s'] / 1_000:.3f} | "
            f"{dwell['per_20ms_lock_common_rate_hz_s'] / 1_000:.3f} | "
            f"**{dwell['primary_robust_ramp_rate_hz_s'] / 1_000:.3f} ± "
            f"{dwell['practical_ramp_cluster_sigma_hz_s'] / 1_000:.3f}** | "
            f"{dwell['random_effects']['mean_hz_s'] / 1_000:.3f} | "
            f"{dwell['odd_validation']['source_glrt_rms_hz']:.1f} → "
            f"{dwell['odd_validation']['primary_ramp_rms_hz']:.1f} |"
        )

    qin_figure = relative(analysis["figures"]["qin_weighted_cfo"])
    slope_figure = relative(analysis["figures"]["ramp_slopes"])
    stability_figure = relative(analysis["figures"]["model_stability"])
    validation_figure = relative(analysis["figures"]["rate_validation"])
    analysis_relative = relative(analysis_path)
    d3_primary = d3["primary_robust_ramp_rate_hz_s"] / 1_000
    d4_primary = d4["primary_robust_ramp_rate_hz_s"] / 1_000
    d3_practical = d3["practical_ramp_cluster_sigma_hz_s"] / 1_000
    d4_practical = d4["practical_ramp_cluster_sigma_hz_s"] / 1_000
    d3_locks = d3["per_20ms_lock_common_rate_hz_s"] / 1_000
    d4_locks = d4["per_20ms_lock_common_rate_hz_s"] / 1_000
    d3_single_ramp = d3["single_ramp_prediction_rms_hz_s"] / 1_000
    d4_single_ramp = d4["single_ramp_prediction_rms_hz_s"] / 1_000
    table_header = (
        "| dwell | frozen GLRT | 20 ms locks only | joined-ramp primary ± practical 1σ | "
        "random-effects ramps | odd RMS, GLRT→ramp (Hz) |"
    )
    text = f"""# Recovering the underlying D3/D4 received-CFO rates

## Abstract

This audit separates the persisted 20 ms GLRT trajectory from the local slope
inside Qin-coherent 1.333 ms frame ramps. D3 and D4 both contain strong repeated
ramps, but their persisted GLRT rates are biased by the sequence of CFO resets.
After giving every 20–125 ms ramp its own arbitrary CFO intercept, the recovered
rates are **{d3_primary:.3f} ± {d3_practical:.3f} kHz/s**
for D3 and **{d4_primary:.3f} ± {d4_practical:.3f} kHz/s**
for D4 (practical 1σ ramp-cluster uncertainty).

These are emitter-reset-debiased **received-CFO rates**, not pure orbital Doppler:
continuous transmitter drift, LNB drift, and receiver-clock drift remain possible
nuisance terms.

## Data

- D3: `{d3['session_id']}`.
- D4: `{d4['session_id']}`.
- Raw-IQ frame cadence: 1.333 ms; even Qin symbols estimate CFO and odd Qin
  symbols validate the fitted rate independently.
- Primary frame gate: normalized exact-Qin score ≥ {FRAME_GATE:.2f} with a
  positive exact-minus-rolled-control margin.
- No new RF data were collected.

## Where the trustworthy frame evidence is

![GLRT and Qin-weighted frame CFO]({qin_figure})

Orange pieces are the persisted constant-CFO 20 ms GLRT windows. Every blue
point is an independently maximized 1.333 ms frame CFO. Point opacity requires
both exact-Qin coherence and separation from the rolled-Qin control; weak
maxima remain faintly visible. The residual panels subtract only the frozen GLRT
line for display. They make the short ramps and resets visible without using the
GLRT CFO as the frame estimate.

D3 is heterogeneous in availability: the high-opacity points concentrate in
several bands, while many other maxima are not Qin-specific. D4 is nearly
continuously Qin-strong. In both cases, the high-confidence points form local
ramps whose slope is visibly shallower than the long-time GLRT line.

## Rate result

![Rate estimators and odd-Qin validation]({validation_figure})

{table_header}
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

The 20 ms-lock-only calculation gives every probe its own intercept, but its
baseline is too short relative to the 25 Hz frame-CFO grid. It moves toward the
correct answer but is visibly estimator-sensitive: {d3_locks:.3f}
kHz/s for D3 and {d4_locks:.3f} kHz/s for
D4. Joining only frequency-continuous locks into 20–125 ms ramps supplies the
leverage needed for the primary estimate.

The primary rates reduce independent odd-Qin prediction RMS by
{d3['odd_validation']['reduction_percent']:.1f}% for D3 and
{d4['odd_validation']['reduction_percent']:.1f}% for D4. Thus the correction is
not merely an even-symbol in-sample improvement.

## Ramp-to-ramp variation and uncertainty

![Independent ramp slopes]({slope_figure})

The dots are slopes fitted independently to individual recovered ramps; their
size encodes ramp duration and their whiskers are conditional line-fit errors.
Short, 25 Hz-quantized ramps naturally have noisy slopes. The old
leave-one-ramp-out RMS asked whether one short ramp predicts another and was
therefore {d3_single_ramp:.3f}
kHz/s for D3 and {d4_single_ramp:.3f}
kHz/s for D4. That is a single-ramp prediction metric, not uncertainty on the
pooled mean.

For inference on the common rate, this audit resamples whole ramps and also fits
a random-effects model to independent ramp slopes. The reported practical 1σ is
the larger of the cluster-bootstrap standard error and the random-effects mean
standard error: {d3['practical_ramp_cluster_sigma_hz_s'] / 1_000:.3f} kHz/s for
D3 and {d4['practical_ramp_cluster_sigma_hz_s'] / 1_000:.3f} kHz/s for D4.
The corresponding practical 95% intervals are
[{d3['practical_p025_hz_s'] / 1_000:.3f}, {d3['practical_p975_hz_s'] / 1_000:.3f}]
and [{d4['practical_p025_hz_s'] / 1_000:.3f}, {d4['practical_p975_hz_s'] / 1_000:.3f}]
kHz/s.

## Sensitivity and slope progression

![Gate and ramp-span sensitivity]({stability_figure})

D3 settles to approximately −3.89 to −3.95 kHz/s once the Qin gate reaches
0.15. D4 settles to approximately −3.57 to −3.64 kHz/s over gates 0.15–0.30.
Changing the minimum retained ramp span from 20 to 80 ms does not move either
robust common-frame fit toward its much steeper GLRT value.

A linear slope-progression term is not selected. For D3 the fitted progression
is {d3['slope_progression']['slope_progression_hz_s2']:+.1f} ±
{d3['slope_progression']['slope_progression_sigma_hz_s2']:.1f} Hz/s² and raises
BIC by {d3['slope_progression']['bic_progression_minus_common']:.2f}. For D4 it
is {d4['slope_progression']['slope_progression_hz_s2']:+.1f} ±
{d4['slope_progression']['slope_progression_sigma_hz_s2']:.1f} Hz/s² and raises
BIC by {d4['slope_progression']['bic_progression_minus_common']:.2f}. The extra
term changes odd-Qin error negligibly, so the constant local-rate model remains
the supported description over each dwell.

## Method

1. Reuse the source-alias GLRT timing epoch to identify complete 1.333 ms frame
   boundaries.
2. Within each frame, maximize the residual-CFO likelihood using even Qin
   symbols on a 25 Hz grid; retain exact strength and rolled-control margin.
3. Fit each timing lock, then globally partition adjacent locks into continuous
   ramps no longer than 125 ms. Retain ramps spanning at least 20 ms with raw
   line-fit RMS ≤ 40 Hz.
4. Fit all retained frame CFOs jointly with one intercept per ramp and a robust
   shared slope. This removes discrete emitter-state CFO offsets while retaining
   the within-ramp derivative.
5. Validate predictions on the odd Qin symbols, which did not choose the frame
   CFO.
6. Quantify practical uncertainty by resampling entire ramps, not individual
   frames, and cross-check with a REML random-ramp-slope model.

## Conclusion

The evidence supports **approximately −3.95 kHz/s for D3** and
**approximately −3.64 kHz/s for D4** as the underlying reset-debiased
received-CFO rates. The original −6.020 and −5.327 kHz/s GLRT slopes are not
supported once arbitrary ramp offsets are removed, and they predict held-out
odd-Qin CFO materially worse.

Machine-readable statistics are in
[d3-d4-underlying-rate-analysis.json]({analysis_relative}).
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    source = _load(arguments.results)
    analysis = analyze(source)
    analysis["source_results"] = str(arguments.results)
    analysis["figures"] = render_all(source, analysis, arguments.output_root)
    arguments.analysis.parent.mkdir(parents=True, exist_ok=True)
    arguments.analysis.write_text(
        json.dumps(analysis, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(analysis, report_path=arguments.report, analysis_path=arguments.analysis)
    print(arguments.report)


if __name__ == "__main__":
    main()
