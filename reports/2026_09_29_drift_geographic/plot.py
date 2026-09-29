"""Plot audited completed outcomes; pending arms stay explicitly excluded."""

import sys

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from study import HERE, read  # noqa: E402


def main(label):
    folder = HERE / label
    rows = [r for r in read(folder / "summary.json")["rows"] if r["status"] == "Audited"]
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained", sharex=True)
    x = np.arange(len(rows))
    axes[0].plot(x, [r["baseline_error_m"] / 1000 for r in rows], "o-", label="Original q020")
    axes[0].plot(x, [r["error_m"] / 1000 for r in rows], "x--", label="Drift corrected")
    axes[0].axhline(1, color="grey", linestyle=":", label="1 km")
    axes[0].set_ylabel("Nominal error (km)")
    axes[0].legend()
    axes[1].bar(x, [r["error_m"] - r["baseline_error_m"] for r in rows])
    axes[1].axhline(0, color="black", linewidth=0.7)
    axes[1].set_ylabel("Error change (m); negative improves")
    axes[1].set_xticks(x, [r["unit_id"].replace("_", " ") for r in rows], rotation=70, ha="right")
    fig.suptitle(f"Differential drift: {len(rows)}/54 combinations audited; incomplete comparison")
    for suffix in ("png", "svg"):
        fig.savefig(folder / ("comparison." + suffix), dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main(sys.argv[1])
