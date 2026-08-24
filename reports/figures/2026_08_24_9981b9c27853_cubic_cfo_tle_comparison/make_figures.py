#!/usr/bin/env python3
# ruff: noqa: E501, B905
"""Rebuild the static figures for the cap9981 CFO/TLE report.

The script reads only the compact, digest-bound ``evidence.json`` committed next
to it.  It deliberately does not open the recording corpus or the TLE archive.
"""

from __future__ import annotations

import json
import warnings
from datetime import UTC, datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence.json"

COLORS = {
    "blue": "#0072B2",
    "orange": "#E69F00",
    "green": "#009E73",
    "red": "#D55E00",
    "purple": "#CC79A7",
    "sky": "#56B4E9",
    "yellow": "#F0E442",
    "black": "#202124",
    "gray": "#777777",
    "light_gray": "#D8DCE2",
    "pale_blue": "#DCEAF7",
    "pale_orange": "#FBE8C5",
    "pale_green": "#DDF2EA",
    "pale_red": "#F7DED5",
}

BRANCH_COLORS = [
    COLORS["blue"],
    COLORS["orange"],
    COLORS["green"],
    COLORS["purple"],
    COLORS["red"],
]


def load_evidence() -> dict:
    with EVIDENCE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "axes.edgecolor": "#6B7280",
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": "#D8DCE2",
            "grid.linewidth": 0.7,
            "grid.alpha": 0.75,
            "legend.frameon": False,
            "legend.fontsize": 9,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.dpi": 180,
        }
    )


def add_title(fig: plt.Figure, title: str, subtitle: str | None = None) -> None:
    fig.suptitle(title, x=0.055, y=0.985, ha="left", va="top", fontsize=16, fontweight="bold")
    if subtitle:
        fig.text(0.055, 0.945, subtitle, ha="left", va="top", fontsize=10, color="#4B5563")


def add_source_note(fig: plt.Figure, text: str) -> None:
    fig.text(0.055, 0.012, text, ha="left", va="bottom", fontsize=7.5, color="#5F6368")


def finish(fig: plt.Figure, name: str, *, top: float = 0.89, bottom: float = 0.075) -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="This figure includes Axes that are not compatible with tight_layout",
        )
        fig.tight_layout(rect=(0.03, bottom, 0.99, top))
    fig.savefig(HERE / name, bbox_inches="tight")
    plt.close(fig)


def arrays(rows: list[list[float]]) -> tuple[np.ndarray, ...]:
    matrix = np.asarray(rows, dtype=float)
    return tuple(matrix[:, index] for index in range(matrix.shape[1]))


def draw_box(
    ax: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    lines: list[str],
    facecolor: str,
) -> None:
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        linewidth=1.0,
        edgecolor="#6B7280",
        facecolor=facecolor,
    )
    ax.add_patch(box)
    ax.text(
        x + 0.025 * width,
        y + 0.72 * height,
        title,
        ha="left",
        va="center",
        fontsize=10,
        fontweight="bold",
    )
    ax.text(
        x + 0.025 * width,
        y + 0.36 * height,
        "\n".join(lines),
        ha="left",
        va="center",
        fontsize=8.2,
        color="#374151",
        linespacing=1.25,
    )


def connect(
    ax: plt.Axes, start: tuple[float, float], end: tuple[float, float], color: str = "#6B7280"
) -> None:
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=11,
        linewidth=1.2,
        color=color,
        connectionstyle="arc3,rad=0",
    )
    ax.add_patch(arrow)


