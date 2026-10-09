"""Synthetic-only illustration of common-clock confounding and linear recovery."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from linear_contrast import fit_projected_contrasts, shrink_zero_sum_means

HERE = Path(__file__).resolve().parent


def main():
    generator = np.random.default_rng(8801)
    satellites = np.repeat(np.arange(3), 40)
    # Broadly overlapping, but different, satellite time coverage.
    times = np.concatenate([generator.normal(mean, 12, 40) for mean in (-15, 0, 15)])
    channel = np.tile(np.arange(2), 60)
    scenarios = (
        ("Common clock only", np.zeros(3), channel),
        ("Identifiable satellite contrast", np.array([-15.0, 0.0, 15.0]), channel),
        ("Satellite equals channel: unidentifiable", np.array([-15.0, 0.0, 15.0]), satellites),
    )
    figure, axes = plt.subplots(1, 3, figsize=(13, 4.6), sharey=True)
    receipt = dict(
        scope="Synthetic data only; no recordings or position-accuracy claim",
        seed=8801,
        pair_noise_scale_hz=5.0,
        prior_sigma_hz=30.0,
        observation_noise="None added: isolates deterministic geometry of the linear estimator",
        scenarios=[],
    )
    for axis, (title, truth, channels) in zip(axes, scenarios, strict=True):
        values = 30 + 0.8 * times + 4 * channels + truth[satellites]
        weights = np.full(len(values), 1 / 5.0**2)
        projected = fit_projected_contrasts(
            values, satellites, times, channels, sigma_hz=30, weights=weights
        )
        simple = shrink_zero_sum_means(values, satellites, sigma_hz=30, weights=weights)
        x = np.arange(3)
        axis.bar(
            x - 0.22, simple["contrasts_hz"], 0.22, color="#D08A35", label="Unadjusted shrinkage"
        )
        axis.bar(x, projected["contrasts_hz"], 0.22, color="#167D9A", label="Background projected")
        axis.scatter(x + 0.22, truth, color="#172A3A", marker="D", s=34, label="Injected contrast")
        axis.axhline(0, color="#777777", linewidth=0.7)
        axis.set_xticks(x, ["A", "B", "C"])
        axis.set_xlabel("Synthetic satellite")
        axis.set_title(title, fontsize=10)
        axis.text(
            0.03,
            0.96,
            f"Data rank {projected['data_rank']}/2",
            transform=axis.transAxes,
            va="top",
            fontsize=10,
        )
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=0.18)
        receipt["scenarios"].append(
            dict(
                name=title,
                injected_hz=truth.tolist(),
                unadjusted_hz=simple["contrasts_hz"].tolist(),
                projected_hz=projected["contrasts_hz"].tolist(),
                data_rank=projected["data_rank"],
                background_rank=projected["background_rank"],
                no_op=projected["no_op"],
            )
        )
    axes[0].set_ylabel("Full RX1−RX0 satellite contrast (Hz)")
    axes[0].set_ylim(-40, 40)
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
    figure.suptitle(
        "Synthetic demonstration: remove common time/channel effects first", fontsize=14
    )
    figure.tight_layout(rect=(0, 0.08, 1, 0.94))
    figure.savefig(HERE / "synthetic-confounding.png", dpi=160)
    plt.close(figure)
    (HERE / "synthetic-confounding.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
