"""Summarize unchanged completion, retaining every assigned recording."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ARMS = ("fitted-c", "zero-c")
VARIANTS = ("published", "control", "slope-0.25")


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    cases = []
    for member in plan["members"]:
        path = HERE / "results" / f"{member['label']}.json"
        raw = json.loads(path.read_text()) if path.exists() else dict(status="missing")
        row = dict(member=member, status=raw["status"], arms={})
        if raw["status"] == "complete":
            baseline = json.loads((HERE / "baselines" / f"{member['label']}.json").read_text())
            current = raw["result"]
            for arm in ARMS:
                selected = next(
                    a["selected"] for a in baseline["methods"][0]["arms"] if a["name"] == arm
                )
                values = dict(
                    published=dict(
                        error_km=selected["horizontal_error_m"] / 1000,
                        rms_hz=selected["posterior_rms_hz"],
                        stage="published",
                    )
                )
                for name, value in (
                    ("control", current["control_operational"][arm]),
                    ("slope-0.25", current["operational"][arm]),
                ):
                    values[name] = dict(
                        error_km=value["error_km"],
                        rms_hz=value["posterior_rms_hz"],
                        stage=value["stage"],
                    )
                final = current["stages"].get("slope-0.25", {}).get(arm)
                row["arms"][arm] = dict(
                    variants=values,
                    final_raw_converged=False if final is None else final["converged"],
                    final_stationarity=None if final is None else final["stationarity"],
                )
        else:
            row["error"] = raw.get("error", "Result missing")
        cases.append(row)
    metrics = {}
    for group in ("development", "validation"):
        assigned = [r for r in cases if r["member"]["group"] == group]
        complete = [r for r in assigned if r["status"] == "complete"]
        metrics[group] = dict(assigned=len(assigned), complete=len(complete), arms={})
        if complete:
            for arm in ARMS:
                metrics[group]["arms"][arm] = {
                    v: dict(
                        mean_km=float(
                            np.mean([r["arms"][arm]["variants"][v]["error_km"] for r in complete])
                        ),
                        worst_km=float(
                            max(r["arms"][arm]["variants"][v]["error_km"] for r in complete)
                        ),
                        mean_rms_hz=float(
                            np.mean([r["arms"][arm]["variants"][v]["rms_hz"] for r in complete])
                        ),
                    )
                    for v in VARIANTS
                }
    validation = metrics["validation"]
    gates = dict(all_assigned_complete=validation["complete"] == validation["assigned"])
    if gates["all_assigned_complete"]:
        fitted = validation["arms"]["fitted-c"]
        candidate = fitted["slope-0.25"]
        limits = plan["primary_gates"]
        gates.update(
            fitted_mean_below_1km=candidate["mean_km"] < limits["fitted_mean_km_strictly_below"],
            fitted_mean_no_worse_than_published=candidate["mean_km"]
            <= fitted["published"]["mean_km"],
            fitted_mean_no_worse_than_control=candidate["mean_km"] <= fitted["control"]["mean_km"],
            fitted_worst_baseline_guard=candidate["worst_km"]
            <= limits["fitted_worst_no_more_than_baseline_factor"]
            * fitted["published"]["worst_km"],
            fitted_worst_control_guard=candidate["worst_km"]
            <= limits["fitted_worst_no_more_than_control_factor"] * fitted["control"]["worst_km"],
            all_final_slope_fitted_converged=all(
                r["arms"]["fitted-c"]["final_raw_converged"]
                for r in cases
                if r["member"]["group"] == "validation"
            ),
        )
    output = dict(
        cases=cases,
        metrics=metrics,
        gates=gates,
        qualified=all(gates.values()),
        scope="Completion only; original iteration28 development availability failure retained",
    )
    (HERE / "summary.json").write_text(json.dumps(output, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
    complete = [r for r in cases if r["status"] == "complete"]
    x = np.arange(len(complete))
    for ax, arm in zip(axes, ARMS, strict=True):
        for i, v in enumerate(VARIANTS):
            ax.bar(
                x + (i - 1) * 0.25,
                [r["arms"][arm]["variants"][v]["error_km"] for r in complete],
                width=0.25,
                label=v,
            )
        ax.set_xticks(
            x, [r["member"]["label"] + "\n" + r["member"]["group"] for r in complete], fontsize=8
        )
        ax.set(title=arm, ylabel="Position error (km)")
        ax.axhline(1, color="gray", linewidth=1)
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.2)
    fig.savefig(HERE / "completion-comparison.png", dpi=160)
    print(json.dumps({k: output[k] for k in ("metrics", "gates", "qualified")}, indent=2))


if __name__ == "__main__":
    main()