def figure_analysis_flow(data: dict) -> None:
    counts = data["glrt"]["counts"]
    snapshot = data["tle"]["snapshot"]
    method = data["tle"]["method"]
    fig, ax = plt.subplots(figsize=(14, 7.2))
    add_title(
        fig,
        "Analysis design: radio evidence first, causal orbital comparison second",
        "Every shape claim has an explicit observable, validation design, and interpretation boundary.",
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    y_radio = 0.61
    y_tle = 0.20
    w, h = 0.17, 0.20
    xs = [0.02, 0.22, 0.42, 0.62, 0.82]
    draw_box(
        ax,
        xs[0],
        y_radio,
        w,
        h,
        "Continuous IQ interval",
        ["19f2 / stream-1 / RX1", "2.5 MS/s; [0, 30 s)", "0 missing samples or gaps"],
        COLORS["pale_blue"],
    )
    draw_box(
        ax,
        xs[1],
        y_radio,
        w,
        h,
        "20 ms GLRT CFO",
        [
            f"{counts['glrt_independent_windows']:,} windows",
            f"{counts['glrt_margin_pass_windows']:,} margin pass",
            "five selected-alias branches",
        ],
        COLORS["pale_blue"],
    )
    draw_box(
        ax,
        xs[2],
        y_radio,
        w,
        h,
        "Join and deduplicate",
        [
            f"{counts['glrt_branch_member_unique_windows']:,} unique observations",
            "median in branch overlaps",
            "hardware sample time",
        ],
        COLORS["pale_blue"],
    )
    draw_box(
        ax,
        xs[3],
        y_radio,
        w,
        h,
        "Robust model comparison",
        ["Huber degrees 1–5", "1 s blocked CV", "6 s blocked stress test"],
        COLORS["pale_green"],
    )
    draw_box(
        ax,
        xs[4],
        y_radio,
        w - 0.01,
        h,
        "Radio conclusion",
        ["cubic is minimum adequate", "rate changes across dwell", "frame CFO is a cross-check"],
        COLORS["pale_green"],
    )
    for left, right in zip(xs[:-1], xs[1:]):
        connect(ax, (left + w, y_radio + h / 2), (right - 0.008, y_radio + h / 2))

    draw_box(
        ax,
        xs[0],
        y_tle,
        w,
        h,
        "Causal TLE snapshot",
        [
            snapshot["collected_utc"].replace("T", " ")[:19] + "Z",
            f"{snapshot['object_count']:,} element-set records",
            "collected before sample zero",
        ],
        COLORS["pale_orange"],
    )
    draw_box(
        ax,
        xs[1],
        y_tle,
        w,
        h,
        "Visibility screen",
        [
            "SGP4 at assumed site",
            "≥10° for ≥95% of epochs",
            f"{data['tle']['candidate_count']} eligible candidates",
        ],
        COLORS["pale_orange"],
    )
    draw_box(
        ax,
        xs[2],
        y_tle,
        w,
        h,
        "Train-only alignment",
        [
            "offset + bounded drift",
            "epoch sensitivity ±0.30 s",
            f"through t={method['training_end_s']:.3f} s",
        ],
        COLORS["pale_orange"],
    )
    draw_box(
        ax,
        xs[3],
        y_tle,
        w,
        h,
        "Out-of-fit tail",
        [
            "352 observations",
            f"from t={method['holdout_start_s']:.3f} s",
            "excluded from rank and fit",
        ],
        COLORS["pale_red"],
    )
    draw_box(
        ax,
        xs[4],
        y_tle,
        w - 0.01,
        h,
        "Interpretation",
        ["67930 shape-compatible", "better tail forecast", "not a secure identity"],
        COLORS["pale_red"],
    )
    for left, right in zip(xs[:-1], xs[1:]):
        connect(ax, (left + w, y_tle + h / 2), (right - 0.008, y_tle + h / 2))

    ax.text(
        0.01,
        0.715,
        "RADIO PATH",
        rotation=90,
        va="center",
        ha="center",
        fontsize=8,
        color=COLORS["blue"],
        fontweight="bold",
    )
    ax.text(
        0.01,
        0.305,
        "TLE PATH",
        rotation=90,
        va="center",
        ha="center",
        fontsize=8,
        color=COLORS["orange"],
        fontweight="bold",
    )
    add_source_note(
        fig,
        "Validation distinction: 1 s CV is mostly local interpolation (edge folds extrapolate); "
        "the retrospective out-of-fit tail tests forward extrapolation.",
    )
    finish(fig, "01_analysis_flow.png", top=0.88, bottom=0.06)


def figure_measurement_overview(data: dict) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True, gridspec_kw={"hspace": 0.10})
    add_title(
        fig,
        "The same 104 kHz sweep seen at two measurement scales",
        "GLRT gives the high-precision trajectory; source-conditioned single-frame fits supply a noisier diagnostic cross-check.",
    )
    ax = axes[0]
    branch_models = {item["id"]: item for item in data["glrt"]["branch_models"]}
    for index, (branch, points) in enumerate(data["glrt"]["branch_observations"].items()):
        t, f = arrays(points)
        mask = (t >= 0) & (t < 30)
        color = BRANCH_COLORS[index]
        ax.scatter(
            t[mask], f[mask] / 1000, s=9, alpha=0.62, color=color, linewidths=0, label=branch
        )
        model = branch_models[branch]
        grid = np.linspace(max(0, model["start_s"]), min(30, model["end_s"]), 80)
        coeff = model["coefficients_hz"]
        pred = coeff[0] * (grid - model["reference_time_s"]) + coeff[1]
        ax.plot(grid, pred / 1000, color=color, linewidth=1.4)
    grid = np.asarray(data["fits"]["grid_times_s"])
    cubic = np.asarray(data["fits"]["fits_hz"]["3"])
    ax.plot(grid, cubic / 1000, color=COLORS["black"], linewidth=2.4, label="robust cubic")
    ax.set_ylabel("selected-alias CFO (kHz)")
    ax.set_title("A. 20 ms GLRT observations and branch-local fits", loc="left")
    ax.legend(ncol=6, loc="upper right")

    ax = axes[1]
    t, median, q10, q90, support = arrays(data["single_frame_cfo"]["frame_bins"])
    take = np.arange(t.size) % 3 == 0
    ax.vlines(
        t[take], q10[take] / 1000, q90[take] / 1000, color=COLORS["sky"], alpha=0.18, linewidth=0.7
    )
    scatter = ax.scatter(
        t,
        median / 1000,
        c=np.clip(support, 1, 25),
        cmap="Blues",
        s=11,
        alpha=0.70,
        linewidths=0,
        label="50 ms median frame CFO",
    )
    global_grid = data["fits"]["global_grid"]
    gt = np.asarray(global_grid["times_s"])
    ax.plot(
        gt,
        np.asarray(global_grid["glrt_cubic_cfo_hz"]) / 1000,
        color=COLORS["black"],
        linewidth=2.3,
        label="GLRT cubic",
    )
    ax.plot(
        gt,
        np.asarray(global_grid["frame_cubic_cfo_hz"]) / 1000,
        color=COLORS["red"],
        linewidth=1.7,
        linestyle="--",
        label="frame cubic",
    )
    cbar = fig.colorbar(scatter, ax=ax, pad=0.012, fraction=0.028)
    cbar.set_label("frames per 50 ms bin")
    ax.set_title("B. Single-frame fitted CFO, summarized in 50 ms bins", loc="left")
    ax.set_xlabel("time from stream-1 first sample (s)")
    ax.set_ylabel("receiver-relative CFO (kHz)")
    ax.legend(ncol=3, loc="upper right")
    ax.set_xlim(0, 30)
    add_source_note(
        fig,
        "Whiskers are 10th–90th percentiles (every third bin shown for legibility). Frame estimates use source-model derotation and 64 known pilot symbols.",
    )
    finish(fig, "02_measurement_overview.png", top=0.89, bottom=0.08)


