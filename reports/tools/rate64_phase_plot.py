"""Plot measured edge CFO before/after the independently derived convention."""

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.audit.read_text())
    bias = {"lower": -24857.954545454573, "upper": 31960.22727271919}
    results = []
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), sharey=True)
    for rx, ax in enumerate(axes):
        for edge, color, marker in (("lower", "#287a9b", "o"), ("upper", "#c87520", "s")):
            scans = [r for r in rows if r["rate"] == 10000000 and r["edge"] == edge]
            values = [
                lane["conditional"]["strong"]["quantiles"]["tracking_pilot_relative_hz"][1]
                for r in scans
                for key, lane in r["lanes"].items()
                if key.endswith(f":{rx}") and lane["conditional"]["strong"]["count"] > 0
            ]
            measured = float(np.mean(values))
            corrected = measured - bias[edge]
            ax.plot(
                [0, 1],
                np.array([measured, corrected]) / 1000,
                marker=marker,
                color=color,
                label=edge.capitalize(),
                linewidth=2,
                markersize=8,
            )
            for x, y in enumerate((measured, corrected)):
                label_y = -16 if x == 1 and edge == "lower" else 8
                ax.annotate(
                    f"{y / 1000:.1f}",
                    (x, y / 1000),
                    xytext=(8, label_y),
                    textcoords="offset points",
                    color=color,
                )
            results.append(
                dict(
                    rate=10000000,
                    receiver=rx,
                    edge=edge,
                    measured_hz=measured,
                    convention_corrected_hz=corrected,
                )
            )
        ax.set_title(f"RX{rx}")
        ax.set_xticks([0, 1], ["Published CFO", "Subtract derived edge bias"])
        ax.set_xlim(-0.2, 1.4)
        ax.grid(alpha=0.2)
        ax.legend()
    axes[0].set_ylabel("Pilot-relative CFO (kHz); acquired alias branches retained")
    fig.suptitle("10 MS/s: most of the edge displacement is a template frequency convention")
    fig.text(
        0.5,
        0.015,
        "Mean of scan/channel medians, strongest winners with margin > 0.4; "
        "different scans, not matched satellites.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))
    args.output.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output / "edge-phase-convention.png", dpi=170)
    (args.output / "edge-phase-observed.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
