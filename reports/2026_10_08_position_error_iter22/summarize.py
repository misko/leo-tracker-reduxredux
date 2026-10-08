"""Summarize oracle profile evidence without selecting operational estimates."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    summary = {}
    figure, axes = plt.subplots(2, 4, figsize=(17, 7), layout="constrained")
    for column, label in enumerate(protocol["cases"]):
        document = json.loads((HERE / "results" / f"{label}.json").read_text())
        summary[label] = {}
        for arm, color in (("fitted-c", "tab:blue"), ("zero-c", "tab:orange")):
            steps = [row for row in document["rows"] if row["arm"] == arm and "step" in row]
            fitted = [row["attempts"][-1] for row in steps]
            releases = [row for row in document["rows"] if row["arm"] == arm and "phase" in row]
            complete = (
                len(fitted) == document["step_count"] + 1
                and all(row["converged"] for row in fitted)
            )
            first, last = fitted[0]["decomposition"], fitted[-1]["decomposition"]
            item = dict(
                profile_complete=complete, selected_error_km=document["fitted_selected"]["error_km"]
            )
            if complete:
                item["reference_minus_selected_fixed"] = {
                    name: last[name] - first[name]
                    for name in (
                        "total", "data_nll", "clock_penalty", "common_penalty", "relative_penalty"
                    )
                }
                contributions = [
                    dict(document["groups"][key], delta_nll=value - first["grouped_nll"][key])
                    for key, value in last["grouped_nll"].items()
                ]
                item["groups"] = sorted(contributions, key=lambda row: -row["delta_nll"])
            if releases:
                release = releases[0]
                item["release"] = {key: release[key] for key in (
                    "error_km", "converged", "stationarity", "objective"
                )}
                item["release_vs_original_objective"] = (
                    release["objective"] - document["fitted_selected"]["objective"]
                    if arm == "fitted-c" else None
                )
            summary[label][arm] = item
            x = np.array([row["step"] for row in steps]) / document["step_count"]
            axes[0, column].plot(
                x, [row["decomposition"]["total"] - first["total"] for row in fitted],
                marker="o", color=color, label=arm,
            )
            axes[1, column].plot(
                x, [row["decomposition"]["data_nll"] - first["data_nll"] for row in fitted],
                marker="o", color=color, label=f"{arm}: data",
            )
            axes[1, column].plot(
                x, [
                    row["decomposition"]["clock_penalty"] - first["clock_penalty"] for row in fitted
                ],
                "--", color=color, label=f"{arm}: clock",
            )
        axes[0, column].set_title(label)
        for ax in axes[:, column]:
            ax.axhline(0, color="gray", linewidth=1)
            ax.set_xlabel("Path: selected position (0) → reference (1)")
            ax.grid(alpha=0.2)
    axes[0, 0].set_ylabel("Total objective change (lower is better)")
    axes[1, 0].set_ylabel("Component objective change")
    axes[0, 0].legend(fontsize=8)
    axes[1, 0].legend(fontsize=8)
    figure.savefig(HERE / "reference-profiles.png", dpi=160)
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    concise = {
        label: {arm: {k: v for k, v in row.items() if k != "groups"}
                for arm, row in arms.items()} for label, arms in summary.items()
    }
    print(json.dumps(concise, indent=2))


if __name__ == "__main__":
    main()