def figure_fit_residuals(data: dict) -> None:
    fig = plt.figure(figsize=(14, 12))
    grid_spec = fig.add_gridspec(4, 1, height_ratios=[1.25, 0.75, 0.75, 0.75], hspace=0.28)
    axes = [fig.add_subplot(grid_spec[index, 0]) for index in range(4)]
    add_title(
        fig,
        "Residual structure separates linear, quadratic, and cubic models",
        "Residual = observed GLRT CFO − fitted CFO. Trend ribbons summarize 500 ms bins.",
    )
    observations = np.asarray(data["fits"]["observations"], dtype=float)
    t = observations[:, 0]
    y = observations[:, 1]
    grid = np.asarray(data["fits"]["grid_times_s"])
    colors = {"1": COLORS["blue"], "2": COLORS["orange"], "3": COLORS["green"]}
    labels = {"1": "linear", "2": "quadratic", "3": "cubic"}
    ax = axes[0]
    ax.scatter(t, y / 1000, s=7, color="#A0A5AD", alpha=0.5, linewidths=0, label="GLRT")
    for key in ("1", "2", "3"):
        ax.plot(
            grid,
            np.asarray(data["fits"]["fits_hz"][key]) / 1000,
            color=colors[key],
            linewidth=2.0,
            label=labels[key],
        )
    ax.set_ylabel("CFO (kHz)")
    ax.set_title("A. All fits appear plausible on the full 104 kHz sweep", loc="left")
    ax.legend(ncol=4, loc="upper right")
    ax.set_xlim(0, 30)
    ax.tick_params(labelbottom=False)

    for panel, key in enumerate(("1", "2", "3"), start=1):
        ax = axes[panel]
        residual_t, residual = arrays(data["fits"]["residuals_hz"][key])
        ax.scatter(residual_t, residual, s=6, color=colors[key], alpha=0.22, linewidths=0)
        trend_t, trend_median, trend_q10, trend_q90 = arrays(
            data["fits"]["residual_trend_500ms_hz"][key]
        )
        ax.fill_between(trend_t, trend_q10, trend_q90, color=colors[key], alpha=0.16, linewidth=0)
        ax.plot(trend_t, trend_median, color=colors[key], linewidth=1.8)
        ax.axhline(0, color=COLORS["black"], linewidth=0.8)
        metrics = data["fits"]["robust_models"][key]["fit"]
        title_letter = chr(ord("A") + panel)
        ax.set_title(
            f"{title_letter}. {labels[key].capitalize()} residuals — RMS {metrics['rms_hz']:.1f} Hz; adjacent-observation correlation {metrics['adjacent_correlation']:.3f}",
            loc="left",
        )
        ax.set_ylabel("residual (Hz)")
        full_range = np.max(np.abs(residual))
        ax.set_ylim(-max(100, full_range * 1.08), max(100, full_range * 1.08))
        ax.set_xlim(0, 30)
        if panel < 3:
            ax.tick_params(labelbottom=False)
    axes[-1].set_xlabel("time from first sample (s)")
    add_source_note(
        fig,
        "The changing vertical scale is stated by each axis: it exposes slow model error that the full CFO scale hides.",
    )
    finish(fig, "03_polynomial_fits_and_residuals.png", top=0.91, bottom=0.06)


def figure_residual_distributions(data: dict) -> None:
    fig, axes = plt.subplots(
        1, 3, figsize=(15, 5.5), gridspec_kw={"width_ratios": [1.35, 1.0, 0.9]}
    )
    add_title(
        fig,
        "Cubic improvement is visible in magnitude, validation, and time structure",
        "The three panels answer different questions; together they show that the gain is not an isolated-point artifact.",
    )
    colors = {"1": COLORS["blue"], "2": COLORS["orange"], "3": COLORS["green"]}
    labels = {"1": "linear", "2": "quadratic", "3": "cubic"}

    ax = axes[0]
    for key in ("1", "2", "3"):
        _, signed_residual = arrays(data["fits"]["residuals_hz"][key])
        residual = np.abs(signed_residual)
        ordered = np.sort(residual)
        cdf = np.arange(1, ordered.size + 1) / ordered.size
        ax.plot(np.maximum(ordered, 0.5), cdf, color=colors[key], linewidth=2, label=labels[key])
    ax.set_xscale("log")
    ax.set_xlim(1, 5000)
    ax.set_ylim(0, 1.01)
    ax.set_xlabel("absolute in-sample residual (Hz, log scale)")
    ax.set_ylabel("empirical cumulative probability")
    ax.set_title("A. Absolute-residual distributions", loc="left")
    ax.legend(loc="lower right")

    ax = axes[1]
    x = np.arange(3)
    fit_rms = [data["fits"]["robust_models"][key]["fit"]["rms_hz"] for key in ("1", "2", "3")]
    cv_rms = [data["fits"]["robust_models"][key]["cv_1s"]["rms_hz"] for key in ("1", "2", "3")]
    width = 0.35
    bars_fit = ax.bar(x - width / 2, fit_rms, width, color=COLORS["sky"], label="in-sample")
    bars_cv = ax.bar(x + width / 2, cv_rms, width, color=COLORS["red"], label="leave-1-s-block-out")
    ax.set_yscale("log")
    ax.set_xticks(x, ["linear", "quadratic", "cubic"])
    ax.set_ylabel("RMS residual (Hz, log scale)")
    ax.set_title("B. Fit versus blocked CV", loc="left")
    ax.legend(loc="upper right")
    for bar in [*bars_fit, *bars_cv]:
        value = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value * 1.08,
            f"{value:.1f}",
            ha="center",
            va="bottom",
            fontsize=8,
            rotation=90,
        )
    ax.set_ylim(40, 2500)

    ax = axes[2]
    corr = [
        data["fits"]["robust_models"][key]["fit"]["adjacent_correlation"] for key in ("1", "2", "3")
    ]
    bars = ax.bar(x, corr, color=[colors[key] for key in ("1", "2", "3")], width=0.62)
    ax.set_xticks(x, ["linear", "quadratic", "cubic"])
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("adjacent-observation residual correlation")
    ax.set_title("C. Remaining time structure", loc="left")
    for bar, value in zip(bars, corr):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.025,
            f"{value:.3f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    add_source_note(
        fig,
        "Blocked CV leaves out each floor(t)-second block in turn; it is an interpolation test, not a 12–14 s forward forecast.",
    )
    finish(fig, "04_residual_distributions.png", top=0.85, bottom=0.12)


