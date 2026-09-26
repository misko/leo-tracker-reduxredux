"""Show common-support robust-filter errors without treating them as phase truth."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    result = json.loads((HERE / "results.json").read_text())
    rows = [row for row in result["cached_even_to_odd"] if row["split"] == "evaluation"]
    points = []
    for row in rows:
        metrics = row["metrics"]
        a = metrics["trailing-20ms-line"]["common_rms_hz"]
        b = metrics["robust-jump-filter"]["common_rms_hz"]
        if a is not None and b is not None and a > 0 and b > 0:
            points.append((a, b))
    values = np.array(points)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    axes[0].scatter(values[:, 0], values[:, 1], alpha=.7, color="#245775")
    low, high = max(1, float(values.min()) * .8), float(values.max()) * 1.2
    axes[0].plot([low, high], [low, high], "--", color="gray")
    axes[0].set(xscale="log", yscale="log", xlim=(low, high), ylim=(low, high),
                xlabel="Trailing 20 ms line · odd-fold RMS (Hz)",
                ylabel="Robust jump filter · odd-fold RMS (Hz)",
                title=f"Same frames in {len(points)} evaluation receiver arcs")
    ratio = values[:, 1] / values[:, 0]
    axes[1].hist(ratio, bins=np.linspace(0, max(2, float(ratio.max())), 25), color="#709daa")
    axes[1].axvline(1, color="gray", ls="--")
    axes[1].set(xlabel="Jump / trailing-line common-frame RMS", ylabel="Receiver arcs",
                title="Below one favors the jump filter")
    fig.supxlabel("Fit past even-symbol CFO; evaluate unseen current odd-symbol CFO. Frequency consistency is not carrier-phase continuity.", fontsize=9)
    for suffix in ("png", "svg"):
        fig.savefig(HERE / f"common-support-comparison.{suffix}", dpi=160)
    plt.close(fig)
    (HERE / "REPORT.md").write_text(
        "# Robust-filter replay on common support\n\n"
        "The actual historical trailing-line, robust-jump, phase-gated-jump, V2 innovation "
        "and offline-smoother kernels are imported from `tools/report_d3_pilot_filter_prototypes.py`. "
        "The full cached lane trains on past even-symbol frame CFO and scores current odd-symbol CFO. "
        "Training support is a binary admission flag, matching the historical adapter; raw coherence "
        "is not passed as the support flag. Scored forecasts begin after the 20 ms acquisition is available.\n\n"
        f"There are {len(rows)} evaluation receiver arcs and {len(points)} with shared predictions "
        f"for both causal methods. Median per-arc common-frame RMS is {np.median(values[:,0]):.2f} Hz "
        f"for the trailing line and {np.median(values[:,1]):.2f} Hz for the robust jump filter. "
        "These are consistency errors against noisy odd-fold frequency observations, not truth CFO. "
        "The offline smoother uses future times and is reported separately in the JSON.\n\n"
        "The exact V2 and phase-gated comparison is limited to the bounded actual tracker checkpoints "
        "on development visits. It is not promoted to a full evaluation-cohort claim. All per-arc "
        "own-mask and common-mask counts remain in `results.json`; empty common support is not a zero error.\n\n"
        "![Common-support frequency prediction](common-support-comparison.png)\n"
    )


if __name__ == "__main__":
    main()
