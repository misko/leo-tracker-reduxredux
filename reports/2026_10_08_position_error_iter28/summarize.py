"""Report every assigned member and apply the frozen validation gates."""

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
            for arm in ARMS:
                selected = next(
                    a["selected"] for a in baseline["methods"][0]["arms"] if a["name"] == arm
                )
                current = raw["result"]
                values = {
                    "published": dict(
                        error_km=selected["horizontal_error_m"] / 1000,
                        rms_hz=selected["posterior_rms_hz"],
                        stage="published",
                    )
                }
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
        rows = [r for r in cases if r["member"]["group"] == group]
        complete = [r for r in rows if r["status"] == "complete"]
        metrics[group] = dict(assigned=len(rows), complete=len(complete), arms={})
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
    all_complete = validation["complete"] == validation["assigned"]
    gates = dict(all_assigned_complete=all_complete)
    if all_complete:
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
    result = dict(cases=cases, metrics=metrics, gates=gates, qualified=all(gates.values()))
    (HERE / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
    complete = [r for r in cases if r["status"] == "complete"]
    for ax, arm in zip(axes, ARMS, strict=True):
        x = np.arange(len(complete))
        for i, variant in enumerate(VARIANTS):
            ax.bar(
                x + (i - 1) * 0.25,
                [r["arms"][arm]["variants"][variant]["error_km"] for r in complete],
                width=0.25,
                label=variant,
            )
        ax.set_xticks(
            x, [r["member"]["label"] + "\n" + r["member"]["group"] for r in complete], fontsize=8
        )
        ax.set(title=arm, ylabel="Position error (km)")
        ax.axhline(1, color="gray", linewidth=1)
        if complete:
            ax.legend(fontsize=8)
        else:
            ax.text(
                0.5,
                0.5,
                "Reserved outcomes unopened\nDevelopment baseline unavailable",
                transform=ax.transAxes,
                ha="center",
                va="center",
            )
        ax.grid(axis="y", alpha=0.2)
    fig.savefig(HERE / "reserved-comparison.png", dpi=160)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
    for ax, label in zip(axes, plan["canaries"], strict=True):
        canary = json.loads((HERE / "canaries" / f"{label}.json").read_text())
        expected = json.loads(
            (HERE.parent / "2026_10_08_position_error_iter27/results" / f"{label}.json").read_text()
        )
        for i, arm in enumerate(ARMS):
            old = next(
                r
                for r in expected["candidates"]
                if r["arm"] == arm and r["variant"] == "sigma-0.25"
            )
            new = canary["result"]["stages"]["slope-0.25"][arm]
            ax.bar(
                i - 0.15,
                old["error_km"],
                width=0.3,
                color="C0",
                label="Frozen iteration27" if i == 0 else None,
            )
            ax.bar(
                i + 0.15,
                new["error_km"],
                width=0.3,
                color="C1",
                label="Assembled final stage" if i == 0 else None,
            )
        ax.set_xticks([0, 1], ARMS)
        ax.set(title=label + ": exact numerical match", ylabel="Position error (km)")
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.2)
    fig.savefig(HERE / "canary-comparison.png", dpi=160)
    print(json.dumps({k: result[k] for k in ("metrics", "gates", "qualified")}, indent=2))


if __name__ == "__main__":
    main()