def figure_model_complexity(data: dict) -> None:
    rows = data["fits"]["complexity"]
    degree = np.asarray([item["degree"] for item in rows])
    fit = np.asarray([item["fit_rms_hz"] for item in rows])
    cv1 = np.asarray([item["cv_1s_rms_hz"] for item in rows])
    cv6 = np.asarray([item["cv_6s_rms_hz"] for item in rows])
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.8), gridspec_kw={"width_ratios": [1.55, 1.0]})
    add_title(
        fig,
        "Model complexity has a clear elbow at degree 3",
        "Quartic buys a tiny local-CV improvement, then loses on longer contiguous holdouts; degree 5 is unstable.",
    )
    ax = axes[0]
    series = [
        (fit, "in-sample", COLORS["blue"], "o", -11, -14),
        (cv1, "leave-1-s-block-out", COLORS["green"], "s", 12, 6),
        (cv6, "leave-6-s-block-out", COLORS["red"], "^", 0, 7),
    ]
    for values, label, color, marker, dx, dy in series:
        ax.plot(degree, values, color=color, marker=marker, linewidth=2, markersize=6, label=label)
        for x, y in zip(degree, values):
            ax.annotate(
                f"{y:.1f}",
                (x, y),
                xytext=(dx, dy),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                color=color,
            )
    ax.set_yscale("log")
    ax.set_xticks(degree)
    ax.set_xlabel("polynomial degree")
    ax.set_ylabel("RMS residual (Hz, log scale)")
    ax.set_title("A. Generalization across block lengths", loc="left")
    ax.legend(loc="upper right")
    ax.axvspan(2.82, 3.18, color=COLORS["pale_green"], alpha=0.55, zorder=0)

    ax = axes[1]
    subset = degree >= 3
    width = 0.24
    xs = np.arange(3)
    bars1 = ax.bar(xs - width, fit[subset], width, color=COLORS["blue"], label="fit")
    bars2 = ax.bar(xs, cv1[subset], width, color=COLORS["green"], label="1 s CV")
    bars3 = ax.bar(xs + width, cv6[subset], width, color=COLORS["red"], label="6 s CV")
    ax.set_xticks(xs, ["cubic", "quartic", "quintic"])
    ax.set_ylabel("RMS residual (Hz)")
    ax.set_ylim(0, 235)
    ax.set_title("B. The high-degree trade-off", loc="left")
    ax.legend(loc="upper left", ncol=3)
    for bars in (bars1, bars2, bars3):
        for bar in bars:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 5,
                f"{bar.get_height():.1f}",
                ha="center",
                va="bottom",
                fontsize=8,
                rotation=90,
            )
    ax.annotate(
        "minimum adequate\nand stable model",
        xy=(0, cv6[2]),
        xytext=(0.45, 178),
        arrowprops={"arrowstyle": "->", "color": COLORS["black"]},
        ha="center",
        fontsize=9,
    )
    add_source_note(
        fig,
        "Degree 4 reduces 1 s CV by only 1.37 Hz versus cubic, while its 6 s CV is 5.41 Hz worse; degree 5 reaches 211.65 Hz on 6 s blocks.",
    )
    finish(fig, "05_model_complexity.png", top=0.84, bottom=0.12)


def figure_rate_acceleration(data: dict) -> None:
    comparison = data["fits"]["global_rate_comparison"]
    boot = data["fits"]["global_block_bootstrap"]["glrt_cubic"]
    t = np.asarray(comparison["times_s"])
    bt = np.asarray(boot["evaluation_times_s"])
    fig, axes = plt.subplots(2, 1, figsize=(13.5, 8.4), sharex=True)
    add_title(
        fig,
        "The cubic implies a steadily changing received-CFO rate",
        "Bands are 95% intervals from 500 one-second block-bootstrap refits; frame-derived curves are diagnostic.",
    )
    ax = axes[0]
    ax.fill_between(
        bt,
        np.asarray(boot["rate_hz_s_p025"]) / 1000,
        np.asarray(boot["rate_hz_s_p975"]) / 1000,
        color=COLORS["green"],
        alpha=0.18,
        label="GLRT cubic 95% block bootstrap",
    )
    ax.plot(
        t,
        np.asarray(comparison["glrt_cubic_hz_s"]) / 1000,
        color=COLORS["green"],
        marker="o",
        linewidth=2.3,
        label="GLRT cubic",
    )
    ax.plot(
        t,
        np.asarray(comparison["glrt_quadratic_hz_s"]) / 1000,
        color=COLORS["orange"],
        marker="s",
        linewidth=1.8,
        label="GLRT quadratic",
    )
    ax.plot(
        t,
        np.asarray(comparison["frame_cubic_hz_s"]) / 1000,
        color=COLORS["red"],
        marker="^",
        linewidth=1.5,
        linestyle="--",
        label="frame cubic (diagnostic)",
    )
    ax.set_ylabel("CFO rate (kHz/s)")
    ax.set_title("A. First derivative", loc="left")
    ax.legend(ncol=2, loc="upper left")

    ax = axes[1]
    ax.fill_between(
        bt,
        np.asarray(boot["acceleration_hz_s2_p025"]),
        np.asarray(boot["acceleration_hz_s2_p975"]),
        color=COLORS["green"],
        alpha=0.18,
    )
    ax.plot(
        t,
        np.asarray(comparison["glrt_cubic_acceleration_hz_s2"]),
        color=COLORS["green"],
        marker="o",
        linewidth=2.3,
        label="GLRT cubic",
    )
    ax.plot(
        t,
        np.asarray(comparison["glrt_quadratic_acceleration_hz_s2"]),
        color=COLORS["orange"],
        marker="s",
        linewidth=1.8,
        label="GLRT quadratic (constant)",
    )
    ax.plot(
        t,
        np.asarray(comparison["frame_cubic_acceleration_hz_s2"]),
        color=COLORS["red"],
        marker="^",
        linewidth=1.5,
        linestyle="--",
        label="frame cubic (diagnostic)",
    )
    ax.axhline(0, color=COLORS["black"], linewidth=0.8)
    ax.set_ylabel("rate change (Hz/s²)")
    ax.set_xlabel("time from first sample (s)")
    ax.set_title("B. Second derivative", loc="left")
    ax.legend(ncol=3, loc="upper left")
    ax.set_xlim(0, 30)
    add_source_note(
        fig,
        "These are derivatives of receiver-relative CFO, not isolated orbital acceleration; transmitter, LNB, receiver, and propagation dynamics remain in the observable.",
    )
    finish(fig, "06_rate_and_acceleration.png", top=0.87, bottom=0.09)


