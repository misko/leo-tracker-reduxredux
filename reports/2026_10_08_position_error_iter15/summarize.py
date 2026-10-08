"""Report reference-directed profiles without treating them as operational fits."""

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
    fig, axes = plt.subplots(2, len(protocol["labels"]), figsize=(12, 8), layout="constrained")
    for col, label in enumerate(protocol["labels"]):
        document = json.loads((HERE / "results" / f"{label}.json").read_text())
        summary[label] = {}
        for arm in ("fitted-c", "zero-c"):
            steps = [r for r in document["rows"] if r["arm"] == arm and "step" in r]
            rows = [r["attempts"][-1] for r in steps]
            first, last = rows[0], rows[-1]
            complete = last["step"] == document["step_count"] and all(r["converged"] for r in rows)
            delta = {
                key: last["decomposition"][key] - first["decomposition"][key]
                for key in (
                    "data_nll",
                    "common_penalty",
                    "relative_penalty",
                    "clock_penalty",
                    "total",
                )
            }
            groups = {
                g: last["decomposition"]["grouped_nll"][g] - value
                for g, value in first["decomposition"]["grouped_nll"].items()
            }
            released = next(
                (
                    r
                    for r in document["rows"]
                    if r["arm"] == arm and r.get("phase") == "reference-released"
                ),
                None,
            )
            summary[label][arm] = dict(
                complete=complete,
                steps_completed=len(rows) - 1,
                steps_expected=document["step_count"],
                retries=sum(len(r["attempts"]) - 1 for r in steps),
                endpoint_delta=delta,
                grouped_delta=groups,
                released=released,
                original_error_km=document["fitted_selected"]["error_km"],
            )
            fraction = [r["step"] / document["step_count"] for r in rows]
            axes[0, col].plot(
                fraction, [r["objective"] - first["objective"] for r in rows], "o-", label=arm
            )
            keys = ("data_nll", "common_penalty", "relative_penalty", "clock_penalty")
            offset = -0.18 if arm == "fitted-c" else 0.18
            axes[1, col].bar(np.arange(4) + offset, [delta[k] for k in keys], width=0.36, label=arm)
        axes[0, col].set(
            title=label, xlabel="Fraction of path to reference", ylabel="Score minus start"
        )
        axes[1, col].set(
            xticks=np.arange(4),
            xticklabels=["Data", "Common time", "Relative time", "Clock"],
            ylabel="Endpoint minus start",
        )
        for ax in axes[:, col]:
            ax.axhline(0, color="black", linewidth=1)
            ax.grid(alpha=0.2)
            ax.legend()
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig.savefig(HERE / "reference-profiles.png", dpi=160)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
