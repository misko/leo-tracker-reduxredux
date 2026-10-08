"""Apply the unchanged full-corpus gates to every tighter satellite prior."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ARMS = ("fitted-c", "zero-c")


def metrics(cases, variants):
    return {
        arm: {
            variant: dict(
                count=len(cases),
                mean_km=float(np.mean([r["arms"][arm][variant]["error_km"] for r in cases])),
                median_km=float(np.median([r["arms"][arm][variant]["error_km"] for r in cases])),
                p95_km=float(
                    np.percentile([r["arms"][arm][variant]["error_km"] for r in cases], 95)
                ),
                worst_km=float(max(r["arms"][arm][variant]["error_km"] for r in cases)),
                mean_rms_hz=float(np.mean([r["arms"][arm][variant]["rms_hz"] for r in cases])),
                raw_converged_count=sum(r["arms"][arm][variant]["raw_converged"] for r in cases),
                fallback_count=sum(r["arms"][arm][variant]["fallback"] is not None for r in cases),
            )
            for variant in variants
        }
        for arm in ARMS
    }


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    parent = json.loads((HERE.parent / "2026_10_08_position_error_iter25/summary.json").read_text())
    cases = []
    variants = ["control", *protocol["variants"], "sigma-1"]
    for label in protocol["labels"]:
        old = next(r for r in parent["cases"] if r["label"] == label)
        document = json.loads((HERE / "results" / f"{label}.json").read_text())
        record = dict(label=label, cohort=old["cohort"], arms={})
        for arm in ARMS:
            control = old["arms"][arm]["control"]
            record["arms"][arm] = dict(control=control, **{"sigma-1": old["arms"][arm]["slope"]})
            for row in document["candidates"]:
                if row["arm"] != arm:
                    continue
                record["arms"][arm][row["variant"]] = dict(
                    error_km=row["error_km"] if row["converged"] else control["error_km"],
                    rms_hz=row["posterior_rms_hz"] if row["converged"] else control["rms_hz"],
                    raw_converged=row["converged"],
                    raw_error_km=row["error_km"],
                    fallback=None if row["converged"] else "matched control operational",
                    stationarity=row["stationarity"],
                    max_satellite_slope_hz_s=float(
                        max(abs(np.asarray(row["satellite_slopes_hz_s"])))
                    ),
                )
                if arm == "zero-c":
                    assert row["vector"][6] == 0 and row["rf_drift_coefficients"] == [0, 0]
        cases.append(record)
    assert len(cases) == 119 and len({r["label"] for r in cases}) == 119
    pooled = metrics(cases, variants)
    cohorts = {
        c: metrics([r for r in cases if r["cohort"] == c], variants)
        for c in ("DS16", "DS17", "NEW", "FRESH", "LATER")
    }
    limits, gates = protocol["gates"], {}
    baseline = pooled["fitted-c"]["control"]
    for variant in variants[1:]:
        row = pooled["fitted-c"][variant]
        gates[variant] = dict(
            all119complete=True,
            mean_below_1km=row["mean_km"] < 1,
            mean_below_control=row["mean_km"] < baseline["mean_km"],
            cohort_mean_guard=all(
                v["fitted-c"][variant]["mean_km"]
                <= limits["each_cohort_mean_no_more_than_control_factor"]
                * v["fitted-c"]["control"]["mean_km"]
                for v in cohorts.values()
            ),
            p95_guard=row["p95_km"]
            <= limits["pooled_p95_and_worst_no_more_than_control_factor"] * baseline["p95_km"],
            worst_guard=row["worst_km"]
            <= limits["pooled_p95_and_worst_no_more_than_control_factor"] * baseline["worst_km"],
            convergence=row["raw_converged_count"] / 119
            >= limits["fitted_raw_convergence_fraction_at_least"],
        )
    selected = next((v for v in protocol["variants"] if all(gates[v].values())), None)
    summary = dict(cases=cases, pooled=pooled, cohorts=cohorts, gates=gates, selected=selected)
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
    for ax, arm in zip(axes[0], ARMS, strict=True):
        for variant in variants:
            values = np.sort([r["arms"][arm][variant]["error_km"] for r in cases])
            ax.step(values, np.arange(1, 120) / 119, where="post", label=variant)
        ax.set(xlabel="Position error (km)", ylabel="Fraction of 119 scans", title=arm)
        ax.axvline(1, color="gray", linewidth=1)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.2)
    for ax, field, title in (
        (axes[1, 0], "mean_km", "Fitted-c mean error (km)"),
        (axes[1, 1], "mean_rms_hz", "Fitted-c mean frequency RMS (Hz)"),
    ):
        for cohort, values in cohorts.items():
            ax.plot(
                variants, [values["fitted-c"][v][field] for v in variants], marker="o", label=cohort
            )
        ax.set_title(title)
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.savefig(HERE / "prior-comparison.png", dpi=160)
    print(json.dumps({k: summary[k] for k in ("pooled", "gates", "selected")}, indent=2))


if __name__ == "__main__":
    main()
