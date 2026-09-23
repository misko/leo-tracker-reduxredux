"""Show all frozen validation configurations without hiding failed arms."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from export import HERE, digest
from selection import CONFIGURATIONS


def main():
    path = HERE / "results.json"
    assert digest(path).split(":")[1] == path.with_suffix(".sha256").read_text().strip()
    results = json.loads(path.read_text())
    groups = json.loads((HERE / "freeze.json").read_text())["groups"]
    figure, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    for col, group in enumerate(groups):
        name = group["utc_8h_start"]
        counts = [1, 6, 16, group["scan_count"]]
        for index, (model, scale) in enumerate(CONFIGURATIONS):
            label = "Baseline" if model == "baseline" else f"{model}, {scale:g} s"
            for row, metric in enumerate(("reference_error_km", "held_capped_rms_hz")):
                matrix = []
                for count in counts:
                    arms = [
                        a
                        for a in results["rows"]
                        if (a["group"], a["view_scan_count"], a["model"], a["scale_s"])
                        == (name, count, model, scale)
                    ]
                    matrix.append([a.get(metric, np.nan) for a in arms])
                array = np.asarray(matrix, dtype=float)
                mean = np.mean(array, axis=1)
                lo = np.min(array, axis=1)
                hi = np.max(array, axis=1)
                axes[row, col].plot(range(4), mean, "o-", color=f"C{index}", label=label)
                axes[row, col].fill_between(range(4), lo, hi, color=f"C{index}", alpha=0.15)
        axes[0, col].set_title(name)
        axes[0, col].axhline(0.3, color="gray", linestyle=":", label="300 m target")
        for row in range(2):
            axes[row, col].set_xticks(range(4), [str(c) for c in counts])
            axes[row, col].set_xlabel("Nested scan count")
            axes[row, col].grid(alpha=0.2)
    axes[0, 0].set_ylabel("Position error (km)")
    axes[1, 0].set_ylabel("Held capped RMS (Hz)")
    axes[0, 1].legend(fontsize=8)
    figure.suptitle(
        "Frozen validation · lines average two starts; bands show their range\n"
        "Missing metrics remain gaps; eligibility is reported separately"
    )
    figure.savefig(HERE / "validation.png", dpi=160)
    summary = results["selection"]["configurations"]
    lines = [
        "| Configuration | Eligible | Mean regime error (km) | Worst error (km) |",
        "|---|---|---:|---:|",
    ]
    for item in summary:
        label = f"{item['model']} / {item['scale_s']:g} s"
        mean = f"{item['mean_regime_error_km']:.3f}" if item["eligible"] else "—"
        worst = f"{item['worst_error_km']:.3f}" if item["eligible"] else "—"
        lines.append(f"| {label} | {item['eligible']} | {mean} | {worst} |")
    (HERE / "selection_table.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
