"""Report every reserved newer member without selecting by measured error."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ARMS = ("fitted-c", "zero-c")
GROUPS = ("development", "validation", "chronological-challenge")


def metrics(rows):
    errors = [row["error_km"] for row in rows]
    return dict(
        count=len(rows), mean_km=float(np.mean(errors)), median_km=float(np.median(errors)),
        p95_km=float(np.percentile(errors, 95)), worst_km=float(np.max(errors)),
        mean_rms_hz=float(np.mean([row["posterior_rms_hz"] for row in rows])),
    )


def main():
    protocol = json.loads((HERE / "validation-protocol.json").read_text())
    cases = []
    for member in protocol["members"]:
        label = member["label"]
        path = HERE / "results" / f"{label}.json"
        output = json.loads(path.read_text()) if path.exists() else dict(status="missing")
        row = dict(label=label, group=member["evaluation_group"], status=output["status"])
        if row["status"] == "complete":
            original = json.loads((HERE / "baselines" / f"{label}.json").read_text())
            row["baseline"] = {}
            for item in original["methods"][0]["arms"]:
                selected = item["selected"]
                row["baseline"][item["name"]] = dict(
                    error_km=selected["horizontal_error_m"] / 1000,
                    posterior_rms_hz=selected["posterior_rms_hz"],
                    converged=selected["converged"],
                )
            result = output["result"]
            row["candidate"] = {
                arm: {key: value[key] for key in (
                    "error_km", "posterior_rms_hz", "converged", "stage"
                )}
                for arm, value in result["operational"].items()
            }
            row["stopped"] = result["stopped"]
            row["regions"] = result["regional_sources"]
            row["removed"] = result.get("removed", [])
        else:
            row["error"] = output.get("error", "No result")
        cases.append(row)
    groups = {}
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), layout="constrained")
    for column, group in enumerate(GROUPS):
        assigned = [row for row in cases if row["group"] == group]
        complete = [row for row in assigned if row["status"] == "complete"]
        stats = dict(assigned=len(assigned), complete=len(complete))
        if complete:
            stats["metrics"] = {
                arm: {
                    method: metrics([row[method][arm] for row in complete])
                    for method in ("baseline", "candidate")
                }
                for arm in ARMS
            }
        groups[group] = stats
        x = np.arange(len(assigned))
        for arm, color in zip(ARMS, ("tab:blue", "tab:orange"), strict=True):
            for method, style in (("baseline", "--"), ("candidate", "-")):
                label = f"{arm}, {method}"
                axes[0, column].plot(
                    x, [
                        row[method][arm]["error_km"] if row["status"] == "complete" else np.nan
                        for row in assigned
                    ],
                    style, color=color, marker="o", label=label,
                )
                axes[1, column].plot(
                    x, [
                        row[method][arm]["posterior_rms_hz"]
                        if row["status"] == "complete" else np.nan for row in assigned
                    ],
                    style, color=color, marker="o", label=label,
                )
        for ax in axes[:, column]:
            ax.set_xticks(x, [row["label"] for row in assigned], rotation=45)
            ax.grid(alpha=0.2)
            for index, row in enumerate(assigned):
                if row["status"] != "complete":
                    ax.text(
                        index, 0.95, "unavailable", color="red", rotation=90, va="top",
                        transform=ax.get_xaxis_transform(),
                    )
        axes[0, column].set_title(f"{group}: {len(complete)}/{len(assigned)} complete")
        axes[0, column].axhline(1, color="gray", linewidth=1)
    axes[0, 0].set_ylabel("Position error (km)")
    axes[1, 0].set_ylabel("Posterior frequency RMS (Hz)")
    axes[0, 0].legend(fontsize=8)
    fig.savefig(HERE / "newer-comparison.png", dpi=160)
    stage_figure, stage_axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
    for ax, label in zip(stage_axes, protocol["development_labels"], strict=True):
        output = json.loads((HERE / "results" / f"{label}.json").read_text())["result"]
        case = next(row for row in cases if row["label"] == label)
        names = ["baseline", "region", *output["stages"]]
        for arm in ARMS:
            values = [
                case["baseline"][arm]["error_km"], output["regional"][arm]["error_km"],
                *[rows[arm]["error_km"] for rows in output["stages"].values()],
            ]
            ax.plot(names, values, marker="o", label=arm)
        ax.set(title=label, ylabel="Position error (km)")
        ax.tick_params(axis="x", rotation=35)
        ax.axhline(1, color="gray", linewidth=1)
        ax.grid(alpha=0.2)
        ax.legend()
    stage_figure.savefig(HERE / "development-stages.png", dpi=160)
    validation = [row for row in cases if row["group"] == "validation"]
    complete = all(row["status"] == "complete" for row in validation)
    gates = dict(all_assigned_scans_complete=complete)
    if complete:
        stats = groups["validation"]["metrics"]["fitted-c"]
        gates.update(
            mean_below_1km=stats["candidate"]["mean_km"] < 1,
            mean_no_worse=stats["candidate"]["mean_km"] <= stats["baseline"]["mean_km"],
            worst_within_10percent=(
                stats["candidate"]["worst_km"] <= 1.1 * stats["baseline"]["worst_km"]
            ),
            all_final_fitted_converged=all(
                row["candidate"]["fitted-c"]["stage"] == "drift-50"
                and row["candidate"]["fitted-c"]["converged"] for row in validation
            ),
        )
    summary = dict(cases=cases, groups=groups, gates=gates, passed=all(gates.values()))
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(dict(groups=groups, gates=gates, passed=summary["passed"]), indent=2))


if __name__ == "__main__":
    main()
