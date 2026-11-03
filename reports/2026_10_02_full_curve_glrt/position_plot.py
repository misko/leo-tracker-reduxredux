import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent


def main():
    results = json.loads((ROOT / "position-results.json").read_text())
    audit = json.loads((ROOT / "position-audit.json").read_text())
    figure, axes = plt.subplots(1, 3, figsize=(17, 5))
    names = ["original", "fixed_rx", "profiled_rx"]
    labels = ["Track-stage\nsolution", "Raw GLRT\nfixed RX", "Raw GLRT\nrefitted RX"]
    colors = ["#64748b", "#2563eb", "#ea580c"]
    errors = [results["models"][name]["reference_error_km"] for name in names]
    axes[0].bar(labels, errors, color=colors)
    for index, error in enumerate(errors):
        axes[0].text(index, error + 0.1, f"{error:.2f} km", ha="center")
    axes[0].set_ylim(0, 6)
    axes[0].set_ylabel("Distance to saved reference (km)")
    original = results["models"]["original"]
    for field, label, marker in (
        ("training_loss", "Training loss", "o"),
        ("evaluation_loss", "Evaluation loss", "s"),
    ):
        values = [100 * (results["models"][name][field] / original[field] - 1) for name in names]
        axes[1].plot(np.arange(3), values, marker=marker, label=label)
    axes[1].set_xticks(np.arange(3), labels)
    axes[1].set_ylabel("Loss change from original (%) — lower is better")
    axes[1].axhline(0, color="#888888", linewidth=0.5)
    axes[1].legend()
    truth = np.array(audit["reference_point"])
    surface = audit["local_surface"]
    points = np.array([row["point"] for row in surface]) - truth
    costs = np.array([row["training_loss"] for row in surface]).reshape(11, 11)
    levels = axes[2].contourf(
        points[:, 0].reshape(11, 11),
        points[:, 1].reshape(11, 11),
        costs / 1000,
        levels=15,
        cmap="viridis",
    )
    figure.colorbar(levels, ax=axes[2], label="Profiled training loss / 1000")
    axes[2].plot(0, 0, "*", color="red", markersize=13, label="Saved reference")
    for name, color, label in zip(names, colors, labels, strict=True):
        point = np.array(results["models"][name]["point"]) - truth
        axes[2].plot(
            *point, "o", color=color, markeredgecolor="white", label=label.replace("\n", " ")
        )
    axes[2].set_xlabel("East of reference (km; prior-grid difference)")
    axes[2].set_ylabel("North of reference (km; prior-grid difference)")
    axes[2].legend(fontsize=7)
    figure.suptitle(
        "scan-fw-4971402f107cf8e1 — position search using raw GLRT frequency residuals\n"
        "Fixed 16-satellite shortlist; 3,192 groups; conditional experiment, not blind validation"
    )
    figure.tight_layout(rect=(0, 0, 1, 0.88))
    figure.savefig(ROOT / "position-comparison.png", dpi=170)


if __name__ == "__main__":
    main()