def figure_branch_local_rates(data: dict) -> None:
    branch = data["glrt"]["branch_metrics"]
    raw = data["raw_dwell_rate"]["branches"]
    names = [item["branch"] for item in branch]
    x = np.arange(len(names))
    fig, axes = plt.subplots(2, 1, figsize=(13.5, 8.5), sharex=True, gridspec_kw={"hspace": 0.12})
    add_title(
        fig,
        "Branch-local checks agree on broad rate, but not on one precise 30 s acceleration",
        "The long-baseline GLRT curve is precise; frame and reset-debiased local estimators have much broader uncertainty.",
    )
    ax = axes[0]
    glrt = np.asarray([item["glrt_rate_hz_s"] for item in branch]) / 1000
    frame = np.asarray([item["frame_huber_rate_hz_s"] for item in branch]) / 1000
    lo = np.asarray([item["frame_huber_rate_bootstrap_p025_hz_s"] for item in branch]) / 1000
    hi = np.asarray([item["frame_huber_rate_bootstrap_p975_hz_s"] for item in branch]) / 1000
    ax.plot(
        x,
        glrt,
        color=COLORS["blue"],
        marker="D",
        linewidth=1.8,
        markersize=6,
        label="branch GLRT slope",
    )
    ax.errorbar(
        x,
        frame,
        yerr=np.vstack([frame - lo, hi - frame]),
        fmt="o",
        color=COLORS["red"],
        ecolor=COLORS["red"],
        capsize=4,
        linewidth=1.3,
        label="frame Huber slope, 95% bootstrap",
    )
    for i, item in enumerate(branch):
        ax.text(
            i,
            max(glrt[i], frame[i]) + 0.08,
            f"Δ {item['frame_minus_glrt_hz_s']:+.1f} Hz/s",
            ha="center",
            fontsize=8,
        )
    ax.set_ylabel("CFO rate (kHz/s)")
    ax.set_title("A. Frozen branch slope versus source-conditioned frame fit", loc="left")
    ax.legend(ncol=2, loc="lower right")

    ax = axes[1]
    raw_glrt = np.asarray([item["glrt_rate_hz_s"] for item in raw]) / 1000
    local = np.asarray(
        [
            np.nan if item["local_rate_hz_s"] is None else item["local_rate_hz_s"] / 1000
            for item in raw
        ]
    )
    local_lo = np.asarray(
        [
            np.nan if item["local_p025_hz_s"] is None else item["local_p025_hz_s"] / 1000
            for item in raw
        ]
    )
    local_hi = np.asarray(
        [
            np.nan if item["local_p975_hz_s"] is None else item["local_p975_hz_s"] / 1000
            for item in raw
        ]
    )
    valid = np.isfinite(local)
    ax.plot(
        x,
        raw_glrt,
        color=COLORS["blue"],
        marker="D",
        linewidth=1.8,
        markersize=6,
        label="branch GLRT slope",
    )
    ax.errorbar(
        x[valid],
        local[valid],
        yerr=np.vstack([local[valid] - local_lo[valid], local_hi[valid] - local[valid]]),
        fmt="o",
        color=COLORS["green"],
        ecolor=COLORS["green"],
        capsize=5,
        linewidth=1.5,
        label="reset-debiased local rate, cluster 95% CI",
    )
    ax.set_ylim(-4.55, -2.55)
    for i, item in enumerate(raw):
        if item["local_rate_hz_s"] is not None:
            ax.text(i, -4.47, f"{item['ramp_count']} ramps", ha="center", va="bottom", fontsize=8)
        else:
            ax.text(
                i,
                raw_glrt[i] + 0.10,
                "2 ramps\ninsufficient",
                ha="center",
                va="bottom",
                fontsize=8,
                color=COLORS["red"],
            )
    ax.set_ylabel("CFO rate (kHz/s)")
    ax.set_title("B. Separate source-bound raw-dwell ramp cross-check", loc="left")
    ax.set_xticks(x, names)
    ax.set_xlabel("selected GLRT branch")
    ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(0.63, 1.01))
    add_source_note(
        fig,
        "Only 3bf1f4b5 preferred within-branch rate progression by BIC (ΔBIC = −11.1); the fifth branch had only two ramps. Four complete local rates passed held-out gates.",
    )
    finish(fig, "07_branch_local_rates.png", top=0.87, bottom=0.10)


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def figure_tle_provenance(data: dict) -> None:
    capture_ns = data["capture"]["first_sample_estimate_utc_ns"]
    capture = datetime.fromtimestamp(capture_ns / 1e9, tz=UTC)
    snapshot = parse_utc(data["tle"]["snapshot"]["collected_utc"])
    newest = parse_utc(data["tle"]["snapshot"]["newest_element_epoch_utc"])
    best = parse_utc(data["tle"]["top_candidates"][0]["element_epoch_utc"])
    events = [
        (best, "67930 element epoch", COLORS["orange"], -0.38),
        (newest, "newest element in snapshot", COLORS["purple"], 0.38),
        (snapshot, "snapshot collected", COLORS["blue"], -0.38),
        (capture, "stream-1 sample zero", COLORS["red"], 0.38),
    ]
    fig, axes = plt.subplots(
        2, 1, figsize=(14, 7.4), gridspec_kw={"height_ratios": [1.2, 0.8], "hspace": 0.40}
    )
    add_title(
        fig,
        "The orbital comparison is strictly causal, but the top-ranked candidate's element is almost 10 hours old",
        "Snapshot collection time and individual element epoch are distinct provenance dates.",
    )
    ax = axes[0]
    ax.axhline(0, color="#9CA3AF", linewidth=1.4)
    for dt, label, color, y in events:
        ax.scatter(dt, 0, s=70, color=color, zorder=3)
        ax.vlines(dt, 0, y * 0.72, color=color, linewidth=1.2)
        ax.text(
            dt, y, f"{label}\n{dt:%H:%M:%S}Z", ha="center", va="center", fontsize=9, color=color
        )
    ax.set_ylim(-0.60, 0.60)
    ax.set_yticks([])
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=UTC))
    ax.set_xlabel("UTC on 2026-08-24")
    ax.set_title("A. Causal catalogue and element timeline", loc="left")
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)

    ax = axes[1]
    train_end = data["tle"]["method"]["training_end_s"]
    hold_start = data["tle"]["method"]["holdout_start_s"]
    ax.barh(
        [0], [train_end], left=[0], color=COLORS["pale_blue"], edgecolor=COLORS["blue"], height=0.48
    )
    ax.barh(
        [0],
        [30 - hold_start],
        left=[hold_start],
        color=COLORS["pale_red"],
        edgecolor=COLORS["red"],
        height=0.48,
    )
    ax.axvspan(train_end, hold_start, color="#E5E7EB", alpha=0.8)
    ax.text(
        train_end / 2,
        0,
        "TRAIN\n529 observations\nthrough 16.400 s",
        ha="center",
        va="center",
        fontsize=10,
        color=COLORS["blue"],
    )
    ax.text(
        (hold_start + 30) / 2,
        0,
        "RETROSPECTIVE OUT-OF-FIT TAIL\n352 observations\nfrom 16.425 s",
        ha="center",
        va="center",
        fontsize=10,
        color=COLORS["red"],
    )
    ax.set_xlim(0, 30)
    ax.set_ylim(-0.55, 0.55)
    ax.set_yticks([])
    ax.set_xlabel("time from first sample (s)")
    ax.set_title(
        "B. Chronological validation split (by observation count, not elapsed duration)", loc="left"
    )
    add_source_note(
        fig,
        "Snapshot age at sample zero: 78 min 47.953 s. STARLINK-36865 element age: 9 h 55 min 41.627 s. Observer is a reviewed Sausalito preset, not capture-bound GPS.",
    )
    finish(fig, "08_tle_provenance_and_split.png", top=0.86, bottom=0.09)


