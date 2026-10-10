"""Render sealed scalar handoff diagnostics; no model calls."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def render(directory=HERE):
    directory = Path(directory)
    data = json.loads((directory / "results/zero/result.json").read_text())
    fig, ax = plt.subplots(figsize=(8, 4.5), layout="constrained")
    for index, (region, saved) in enumerate(sorted(data["regions"].items())):
        h = saved["recovery"]["result"]["handoff"]
        values = [
            h["discovery_audit"]["stationarity"],
            h["fitted_audit"]["stationarity"],
            h["repair"]["fit"]["stationarity"],
        ]
        ax.plot(range(3), values, marker="o", label=region)
        ax.annotate(
            f"{h['repair']['objective_evaluations']} repair evaluations",
            (2, values[2]),
            xytext=(-8, 8 + index * 7),
            textcoords="offset points",
            ha="right",
            fontsize=9,
        )
    ax.axhline(0.001, color="black", linestyle="--", label="Qualification threshold 0.001")
    ax.set_yscale("log")
    ax.set_xlim(-0.15, 2.45)
    ax.set_xticks(range(3), ["Original, c=0", "Same state, c freed", "After bounded repair"])
    ax.set_ylabel("Scaled stationarity (KKT)")
    ax.set_title("All three zero-c optima fail the fitted-c handoff")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(loc="lower right")
    fig.savefig(directory / "handoff-diagnostics.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    render()
