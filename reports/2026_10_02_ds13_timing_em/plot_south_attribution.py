"""Visualize loss attribution and the residual structure of dominant satellites."""

from __future__ import annotations

import json

import numpy as np
from finite_set_fit import assert_snapshot_unchanged
from prepare_scans import ROOT


def binned_means(times, values, weights, width_s=10.):
    bins = np.floor(np.asarray(times) / width_s).astype(int)
    output = []
    for time_bin in np.unique(bins):
        mask = bins == time_bin
        total = np.sum(weights[mask])
        if total >= 3:
            output.append((np.sum(times[mask] * weights[mask]) / total,
                           np.sum(values[mask] * weights[mask]) / total))
    return np.asarray(output).reshape(-1, 2)


def plot():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sessions = json.loads((ROOT / "position-profile-protocol.json").read_text())["sessions"]
    figure, axes = plt.subplots(2, 3, figsize=(16, 10))
    residual_figure, residual_axes = plt.subplots(2, 2, figsize=(14, 9))
    for scan_index, session in enumerate(sessions):
        directory = ROOT / "south-point-attribution" / f"{session}-pruned"
        summary = json.loads((directory / "summary.json").read_text())
        assert_snapshot_unchanged(summary["source_hashes"])
        data = np.load(directory / "evidence.npz")
        for variant in ("current", "pruned"):
            other = np.load(ROOT / "south-point-attribution" / f"{session}-{variant}" /
                            "evidence.npz")
            order = np.argsort(other["group_time_s"])
            axes[scan_index, 0].plot(other["group_time_s"][order],
                                     np.cumsum(other["group_gain"][order]), label=variant)
        axes[scan_index, 0].set_title(f"...{session[-4:]}: accumulated data gain")
        axes[scan_index, 0].set_xlabel("Receive time (s)")
        axes[scan_index, 0].set_ylabel("South advantage in log likelihood")
        axes[scan_index, 0].legend()
        satellites = list(reversed(summary["satellites"]))
        gains = [satellite["path_attributed_data_gain"] for satellite in satellites]
        axes[scan_index, 1].barh([str(satellite["catalog_number"]) for satellite in satellites],
                                 gains, color=["C2" if gain >= 0 else "C3" for gain in gains])
        axes[scan_index, 1].set_title("Per-satellite contribution, pruned model")
        axes[scan_index, 1].set_xlabel("Path-attributed data gain")
        winner = data["truth_posterior"].argmax(axis=1)
        rows = np.arange(len(winner))
        chosen = data["stable_confident"]
        residual = data["truth_residual"][rows, winner]
        change = (data["south_prediction"] - data["truth_prediction"])[rows, winner]
        axes[scan_index, 2].scatter(residual[chosen], change[chosen], s=6, alpha=.22)
        axes[scan_index, 2].axhline(0, color="gray", linewidth=.7)
        axes[scan_index, 2].axvline(0, color="gray", linewidth=.7)
        axes[scan_index, 2].set_title("Same confident identity at both positions")
        axes[scan_index, 2].set_xlabel("Observed minus truth prediction (Hz)")
        axes[scan_index, 2].set_ylabel("South minus truth prediction (Hz)")
        for column, satellite in enumerate(summary["satellites"][:2]):
            satellite_column = np.flatnonzero(
                data["catalog_numbers"] == satellite["catalog_number"])[0]
            axis = residual_axes[scan_index, column]
            weight = data["truth_posterior"][:, satellite_column]
            for receiver in (0, 1):
                mask = (data["receiver"] == receiver) & (weight >= .8)
                times = data["times"][mask]
                truth = data["truth_residual"][mask, satellite_column]
                south = data["south_residual"][mask, satellite_column]
                axis.scatter(times, truth, s=6, color=f"C{receiver}", alpha=.15)
                for values, style, name in ((truth, "-", "truth"), (south, "--", "south")):
                    bins = binned_means(times, values, weight[mask])
                    axis.plot(bins[:, 0], bins[:, 1], style, color=f"C{receiver}",
                              label=f"RX{receiver} {name}, 10s means")
            axis.axhline(0, color="black", linewidth=.7)
            axis.set_title(f"...{session[-4:]} / NORAD {satellite['catalog_number']} / "
                           f"gain {satellite['path_attributed_data_gain']:.2f}")
            axis.set_xlabel("Receive time (s)")
            axis.set_ylabel("Frequency residual (Hz)")
            axis.legend(fontsize=8)
            axis.grid(alpha=.2)
    for axis in axes.flat:
        axis.grid(alpha=.2)
    figure.suptitle("Why south scores better: stored GLRT peak likelihood, not full GLRT surfaces")
    residual_figure.suptitle("Dominant satellites: coherent residual trends remain at truth")
    figure.tight_layout()
    residual_figure.tight_layout()
    destination = ROOT / "south-point-attribution"
    figures = (("loss-attribution", figure), ("dominant-satellite-residuals", residual_figure))
    for name, current in figures:
        current.savefig(destination / f"{name}.png", dpi=150)
        current.savefig(destination / f"{name}.svg")
        plt.close(current)


if __name__ == "__main__":
    plot()