def figure_tle_candidates(data: dict) -> None:
    candidates = data["tle"]["top_candidates"]
    ranks = np.asarray([item["rank"] for item in candidates])
    labels = [f"{item['rank']}. {item['catalog_number']}" for item in candidates]
    train = np.asarray([item["constrained"]["train_rms_hz"] for item in candidates])
    hold = np.asarray([item["constrained"]["holdout_rms_hz"] for item in candidates])
    y = np.arange(len(candidates))
    fig, axes = plt.subplots(1, 2, figsize=(14, 7.2), gridspec_kw={"width_ratios": [1.2, 1.0]})
    add_title(
        fig,
        "STARLINK-36865 / NORAD 67930 is the strongest causal shape candidate",
        "Candidates were ranked only on training RMS; tail values were excluded from ranking and nuisance fitting.",
    )
    ax = axes[0]
    for index in range(len(candidates)):
        color = COLORS["green"] if index == 0 else (COLORS["orange"] if index == 1 else "#9CA3AF")
        ax.plot([train[index], hold[index]], [y[index], y[index]], color="#D1D5DB", linewidth=1.2)
        ax.scatter(train[index], y[index], marker="o", color=color, s=45, zorder=3)
        ax.scatter(
            hold[index],
            y[index],
            marker="s",
            facecolor="white",
            edgecolor=color,
            linewidth=1.5,
            s=48,
            zorder=3,
        )
    ax.set_xscale("log")
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("RMS error (Hz, log scale)")
    ax.set_ylabel("training rank · NORAD catalog number")
    ax.set_title("A. Top 10 of 184 visibility-qualified candidates", loc="left")
    ax.axvline(
        data["tle"]["radio_polynomial_nulls_train_only"]["cubic"]["holdout_rms_hz"],
        color=COLORS["red"],
        linestyle="--",
        linewidth=1.2,
        label="train-only cubic tail",
    )
    ax.scatter([], [], marker="o", color="#6B7280", s=45, label="training RMS")
    ax.scatter(
        [],
        [],
        marker="s",
        facecolor="white",
        edgecolor="#6B7280",
        linewidth=1.5,
        s=48,
        label="holdout RMS",
    )
    handles, legend_labels = ax.get_legend_handles_labels()
    order = [1, 2, 0]
    ax.legend(
        [handles[index] for index in order],
        [legend_labels[index] for index in order],
        loc="upper right",
    )

    ax = axes[1]
    colors = [
        COLORS["green"] if rank == 1 else (COLORS["orange"] if rank == 2 else "#9CA3AF")
        for rank in ranks
    ]
    ax.scatter(train, hold, c=colors, s=58, alpha=0.9)
    for rank, tx, hy in zip(ranks, train, hold):
        ax.annotate(str(rank), (tx, hy), xytext=(5, 4), textcoords="offset points", fontsize=8)
    bound = max(np.max(train), np.max(hold)) * 1.25
    low = min(np.min(train), np.min(hold)) / 1.35
    ax.plot([low, bound], [low, bound], color="#9CA3AF", linestyle=":", linewidth=1.0)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(low, bound)
    ax.set_ylim(low, bound)
    ax.set_xlabel("training RMS (Hz)")
    ax.set_ylabel("chronological out-of-fit-tail RMS (Hz)")
    ax.set_title("B. Training fit does not guarantee tail prediction", loc="left")
    ax.annotate(
        "67930",
        (train[0], hold[0]),
        xytext=(18, -4),
        textcoords="offset points",
        color=COLORS["green"],
        fontweight="bold",
    )
    ax.annotate(
        "59523",
        (train[1], hold[1]),
        xytext=(18, 3),
        textcoords="offset points",
        color=COLORS["orange"],
    )
    add_source_note(
        fig,
        "The best-versus-runner training margin is only 23.86 Hz. Ranking among 184 candidates has no calibrated false-association rate, so this is not an identity claim.",
    )
    finish(fig, "09_tle_candidate_ranking.png", top=0.86, bottom=0.09)


