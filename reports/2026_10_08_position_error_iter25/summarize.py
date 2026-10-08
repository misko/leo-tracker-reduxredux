"""All-member broad regression gates for the frozen satellite slope candidate."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ARMS = ("fitted-c", "zero-c")
METHODS = ("previous", "control", "slope")
COHORTS = ("DS16", "DS17", "NEW", "FRESH", "LATER")


def aggregate(cases):
    result = {}
    for arm in ARMS:
        result[arm] = {}
        for method in METHODS:
            rows = [row["arms"][arm][method] for row in cases]
            errors = np.array([row["error_km"] for row in rows])
            result[arm][method] = dict(
                count=len(rows),
                mean_km=float(errors.mean()),
                median_km=float(np.median(errors)),
                p95_km=float(np.percentile(errors, 95)),
                worst_km=float(errors.max()),
                mean_rms_hz=float(np.mean([row["rms_hz"] for row in rows])),
                raw_converged_count=(
                    sum(row["raw_converged"] for row in rows) if method != "previous" else None
                ),
                fallback_count=(
                    sum(row["fallback"] is not None for row in rows)
                    if method != "previous"
                    else None
                ),
            )
    return result


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    assert len(protocol["members"]) == 119
    cases = []
    for label, binding in protocol["members"].items():
        document = json.loads((HERE / "results" / f"{label}.json").read_text())
        item = dict(label=label, cohort=binding["cohort"], arms={})
        for arm in ARMS:
            previous = document["previous_operational"][arm]
            raw = {r["variant"]: r for r in document["candidates"] if r["arm"] == arm}
            control = raw["control"] if raw["control"]["converged"] else previous
            item["arms"][arm] = dict(
                previous=dict(error_km=previous["error_km"], rms_hz=previous["posterior_rms_hz"])
            )
            for variant in ("control", "slope"):
                row = raw[variant]
                selected = row if row["converged"] else control
                fallback = (
                    None
                    if row["converged"]
                    else ("control" if raw["control"]["converged"] else "previous")
                )
                item["arms"][arm][variant] = dict(
                    error_km=selected["error_km"],
                    rms_hz=selected["posterior_rms_hz"],
                    raw_converged=row["converged"],
                    raw_error_km=row["error_km"],
                    stationarity=row["stationarity"],
                    fallback=fallback,
                    elapsed_s=row["elapsed_s"],
                )
                if arm == "zero-c":
                    assert row["vector"][6] == 0 and row["rf_drift_coefficients"] == [0, 0]
        cases.append(item)
    pooled = aggregate(cases)
    by_cohort = {c: aggregate([r for r in cases if r["cohort"] == c]) for c in COHORTS}
    limits = protocol["gates"]
    control, slope = pooled["fitted-c"]["control"], pooled["fitted-c"]["slope"]
    gates = dict(
        all119complete=len(cases) == 119,
        fitted_pooled_mean_below_1km=slope["mean_km"] < 1,
        fitted_pooled_mean_below_control=slope["mean_km"] < control["mean_km"],
        each_cohort_mean_guard=all(
            value["fitted-c"]["slope"]["mean_km"]
            <= limits["each_cohort_mean_no_more_than_control_factor"]
            * value["fitted-c"]["control"]["mean_km"]
            for value in by_cohort.values()
        ),
        pooled_p95_guard=slope["p95_km"]
        <= limits["pooled_p95_and_worst_no_more_than_control_factor"] * control["p95_km"],
        pooled_worst_guard=slope["worst_km"]
        <= limits["pooled_p95_and_worst_no_more_than_control_factor"] * control["worst_km"],
        fitted_raw_convergence=slope["raw_converged_count"] / len(cases)
        >= limits["fitted_raw_convergence_fraction_at_least"],
    )
    differences = [
        dict(
            label=r["label"],
            delta_km=r["arms"]["fitted-c"]["slope"]["error_km"]
            - r["arms"]["fitted-c"]["control"]["error_km"],
        )
        for r in cases
    ]
    summary = dict(
        cases=cases,
        pooled=pooled,
        cohorts=by_cohort,
        gates=gates,
        passed=all(gates.values()),
        changes=dict(
            improved=sum(r["delta_km"] < -0.001 for r in differences),
            worsened=sum(r["delta_km"] > 0.001 for r in differences),
            within_1m=sum(abs(r["delta_km"]) <= 0.001 for r in differences),
        ),
        differences=sorted(differences, key=lambda row: -row["delta_km"]),
    )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    figure, axes = plt.subplots(2, 2, figsize=(13, 9), layout="constrained")
    for ax, arm in zip(axes[0], ARMS, strict=True):
        for method in ("control", "slope"):
            errors = np.sort([row["arms"][arm][method]["error_km"] for row in cases])
            ax.step(errors, np.arange(1, len(errors) + 1) / len(errors), where="post", label=method)
        ax.set(xlabel="Position error (km)", ylabel="Fraction of119 scans", title=arm)
        ax.axvline(1, color="gray", linewidth=1)
        ax.grid(alpha=0.2)
        ax.legend()
    before = np.array([r["arms"]["fitted-c"]["control"]["error_km"] for r in cases])
    after = np.array([r["arms"]["fitted-c"]["slope"]["error_km"] for r in cases])
    axes[1, 0].scatter(before, after, s=18)
    bound = max(before.max(), after.max()) * 1.05
    axes[1, 0].plot([0, bound], [0, bound], "--", color="gray")
    axes[1, 0].set(
        xlabel="Control error (km)", ylabel="Slope error (km)", title="Fitted-c: every recording"
    )
    for delta in summary["differences"][:3]:
        i = next(i for i, r in enumerate(cases) if r["label"] == delta["label"])
        axes[1, 0].annotate(delta["label"], (before[i], after[i]), fontsize=8)
    x = np.arange(len(COHORTS))
    for offset, method in ((-0.18, "control"), (0.18, "slope")):
        axes[1, 1].bar(
            x + offset,
            [by_cohort[c]["fitted-c"][method]["mean_km"] for c in COHORTS],
            width=0.36,
            label=method,
        )
    axes[1, 1].set_xticks(x, COHORTS)
    axes[1, 1].set(ylabel="Mean position error (km)", title="Fitted-c cohort means")
    axes[1, 1].axhline(1, color="gray", linewidth=1)
    axes[1, 1].legend()
    figure.savefig(HERE / "all119-comparison.png", dpi=160)
    print(
        json.dumps(
            {k: summary[k] for k in ("pooled", "cohorts", "gates", "passed", "changes")}, indent=2
        )
    )


if __name__ == "__main__":
    main()
