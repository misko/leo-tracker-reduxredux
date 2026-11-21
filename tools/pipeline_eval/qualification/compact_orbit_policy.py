"""Compare all three receivers with both measured orbit retries applied equally."""

import csv
from collections import defaultdict

import numpy as np

from ..variants import v5_orbit_domain
from .compact_position_diagnosis import OUT, panel
from .compact_position_score import paired_interval
from .full_v5_check import _sha
from .reverse_glrt_report import write_csv


def selected_mode(reason, function):
    if reason == "ValueError: " + v5_orbit_domain.OUTSIDE and function == "prepare":
        return "orbit_support"
    if reason == "AssertionError" and function == "previous_bank":
        return "history_support"
    return "stock"


def position_figure(rows):
    import matplotlib.pyplot as plt

    from .blind_compact_figures import COLORS, LINES, NAMES, cdf_axis, cumulative

    fig, axes = plt.subplots(1, 2, figsize=(9.7, 4.45), sharey=True)
    fig.subplots_adjust(left=0.088, right=0.985, top=0.71, bottom=0.19, wspace=0.19)
    fig.text(
        0.042,
        0.925,
        "Position after both orbit repairs",
        fontsize=19,
        weight="bold",
        color="#192f3c",
    )
    fig.text(
        0.043,
        0.848,
        "Same recordings and orbit rules for all three receivers  ·  Fitted RF calibration",
        fontsize=10,
        color="#465966",
    )
    fitted = [r for r in rows if r["calibration"] == "fitted_c"]
    limit = max(1, float(np.ceil(max(r["error_km"] for r in fitted if r["error_km"] is not None))))
    for ax, dataset in zip(axes, ("DS26", "DS29"), strict=True):
        ax.set_title(dataset + "  ·  8 recordings", loc="left", weight="bold", fontsize=12)
        for method in panel.METHODS:
            values = [
                r["error_km"] for r in fitted if (r["method"], r["dataset"]) == (method, dataset)
            ]
            xx, yy = cumulative(values, len(values), (0, limit))
            ax.step(
                xx,
                yy,
                where="post",
                color=COLORS[method],
                ls=LINES[method],
                lw=2.2,
                label=NAMES[method],
            )
        cdf_axis(ax)
        ax.set_xlim(0, limit)
        ax.set_axisbelow(True)
        ax.grid(color="#dfe5e9", lw=0.8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xlabel("Horizontal position error (km)")
    axes[0].set_ylabel("Fraction of all recordings")
    axes[1].legend(loc="lower right", frameon=False, fontsize=8.5)
    fig.savefig(OUT / "orbit-policy-position.png", dpi=160, facecolor="white")
    plt.close(fig)


def run():
    def read_csv(path):
        with path.open() as stream:
            return list(csv.DictReader(stream))

    index = {
        (r["case"], r["method"], r["calibration"], r["mode"]): r
        for r in read_csv(OUT / "recordings.csv")
    }
    errors = {(r["case"], r["method"]): r for r in read_csv(panel.OUT / "solver-failures.csv")}
    rows = []
    for (case, method, arm, mode), row in index.items():
        if mode != "stock":
            continue
        failure = errors.get((case, method), {})
        if failure.get("reason", "") != row["reason"]:
            raise ValueError("stock failure differs from frozen traceback")
        route = selected_mode(row["reason"], failure.get("function"))
        selected = index[case, method, arm, route]
        rows.append(
            dict(
                case=case,
                dataset=row["dataset"],
                method=method,
                calibration=arm,
                route=route,
                error_km=float(selected["error_km"]) if selected["error_km"] else None,
                rf_rms_hz=float(selected["rf_rms_hz"]) if selected["rf_rms_hz"] else None,
            )
        )
    baseline = {(r["case"], r["calibration"]): r for r in rows if r["method"] == "original"}
    groups = defaultdict(list)
    for r in rows:
        for label in ("all", r["dataset"]):
            groups[label, r["method"], r["calibration"]].append(r)
    summary = []
    for (dataset, method, arm), assigned in groups.items():
        fixed = [r for r in assigned if r["error_km"] is not None]
        e = np.array([r["error_km"] for r in fixed])
        pairs = [
            (baseline[r["case"], arm], r)
            for r in fixed
            if baseline[r["case"], arm]["error_km"] is not None
        ]
        deltas = [b["error_km"] - a["error_km"] for a, b in pairs]
        lo, hi = paired_interval(pairs)
        summary.append(
            dict(
                dataset=dataset,
                method=method,
                calibration=arm,
                assigned=len(assigned),
                fixes=len(fixed),
                within_1km=int((e <= 1).sum()),
                within_2km=int((e <= 2).sum()),
                median_km=float(np.median(e)),
                p95_km=float(np.quantile(e, 0.95)),
                median_rf_rms_hz=float(np.median([r["rf_rms_hz"] for r in fixed])),
                common_with_glrt=len(pairs),
                closer_than_glrt=sum(d < 0 for d in deltas),
                farther_than_glrt=sum(d > 0 for d in deltas),
                median_delta_km=float(np.median(deltas)),
                delta_bootstrap_low_km=lo,
                delta_bootstrap_high_km=hi,
            )
        )
    write_csv(OUT / "orbit-policy-recordings.csv", rows)
    write_csv(OUT / "orbit-policy-summary.csv", summary)
    position_figure(rows)
    panel.seal(
        OUT / "orbit-policy-lock.json",
        dict(
            input_predictions=_sha(OUT / "prediction-lock.json"),
            failure_routes=_sha(panel.OUT / "solver-failures.csv"),
            results=_sha(OUT / "orbit-policy-recordings.csv"),
        ),
    )


if __name__ == "__main__":
    run()
