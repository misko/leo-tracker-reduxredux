"""Render measured fits and the numeric evidence for bounded native arrivals."""

from ..__main__ import save_json
from . import native_arrival as trial
from . import native_arrival_results as results
from .prefix_figures import csv_file

STAGE_ID = "native-arrival-ds26-0020-stage"
STAGE_PNG = "bounded-arrival.png"
STAGE_CSV = "stage.csv"
STAGE_FIGURE = "stage-figure.json"


def stage(output, scored):
    import matplotlib.pyplot as plt
    import numpy as np

    methods = [trial.method(w, p) for w, p in trial.POLICY_ORDER]
    methods = sorted(methods, key=lambda m: (m[0], m[3:])) + [trial.MISSING]
    plotted = []

    def add(panel, method, source, statistic, value, unit):
        plotted.append(dict(panel=panel, method=method, source=source, statistic=statistic,
                            value=value, unit=unit))

    model = {
        label: trial.unpack(output / f"{label}-schedules.json.gz")
        for label in (trial.NATIVE, trial.EXPRESS)
    }
    fig, axes = plt.subplots(2, 2, figsize=(14.8, 9.6))
    fig.suptitle("Bounded native detector arrivals · DS26-0020", x=0.07, ha="left",
                 fontweight="bold", fontsize=20, color="#18313b")
    xpos = np.arange(len(methods))
    for label, clock, hue, dx, legend in (
        (trial.NATIVE, "cpu", "#08716d", -0.22, "Portable C · CPU service"),
        (trial.NATIVE, "wall", "#70aaa3", 0, "Portable C · wall service"),
        (trial.EXPRESS, "cpu", "#a4553e", 0.22, "Accelerated · CPU service"),
    ):
        summary = [model[label][clock][m]["summary"] for m in methods]
        pct = [100 * row["ready_count"] / row["valid_count"] for row in summary]
        axes[0, 0].bar(xpos + dx, pct, width=0.2, label=legend, color=hue)
        for x, m, row, val in zip(xpos + dx, methods, summary, pct, strict=True):
            add("retention", m, f"{label} {clock}", "ready", val, "% valid")
            ages = row["age_ms"]
            if ages["n"]:
                axes[0, 1].plot((x, x), (ages["p50"], ages["p95"]), color=hue, linewidth=2)
                axes[0, 1].scatter((x, x), (ages["p50"], ages["p95"]), color=hue, s=14)
                for q in ("p50", "p95"):
                    add("ready_age", m, f"{label} {clock}", q, ages[q], "ms")
    axes[0, 0].set(title="Retained visits from the delivery model", ylabel="Valid visits ready (%)",
                   ylim=(0, 100))
    axes[0, 0].legend(frameon=False, loc="upper left", fontsize=8)
    axes[0, 1].axhline(1000, color="#777777", linestyle=":", linewidth=1)
    add("ready_age", "all", "protocol", "age_cap", 1000, "ms")
    axes[0, 1].set(title="Median to p95 detector readiness", ylabel="Delivery to readiness (ms)",
                   ylim=(0, 1075))
    common = {r["method"]: r["status"] for r in scored}
    lookup = {(r["method"], r["arm"]): r for r in scored}
    errors = [*methods[:-1], results.FULL, "baseline", "omitted-track-one"]
    for arm, color, dx, marker in (("c0", "#166b85", -0.13, "o"),
                                    ("fitted_c", "#a54c36", 0.13, "D")):
        for i, key in enumerate(errors):
            row = lookup[key, arm]
            for axis, field, unit in ((axes[1, 0], "error_km", "km"),
                                      (axes[1, 1], "rf_rms_hz", "Hz")):
                value = row[field]
                if value is None:
                    continue
                axis.scatter(i + dx, value, s=30, color=color, marker=marker, zorder=3,
                             label=arm.replace("_", " ") if i == 1 else None)
                add(field, key, "position run", arm, value, unit)
    for i, key in enumerate(errors):
        if common[key] != "ok":
            for axis in axes[1]:
                axis.annotate(common[key], xy=(i, 0.06), xycoords=("data", "axes fraction"),
                              color="#5d6e6e", rotation=90, fontsize=8, ha="center")
    axes[1, 0].set(title="Recomputed compact position error", ylabel="Surveyed position error (km)")
    axes[1, 0].legend(frameon=False, loc="upper left", fontsize=8)
    axes[1, 1].set(title="In-sample RF residuals", ylabel="CFO RMS (Hz)")
    tick = {
        m: m.replace("w-", "w\n").replace("replace-oldest", "replace").replace("rf-round-robin", "RF RR")
        for m in methods
    } | {results.FULL: "Full C", "baseline": "v5 no repair", "omitted-track-one": "v5 omit one"}
    for axis, keys in zip(axes.flat, (methods, methods, errors, errors), strict=True):
        axis.set_xticks(range(len(keys)), [tick[m] for m in keys], fontsize=8)
        axis.grid(axis="y", alpha=0.23)
        axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(rect=(0, 0.01, 1, 0.94), h_pad=2.1, w_pad=2.5)
    fig.savefig(output / STAGE_PNG, dpi=145)
    plt.close(fig)
    csv_file(output / STAGE_CSV, plotted)
    save_json(output / STAGE_FIGURE, dict(
        version=1, id=STAGE_ID, seal=results.SCORE_LOCK, image=STAGE_PNG, csv=STAGE_CSV,
        title="Bounded native detector arrivals",
        sample="DS26-0020 across 6,764 signed hardware-counter arrivals.",
        boundary="Queue readiness is modeled from measured native C service. Compact fits are measured.",
        note="Geographic error and in-sample CFO residuals use separate axes. Both fitted-c arms use the same input selection as c = 0.",
    ))
    return STAGE_PNG, STAGE_CSV, STAGE_FIGURE


def descriptors(output):
    charts = []
    for w, policy in trial.POLICY_ORDER:
        name = trial.method(w, policy)
        charts.append(dict(
            id=f"native-arrival-ds26-0020-{name}", method=name, scope="roof",
            title=f"Bounded arrival · {results.LABELS[name]}",
            caption="Recomputed both calibration arms on whole paired C visits selected by the one-second queue model. Original v5 omitted-tracks timed out.",
            cases=[trial.CASE], seal=results.SCORE_LOCK, provenance=[results.PREDICTION_LOCK],
            series=[
                dict(key=key, label=results.LABELS[m], file=results.PREDICTIONS, value=m,
                     native_field="archived_native_sha256", match=list(results.FIT_SOURCES))
                for key, m in (("one", name), ("stock", results.FULL))
            ],
        ))
    save_json(output / "figures.json", dict(version=2, charts=charts))
