#!/usr/bin/env python3
"""Plot DS2 missing-model diagnostics from sealed inference and postseal evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main() -> None:
    inference = json.loads((HERE / "inference.json").read_text())
    evaluation = json.loads((HERE / "evaluation.json").read_text())
    scale = inference["common_plus_session_scale"]
    rows = evaluation["session_scale_lattice"]
    finalists = sorted(evaluation["residual_finalists"], key=lambda row: row["finalist_id"])

    figure, axes = plt.subplots(1, 2, figsize=(13.2, 5.2), constrained_layout=True)
    axis = axes[0]
    east = np.asarray([row["east_km"] for row in rows])
    north = np.asarray([row["north_km"] for row in rows])
    values = np.asarray([row["common_plus_session_scale_objective"] for row in rows])
    points = axis.scatter(east, north, c=values, cmap="viridis_r", s=220, edgecolor="black")
    winner = scale["winner"]
    baseline = scale["matched_rate_only_winner"]
    axis.scatter(
        [winner["east_km"]], [winner["north_km"]], marker="*", s=260, color="red",
        edgecolor="black", label="scale winner",
    )
    axis.scatter(
        [baseline["east_km"]], [baseline["north_km"]], marker="o", s=75,
        facecolor="none", edgecolor="white", linewidth=2.2, label="matched rate-only winner",
    )
    axis.set(
        title="Repaired session-scale local objective\n(lower is better; winner reaches grid edge)",
        xlabel="East of sealed fine rate winner (km)",
        ylabel="North of sealed fine rate winner (km)",
        aspect="equal",
    )
    axis.legend(loc="lower right", fontsize=8)
    figure.colorbar(points, ax=axis, label="Regularized selection objective")

    axis = axes[1]
    labels = [row["finalist_id"] for row in finalists]
    x = np.arange(len(labels))
    gaussian = np.asarray([row["gaussian_nll"] for row in finalists])
    robust = np.asarray([row["ar1_student_t_nll"] for row in finalists])
    gaussian_rank = np.argsort(np.argsort(gaussian)) + 1
    robust_rank = np.argsort(np.argsort(robust)) + 1
    axis.plot(x, gaussian_rank, "o-", linewidth=2, label="Gaussian rank")
    axis.plot(x, robust_rank, "s-", linewidth=2, label="AR(1)+Student-t rank")
    axis.set_xticks(x, labels, rotation=35, ha="right")
    axis.set(
        title="Fixed exact-finalist residual rerank\n(each model shown relative to its own winner)",
        ylabel="Reference-free likelihood rank (1 = best)",
        yticks=np.arange(1, len(finalists) + 1),
    )
    axis.invert_yaxis()
    axis.set_ylim(len(finalists) + 0.55, 0.45)
    axis.legend(loc="upper center", fontsize=8)
    for index, item in enumerate(finalists):
        axis.text(
            index,
            max(gaussian_rank[index], robust_rank[index]) + 0.25,
            f"{item['postseal_error_km']:.2f} km",
            ha="center",
            va="bottom",
            fontsize=7,
        )
    figure.suptitle(
        "DS2 · 20 whole Sept-24 captures · truth-free inference, reference added post-seal",
        fontsize=13,
    )
    figure.savefig(HERE / "missing-models-comparison.png", dpi=180)


if __name__ == "__main__":
    main()
