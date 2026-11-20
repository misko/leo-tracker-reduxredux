"""Rebuild the runtime and position figures from the sealed roof evaluations."""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.ticker import NullLocator, PercentFormatter


OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent / "2026_11_19_receiver_screening"
ORIGINAL, COMPACT = "baseline", "v5_secant_fit"
METHODS = (ORIGINAL, COMPACT)
NAMES = {ORIGINAL: "Original algo7v5", COMPACT: "Compact v5"}
COLORS = {ORIGINAL: "#354F78", COMPACT: "#00836B"}
MARKERS = {ORIGINAL: "o", COMPACT: "D"}
INK, MUTED, GRID = "#192F40", "#4D6070", "#DEE5EA"
ARMS = ("c0", "fitted_c")
STAGES = {
    "Prepare tracks and orbits": "native_preparation_s",
    "Initial matches and position fits": "initial_s",
    "Reject suspect tracks and refit": "conservative_s",
    "Fit satellite families": "family_s",
    "Correct orbit timing and refit": "signed_s",
    "Leave one family out and refit": "cavity_s",
    "Late recovery and reassociation": "original_full_late_s",
    "Prepare and render plots": "original_render_s",
    "Other startup, I/O and output": "other_s",
}


def read_csv(path):
    with (SOURCE / path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def number(cell):
    return float(cell) if cell else None


def measured_rows():
    full = read_csv("redesign/roof-selection/comparison/scores.csv")
    benchmark = read_csv("recovery/full-receivers/scores.csv")
    secant = read_csv("secant-full/per-recording.csv")
    timings = read_csv("deployment/same-core-baseline/timings.csv")
    source_method = {"original-baseline": ORIGINAL, COMPACT: COMPACT}
    controls = {(r["id"], source_method[r["method"]]): r for r in timings}
    assert len(controls) == len(timings) == 8
    for (ident, method), row in controls.items():
        assert row["status"] == "ok" and row["cpu"] == controls[ident, ORIGINAL]["cpu"]
        row["other_s"] = float(row["outer_setup_s"]) + float(row["worker_other_s"])
        stages = sum(float(row[col] or 0) for col in STAGES.values())
        assert abs(stages - float(row["launcher_wall_s"])) < 1e-5

    # Each archived compact recording has one worker clock from the campaign
    # that produced its prediction. The compact-projector clock is a different solver.
    secant_wall = {}
    for r in secant:
        clock_col = {
            "fresh_full_panel": "worker_wall_s",
            "prior_timing": "prior_timing_worker_wall_s",
            "prior_confirmation": "prior_confirmation_worker_wall_s",
        }[r["source"]]
        secant_wall[r["recording"], r["arm"]] = (float(r[clock_col]), r["source"])

    # Key every input by recording, actual solver and calibration before joining.
    endpoints = {}
    for r in full:
        if r["method"] in METHODS:
            key = (r["id"], r["method"], r["arm"])
            assert key not in endpoints
            endpoints[key] = dict(
                cohort=r["cohort"], outcome=r["outcome"], error=number(r["error_km"]),
                rms=number(r["rf_rms_hz"]), rms_kind=r["rf_rms_kind"],
                wall=number(r["worker_wall_s"]), source=r["source"],
            )
    common_keys = set()
    for r in benchmark:
        ident, method, arm = r["id"], r["method"], r["arm"]
        if method not in METHODS:
            continue
        key = (ident, method, arm)
        assert key not in common_keys and r["status"] in {"fix", "ok"}
        common_keys.add(key)
        if r["dataset"] == "DS26":
            assert endpoints[key]["cohort"] == "common127"
            assert endpoints[key]["error"] == float(r["error_km"])
            continue
        assert r["dataset"] == "DS29" and key not in endpoints
        if method == COMPACT:
            wall, source = secant_wall[ident, arm]
        else:
            wall, source = float(r["recorded_wall_s"]), "archived_original_v5"
        endpoints[key] = dict(
            cohort="ds29_benchmark", outcome="published", error=float(r["error_km"]),
            rms=float(r["conditional_rms_hz"]),
            rms_kind="compact secant cavity conditional RMS" if method == COMPACT
            else "archived original v5 report RMS",
            wall=wall, source=source,
        )
    assert common_keys == {k for k, v in endpoints.items() if v["cohort"] != "excluded32"}

    records = []
    for ident in sorted({k[0] for k in endpoints}):
        for method in METHODS:
            zero, fit = (endpoints[ident, method, a] for a in ARMS)
            assert all(zero[k] == fit[k] for k in ("cohort", "outcome", "wall", "source", "rms_kind"))
            for endpoint in (zero, fit):
                assert (endpoint["error"] is not None) == (endpoint["outcome"] == "published")
            if (ident, "c0") in secant_wall and method == COMPACT:
                assert zero["wall"] == secant_wall[ident, "c0"][0]
            control = controls.get((ident, method), {})
            records.append(dict(
                recording=ident, dataset=ident.split("-")[0], cohort=zero["cohort"], solver=method,
                outcome=zero["outcome"], archived_wall_s=zero["wall"], timing_source=zero["source"],
                same_core_wall_s=number(control.get("launcher_wall_s")),
                same_core_numerical_s=number(control.get("numerical_published_boundary_s")),
                c0_error_km=zero["error"], fitted_c_error_km=fit["error"],
                c0_rf_rms_hz=zero["rms"], fitted_c_rf_rms_hz=fit["rms"], rf_metric=zero["rms_kind"],
            ))
    return records, controls


def header(fig, title, subtitle):
    fig.text(.043, .958, title, fontsize=23, weight="bold", va="top", color=INK)
    fig.text(.044, .958 - .48 / fig.get_figheight(), subtitle, fontsize=12, va="top", color=MUTED)
    lines = [
        Line2D([], [], color=COLORS[ORIGINAL], lw=3.4, label=NAMES[ORIGINAL]),
        Line2D([], [], color=COLORS[COMPACT], lw=2.5, ls=(0, (3, 2)), label=NAMES[COMPACT]),
    ]
    fig.legend(handles=lines, loc="upper right", bbox_to_anchor=(.971, .957),
               ncol=2, frameon=False, handlelength=2.5, columnspacing=1.6, borderaxespad=0)


def probability_axes(ax, limits, ticks, tick_labels=None):
    ax.set_xscale("log")
    ax.set_xlim(limits)
    ax.set_xticks(ticks, tick_labels or [f"{x:g}" for x in ticks])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_ylim(-.028, 1.035)
    ax.set_yticks([0, .25, .5, .75, 1])
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.grid(True, color=GRID, lw=.8)
    ax.set_axisbelow(True)


def distribution(ax, values, denominator, method):
    values = np.asarray(values, dtype=float)
    lo, hi = ax.get_xlim()
    assert len(values) <= denominator and np.all((lo < values) & (values < hi))
    unique, repetitions = np.unique(values, return_counts=True)
    end_fraction = len(values) / denominator
    ax.step(np.r_[lo, unique, hi], np.r_[0, np.cumsum(repetitions) / denominator, end_fraction],
            where="post", color=COLORS[method], lw=3.5 if method == ORIGINAL else 2.4,
            ls="solid" if method == ORIGINAL else (0, (3, 2)), solid_capstyle="butt")


def position_plot(rows):
    fig, axes = plt.subplots(2, 3, figsize=(14.3, 7.8), sharex=True, sharey=True)
    fig.subplots_adjust(left=.103, right=.97, top=.76, bottom=.165, wspace=.17, hspace=.18)
    header(fig, "Cumulative horizontal position error",
           "Each step counts recordings with a published fix within the distance on the horizontal axis.")
    panels = [
        ("DS26 · full roster", [r for r in rows if r["dataset"] == "DS26"]),
        ("DS26 · standard benchmark", [r for r in rows if r["cohort"] == "common127"]),
        ("DS29 · standard benchmark", [r for r in rows if r["dataset"] == "DS29"]),
    ]
    for col, (title, panel) in enumerate(panels):
        denom = len({r["recording"] for r in panel})
        counts = [sum(r["solver"] == m and r["outcome"] == "published" for r in panel) for m in METHODS]
        ax = axes[0, col]
        ax.text(0, 1.23, title, weight="bold", fontsize=14.2, transform=ax.transAxes)
        ax.text(0, 1.10, f"{denom} recordings   ·   {counts[0]} original / {counts[1]} compact fixes",
                color=MUTED, fontsize=10, transform=ax.transAxes)
        for idx, (arm, label) in enumerate([("fitted_c", "Fitted calibration"), ("c0", "Zero calibration")]):
            ax = axes[idx, col]
            probability_axes(ax, (.035, 10), [.05, .1, .3, 1, 2, 5, 10])
            for method in METHODS:
                errors = [r[f"{arm}_error_km"] for r in panel
                          if r["solver"] == method and r["outcome"] == "published"]
                distribution(ax, errors, denom, method)
            if col == 0:
                ax.set_ylabel(f"{label}\nShare of recordings", fontsize=11, labelpad=13)
            if idx == 1:
                ax.set_xlabel("Horizontal error (km)", labelpad=8)
    fig.text(.044, .052,
             "The denominator includes every recording in each roster. The 127-recording benchmark is a subset of DS26. Both datasets come from the same roof.",
             fontsize=10.5, color=MUTED)
    return fig


def runtime_plot(rows, controls):
    fig, axes = plt.subplots(1, 3, figsize=(14.3, 5.7), gridspec_kw={"width_ratios": [1.11, 1, 1]})
    fig.subplots_adjust(left=.091, right=.973, top=.68, bottom=.25, wspace=.32)
    header(fig, "Runtime from saved detections",
           "Desktop elapsed time per recording. Each solver invocation includes both calibration settings.")
    titles = ["Controlled replay", "DS26 · archived runs", "DS29 · archived runs"]
    datasets = {ds: [r for r in rows if r["dataset"] == ds and r["archived_wall_s"] is not None]
                for ds in ("DS26", "DS29")}
    captions = ["4 recordings · same core within each pair",
                *[f"{len(subset) // 2} timed runs per solver" for subset in datasets.values()]]
    for ax, title, caption in zip(axes, titles, captions, strict=True):
        ax.text(0, 1.19, title, weight="bold", fontsize=14.7, transform=ax.transAxes)
        ax.text(0, 1.085, caption, color=MUTED, fontsize=10.5, transform=ax.transAxes)

    ax = axes[0]
    ids = sorted({k[0] for k in controls})
    ax.set_ylim(len(ids) - .45, -.52)
    ax.set_xlim(0, 7.7)
    ax.set_xticks([0, 2, 4, 6])
    ax.set_yticks(range(len(ids)), ids, fontsize=10)
    ax.grid(axis="x", color=GRID)
    for y, ident in enumerate(ids):
        times = {m: float(controls[ident, m]["launcher_wall_s"]) for m in METHODS}
        ax.hlines(y, min(times.values()) / 60, max(times.values()) / 60, color="#ADB9C2", lw=1.8)
        for method in METHODS:
            x = times[method] / 60
            ax.scatter(x, y, marker=MARKERS[method], color=COLORS[method], s=54, zorder=3)
            ax.annotate(f"{times[method]:.0f} s", (x, y), xytext=(0, 8), textcoords="offset points",
                        ha="center", color=COLORS[method], fontsize=9.3, weight="bold")
    ax.set_xlabel("Time to usable output (min)", labelpad=8)
    for ax, subset in zip(axes[1:], datasets.values(), strict=True):
        probability_axes(ax, (.45, 22), [.5, 1, 2, 5, 10, 20])
        for method in METHODS:
            minutes = [r["archived_wall_s"] / 60 for r in subset if r["solver"] == method]
            distribution(ax, minutes, len(minutes), method)
        ax.set_xlabel("Time to worker exit (min)", labelpad=8)
    axes[1].set_ylabel("Share of timed runs", labelpad=5)
    fig.text(.044, .087, "Controlled runs include normal output handling and the original’s eight diagnostic plots. Archives used different CPU allocations and time limits.",
             fontsize=10.5, color=MUTED)
    fig.text(.044, .043, "Archived runtimes include failures and timeouts. One DS26 recording had no detector input. Raw-signal acquisition and GLRT precede these clocks.",
             fontsize=10.5, color=MUTED)
    return fig


def stage_plot(controls):
    fig, ax = plt.subplots(figsize=(12.9, 7.1))
    fig.subplots_adjust(left=.29, right=.765, top=.78, bottom=.15)
    header(fig, "Runtime by processing stage",
           "Four same-core recording pairs. Dots are individual elapsed times and open diamonds mark medians.")
    ax.set_ylim(len(STAGES) - .44, -.56)
    ax.set_xlim(-3, 170)
    ax.set_yticks(range(len(STAGES)), STAGES.keys())
    ax.set_xticks(np.arange(0, 161, 20))
    ax.set_xlabel("Stage wall time (s)", labelpad=8)
    ax.grid(axis="x", color=GRID)
    for method, offset, xcol, column in [(ORIGINAL, -.15, 1.10, "Original"),
                                          (COMPACT, .15, 1.29, "Compact")]:
        ax.text(xcol, 1.05, column, ha="center", transform=ax.transAxes, fontsize=11,
                color=COLORS[method], weight="bold")
        rows = [r for (_, m), r in sorted(controls.items()) if m == method]
        for i, col in enumerate(STAGES.values()):
            y = i + offset
            values = [float(r[col]) for r in rows if r[col] != ""]
            label = "Skipped"
            if values:
                median = float(np.median(values))
                label = f"{median:.1f} s"
                ax.hlines(y, min(values), max(values), color=COLORS[method], lw=1.2, alpha=.65,
                          linestyle="solid" if method == ORIGINAL else "dashed")
                ax.scatter(values, y + np.array([-.037, .033, -.018, .047]), s=25, color=COLORS[method], zorder=3)
                ax.scatter(median, y, s=48, marker="D", facecolor="white", edgecolor=COLORS[method], lw=1.65, zorder=4)
            ax.text(xcol, i, label, ha="center", va="center", transform=ax.get_yaxis_transform(), color=COLORS[method])
    fig.text(.044, .052, "Each column gives the median of four recordings. A position refit is timed within the stage that requests it. The clocks start from saved GLRT detections.",
             fontsize=10.3, color=MUTED)
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT, help="Directory for the figures and CSV")
    out = parser.parse_args().out.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows, controls = measured_rows()
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "text.color": INK,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.spines.left": False, "axes.spines.bottom": False,
                         "xtick.major.size": 0, "ytick.major.size": 0, "pdf.fonttype": 42})
    with (out / "per-recording.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    with PdfPages(out / "v5-comparison.pdf", metadata={"CreationDate": None}) as pdf:
        for name, fig in [("runtime", runtime_plot(rows, controls)),
                          ("position-error", position_plot(rows)), ("stage-runtime", stage_plot(controls))]:
            fig.savefig(out / f"{name}.png", dpi=160, facecolor="white")
            pdf.savefig(fig, facecolor="white")
            plt.close(fig)


if __name__ == "__main__":
    main()