def shade_holdout(ax: plt.Axes, start: float) -> None:
    ax.axvspan(start, 30, color=COLORS["pale_red"], alpha=0.42, zorder=0)
    ax.axvline(start, color=COLORS["red"], linewidth=0.9, linestyle=":")


def figure_tle_alignment(data: dict) -> None:
    plot = data["tle"]["plot"]
    t = np.asarray(plot["time_s"])
    cubic_cfo = np.asarray(plot["cubic_cfo_hz"])
    cubic_rate = np.asarray(plot["cubic_rate_hz_s"])
    cubic_acc = np.asarray(plot["cubic_acceleration_hz_s2"])
    exact = plot["exact_utc"]
    constrained = plot["constrained"]
    holdout_start = data["tle"]["method"]["holdout_start_s"]
    smooth_holdout = t >= holdout_start
    exact_grid_tail_rms = float(
        np.sqrt(np.mean(np.square(np.asarray(exact["residual_hz"])[smooth_holdout])))
    )
    constrained_grid_tail_rms = float(
        np.sqrt(np.mean(np.square(np.asarray(constrained["residual_hz"])[smooth_holdout])))
    )
    fig, axes = plt.subplots(
        4,
        1,
        figsize=(14, 11.2),
        sharex=True,
        gridspec_kw={"height_ratios": [1.05, 0.8, 0.8, 0.8], "hspace": 0.12},
    )
    add_title(
        fig,
        "Causal TLE geometry tracks the cubic shape and forecasts the out-of-fit tail",
        "Both TLE curves use training-only offset and bounded drift; exact UTC fixes δ=0, while constrained sensitivity searches δ∈[−0.30,+0.30] s.",
    )
    for ax in axes:
        shade_holdout(ax, holdout_start)

    ax = axes[0]
    ax.plot(t, cubic_cfo / 1000, color=COLORS["black"], linewidth=2.4, label="robust cubic")
    ax.plot(
        t,
        np.asarray(exact["aligned_cfo_hz"]) / 1000,
        color=COLORS["blue"],
        linewidth=1.5,
        linestyle="--",
        label="67930 exact UTC",
    )
    ax.plot(
        t,
        np.asarray(constrained["aligned_cfo_hz"]) / 1000,
        color=COLORS["green"],
        linewidth=1.8,
        label="67930 constrained δ=−0.30 s",
    )
    ax.set_ylabel("CFO (kHz)")
    ax.set_title("A. Aligned CFO shape", loc="left")
    ax.legend(ncol=3, loc="upper right")

    ax = axes[1]
    ax.plot(
        t,
        np.asarray(exact["residual_hz"]),
        color=COLORS["blue"],
        linewidth=1.4,
        linestyle="--",
        label=f"exact UTC; smooth-grid tail RMS {exact_grid_tail_rms:.1f} Hz",
    )
    ax.plot(
        t,
        np.asarray(constrained["residual_hz"]),
        color=COLORS["green"],
        linewidth=1.6,
        label=f"constrained; smooth-grid tail RMS {constrained_grid_tail_rms:.1f} Hz",
    )
    ax.axhline(0, color=COLORS["black"], linewidth=0.8)
    ax.set_ylabel("cubic − TLE (Hz)")
    ax.set_title("B. Shape residual", loc="left")
    ax.legend(ncol=2, loc="lower left")

    ax = axes[2]
    ax.plot(t, cubic_rate / 1000, color=COLORS["black"], linewidth=2.3, label="robust cubic")
    ax.plot(
        t,
        np.asarray(exact["aligned_rate_hz_s"]) / 1000,
        color=COLORS["blue"],
        linewidth=1.4,
        linestyle="--",
        label="67930 exact UTC",
    )
    ax.plot(
        t,
        np.asarray(constrained["aligned_rate_hz_s"]) / 1000,
        color=COLORS["green"],
        linewidth=1.7,
        label="67930 constrained",
    )
    ax.set_ylabel("CFO rate (kHz/s)")
    ax.set_title("C. First derivative", loc="left")

    ax = axes[3]
    ax.plot(t, cubic_acc, color=COLORS["black"], linewidth=2.3, label="robust cubic")
    ax.plot(
        t,
        np.asarray(exact["acceleration_hz_s2"]),
        color=COLORS["blue"],
        linewidth=1.4,
        linestyle="--",
        label="67930 exact UTC",
    )
    ax.plot(
        t,
        np.asarray(constrained["acceleration_hz_s2"]),
        color=COLORS["green"],
        linewidth=1.7,
        label="67930 constrained",
    )
    ax.set_ylabel("rate change (Hz/s²)")
    ax.set_xlabel("time from first sample (s)")
    ax.set_title("D. Second derivative", loc="left")
    ax.set_xlim(0, 30)
    add_source_note(
        fig,
        "Red shading marks the retrospective out-of-fit tail. The constrained δ optimum hits the "
        "−0.30 s bound and is interpreted as TLE/orbital along-track sensitivity, not capture timing.",
    )
    finish(fig, "10_tle_alignment_and_derivatives.png", top=0.91, bottom=0.07)


