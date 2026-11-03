import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from common import ROOT, Data, circular


def main():
    result = json.loads((ROOT / "results.json").read_text())
    anchors = json.loads((ROOT / "anchors.json").read_text())
    extensions = json.loads((ROOT / "extensions.json").read_text())
    data = Data()
    figure, axes = plt.subplots(3, 2, figsize=(14, 10), sharex=True, sharey=True)
    for stage_index, (name, stage) in enumerate(result["stages"].items()):
        assignment = anchors if name == "anchors" else extensions
        rows = np.asarray(assignment["rows"], dtype=int)
        satellites = np.asarray(assignment["satellites"], dtype=int)
        prediction, visible = data.predict(np.asarray(stage["fit"]["parameters"]), rows, satellites)
        error = circular(data.measured[rows], prediction)
        for receiver in (0, 1):
            axis = axes[stage_index, receiver]
            chosen = (data.receiver[rows] == receiver) & visible
            axis.scatter(
                data.times[rows[chosen]],
                error[chosen],
                c=satellites[chosen],
                cmap="turbo",
                vmin=0,
                vmax=63,
                s=8,
                alpha=0.7,
            )
            axis.axhline(0, color="black", linewidth=0.7)
            for boundary in (-1000, 1000):
                axis.axhline(boundary, color="red", linestyle="--", linewidth=0.6)
            axis.set_title(
                f"{name}: RX{receiver}; reference error {stage['reference_error_km']:.3f} km"
            )
            axis.set_xlim(0, 300)
            axis.set_ylim(-2200, 2200)
            axis.grid(alpha=0.15)
            axis.set_ylabel("Measured − assigned prediction (Hz)")
            axis.set_xlabel("Receive time (s)")
    figure.suptitle(
        "scan-fw-4971402f107cf8e1 — coherent-association prototypes\n"
        "Colors: candidate satellite IDs; real measured frequencies, no synthetic snapping; "
        "all-data conditional fits"
    )
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(ROOT / "residual-comparison.png", dpi=160)
    figure.savefig(ROOT / "residual-comparison.svg")


if __name__ == "__main__":
    main()
