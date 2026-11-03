import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent


def main():
    results = json.loads((ROOT / "results.json").read_text())
    linear = results["models"]["linear"]
    figure, axes = plt.subplots(1, 3, figsize=(16, 5))
    colors = ["#2563eb", "#ea580c"]
    for receiver, axis in enumerate(axes[:2]):
        parameters = linear["parameters"][str(receiver)]
        times = np.array([0, 300])
        axis.plot(
            times,
            (parameters["intercept_hz_at_150s"] + parameters["slope_hz_s"] * (times - 150)) / 1000,
            color=colors[receiver],
            label="Shared fitted line",
        )
        for accepted, marker in ((True, "o"), (False, "x")):
            tracks = [
                row
                for row in linear["tracks"]
                if row["receiver"] == receiver and row["accepted"] == accepted
            ]
            axis.scatter(
                [row["training_mean_time_s"] for row in tracks],
                [row["training_offset_hz"] / 1000 for row in tracks],
                marker=marker,
                color=colors[receiver] if accepted else "#999999",
                label="Accepted tracks" if accepted else "Unmatched tracks",
            )
        axis.set_title(f"RX{receiver}: {parameters['slope_hz_s']:.2f} Hz/s")
        axis.set_xlabel("Mean training-observation time (s)")
        axis.set_ylabel("Unwrapped offset at trial solution (kHz)")
        axis.set_xlim(0, 300)
        axis.grid(alpha=0.2)
        axis.legend(fontsize=8)
    names = list(results["models"])
    axes[2].bar(
        names,
        [results["models"][name]["reference_error_km"] for name in names],
        color=["#94a3b8", "#64748b", "#16a34a"],
    )
    axes[2].set_ylabel("Distance to saved reference (km)")
    axes[2].set_title("Conditional position comparison")
    for index, name in enumerate(names):
        row = results["models"][name]
        axes[2].text(
            index,
            row["reference_error_km"] + 0.1,
            f"{row['reference_error_km']:.2f} km\n{row['accepted_tracks']}/60 tracks",
            ha="center",
            fontsize=9,
        )
    axes[2].set_ylim(0, 9.5)
    figure.suptitle(
        "scan-fw-4971402f107cf8e1 — shared RX linear-offset prototype\n"
        "Fixed-site candidate shortlist; not blind localization or independent validation"
    )
    figure.tight_layout(rect=(0, 0, 1, 0.88))
    figure.savefig(ROOT / "comparison.png", dpi=160)


if __name__ == "__main__":
    main()