def figure_validation_controls(data: dict) -> None:
    top = data["tle"]["top_candidates"][0]
    nulls = data["tle"]["radio_polynomial_nulls_train_only"]
    sensitivity = data["tle"]["epoch_sensitivity"]
    names = [
        "wide δ diagnostic\n(post hoc)",
        "TLE constrained\n±0.30 s",
        "TLE exact UTC",
        "TLE ±0.30 s\noffset only, no drift",
        "train-only\nradio cubic",
        "train-only\nradio quadratic",
        "train-only\nradio linear",
    ]
    values = [
        sensitivity["wide_plus_minus_2_s_diagnostic"]["holdout_rms_hz"],
        top["constrained"]["holdout_rms_hz"],
        top["exact_utc"]["holdout_rms_hz"],
        top["constant_offset"]["holdout_rms_hz"],
        nulls["cubic"]["holdout_rms_hz"],
        nulls["quadratic"]["holdout_rms_hz"],
        nulls["linear"]["holdout_rms_hz"],
    ]
    colors = [
        "#B8BCC4",
        COLORS["green"],
        COLORS["blue"],
        COLORS["sky"],
        COLORS["purple"],
        COLORS["orange"],
        COLORS["red"],
    ]
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.6), gridspec_kw={"width_ratios": [1.35, 1.0]})
    add_title(
        fig,
        "Physics-informed TLE geometry extrapolates better than radio-only polynomials",
        "The wide δ result is a labeled sensitivity diagnostic and is excluded from the primary claim.",
    )
    ax = axes[0]
    x = np.arange(len(names))
    bars = ax.bar(x, values, color=colors, width=0.68)
    bars[0].set_hatch("//")
    bars[0].set_edgecolor("#666666")
    ax.set_yscale("log")
    ax.set_xticks(x, names, rotation=18, ha="right")
    ax.set_ylabel("chronological out-of-fit-tail RMS (Hz, log scale)")
    ax.set_title("A. Forward-validation controls", loc="left")
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value * 1.08,
            f"{value:.1f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    ax.set_ylim(60, 5200)

    ax = axes[1]
    variants = [
        ("wide diagnostic", sensitivity["wide_plus_minus_2_s_diagnostic"], COLORS["gray"], "^"),
        ("constrained", sensitivity["constrained_plus_minus_0_30_s"], COLORS["green"], "o"),
        ("exact UTC", sensitivity["exact_utc"], COLORS["blue"], "s"),
    ]
    for label, item, color, marker in variants:
        shift = item["epoch_adjustment_s"]
        ax.scatter(shift, item["train_rms_hz"], color=color, marker=marker, s=60)
        ax.scatter(
            shift,
            item["holdout_rms_hz"],
            facecolor="white",
            edgecolor=color,
            marker=marker,
            linewidth=1.5,
            s=60,
        )
        ax.plot(
            [shift, shift],
            [item["train_rms_hz"], item["holdout_rms_hz"]],
            color=color,
            linewidth=1.0,
        )
        ax.annotate(
            label,
            (shift, item["holdout_rms_hz"]),
            xytext=(4, 5),
            textcoords="offset points",
            fontsize=8,
            color=color,
        )
    ax.axvspan(
        -0.30, 0.30, color=COLORS["pale_green"], alpha=0.42, label="primary bounded ±0.30 s search"
    )
    timing = sensitivity["capture_timing_half_width_s"]
    ax.axvline(-timing, color=COLORS["red"], linewidth=1.1)
    ax.axvline(timing, color=COLORS["red"], linewidth=1.1, label="capture timing ±0.53 ms")
    ax.set_yscale("log")
    ax.set_xlim(-1.08, 0.38)
    ax.set_ylim(50, 310)
    ax.set_xlabel("TLE epoch adjustment δ (s)")
    ax.set_ylabel("RMS (Hz, log scale)")
    ax.set_title("B. Epoch/along-track sensitivity", loc="left")
    ax.scatter([], [], color=COLORS["black"], marker="o", label="training RMS")
    ax.scatter(
        [], [], facecolor="white", edgecolor=COLORS["black"], marker="o", label="holdout RMS"
    )
    ax.legend(loc="upper left", fontsize=8)
    add_source_note(
        fig,
        "The −0.95 s best-candidate wide optimum cannot be a capture-clock correction: manifest timing uncertainty is only ±0.000529741 s.",
    )
    finish(fig, "11_validation_controls_and_sensitivity.png", top=0.85, bottom=0.15)


def main() -> None:
    configure_style()
    data = load_evidence()
    figure_analysis_flow(data)
    figure_measurement_overview(data)
    figure_fit_residuals(data)
    figure_residual_distributions(data)
    figure_model_complexity(data)
    figure_rate_acceleration(data)
    figure_branch_local_rates(data)
    figure_tle_provenance(data)
    figure_tle_candidates(data)
    figure_tle_alignment(data)
    figure_validation_controls(data)
    print("generated 11 report figures")


if __name__ == "__main__":
    main()
