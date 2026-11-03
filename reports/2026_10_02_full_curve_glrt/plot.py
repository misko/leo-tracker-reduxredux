import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matching import ALIAS_HZ, circular_residual
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent


def wrapped_curves(times, values, elevations):
    folded = circular_residual(values, 0) / 1000
    jumps = np.c_[
        np.zeros(len(values), dtype=bool), np.abs(np.diff(folded, axis=1)) > ALIAS_HZ / 2000
    ]
    folded[(elevations < 0) | jumps] = np.nan
    return np.stack([np.broadcast_to(times, folded.shape), folded], axis=-1)


def main():
    data = np.load(ROOT / "inputs.npz")
    assignments = np.load(ROOT / "assignments.npz")
    metadata = json.loads((ROOT / "inputs.json").read_text())
    selected_numbers = data["selected_numbers"]
    colors = plt.get_cmap("tab20")(np.arange(len(selected_numbers)))
    selected_indices = [
        int(np.flatnonzero(data["numbers"] == number)[0]) for number in selected_numbers
    ]
    figure, axes = plt.subplots(4, 2, figsize=(17, 14), sharex=True, sharey=True)
    for channel in range(1, 5):
        for receiver in (0, 1):
            axis = axes[channel - 1, receiver]
            lane = (data["channel"] == channel) & (data["receiver"] == receiver)
            rf = float(np.median(data["rf"][lane]))
            parameters = metadata["solution"]["parameters"][str(receiver)]
            offset = parameters["intercept_hz_at_150s"] + parameters["slope_hz_s"] * (
                data["nodes"] - 150
            )
            curves = wrapped_curves(
                data["nodes"], data["fractions"] * rf + offset, data["elevations"]
            )
            axis.add_collection(
                LineCollection(curves, colors="#bbbbbb", linewidths=0.3, alpha=0.2, rasterized=True)
            )
            axis.add_collection(
                LineCollection(curves[selected_indices], colors=colors, linewidths=1, alpha=0.85)
            )
            axis.scatter(
                data["times"][lane],
                circular_residual(data["measured"][lane], 0) / 1000,
                color="#666666",
                s=3,
                alpha=0.45,
            )
            rows = assignments["rows"]
            chosen = assignments["coherent"] & lane[rows]
            axis.scatter(
                data["times"][rows[chosen]],
                circular_residual(data["measured"][rows[chosen]], 0) / 1000,
                c=colors[assignments["satellites"][chosen]],
                s=12,
            )
            axis.set_title(f"CH{channel} / RX{receiver}", loc="left")
            axis.set_xlim(0, 300)
            axis.set_ylim(-ALIAS_HZ / 2000, ALIAS_HZ / 2000)
            axis.set_ylabel("CFO modulo alias (kHz)")
            axis.grid(alpha=0.15)
    for axis in axes[-1]:
        axis.set_xlabel("Time within scan (s)")
    handles = [
        Line2D([], [], color=colors[index], label=str(number))
        for index, number in enumerate(selected_numbers)
    ]
    figure.legend(
        handles=handles,
        loc="lower center",
        ncol=8,
        title="16 previously selected candidate satellites",
    )
    figure.suptitle(
        f"scan-fw-4971402f107cf8e1 — all {len(data['numbers'])} visible TLE curves + stored GLRT\n"
        "Frozen position and RX offsets; gray curves = full catalogue; "
        "colored points = conservative curve-supported groups",
        fontsize=14,
    )
    figure.tight_layout(rect=(0, 0.085, 1, 0.945))
    figure.savefig(ROOT / "all-tle-glrt.png", dpi=150)
    figure.savefig(ROOT / "all-tle-glrt.pdf")

    target = int(np.flatnonzero(selected_numbers == 66891)[0])
    parameters = metadata["solution"]["parameters"]["0"]
    native_prediction = (
        data["exact_fraction"][target] * data["rf"]
        + parameters["intercept_hz_at_150s"]
        + parameters["slope_hz_s"] * (data["times"] - 150)
    )
    residual = circular_residual(data["measured"], native_prediction)
    lane = (data["channel"] == 1) & (data["receiver"] == 0)
    display = lane & (np.abs(residual) < 8000)
    target_rows = assignments["target_rows"][assignments["target_coherent"]]
    old_rows = target_rows[data["old_group"][target_rows]]
    new_rows = target_rows[~data["old_group"][target_rows]]
    curve_index = selected_indices[target]
    rf = float(np.median(data["rf"][lane]))
    predicted_curve = (
        data["fractions"][curve_index] * rf
        + parameters["intercept_hz_at_150s"]
        + parameters["slope_hz_s"] * (data["nodes"] - 150)
    )
    detail, detail_axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
    detail_axes[0].plot(
        data["nodes"],
        predicted_curve / 1000,
        color="black",
        label="Full TLE 66891 + frozen RX0 line",
    )
    detail_axes[0].scatter(
        data["times"][display],
        (native_prediction[display] + residual[display]) / 1000,
        s=8,
        color="#aaaaaa",
        label="GLRT within ±8 kHz (alias-lifted)",
    )
    for rows, color, marker, label in (
        (old_rows, "#2563eb", "o", "Previously tracked source groups"),
        (new_rows, "#16a34a", "D", "New source groups outside all prior tracks"),
    ):
        detail_axes[0].scatter(
            data["times"][rows],
            (native_prediction[rows] + residual[rows]) / 1000,
            s=22,
            color=color,
            marker=marker,
            label=label,
        )
        detail_axes[1].scatter(
            data["times"][rows], residual[rows], s=22, color=color, marker=marker, label=label
        )
    detail_axes[1].scatter(
        data["times"][display], residual[display], s=5, color="#aaaaaa", alpha=0.4, zorder=0
    )
    detail_axes[1].axhline(0, color="black", linewidth=1)
    for gate in (-1000, 1000):
        detail_axes[1].axhline(gate, color="#dc2626", linestyle="--", linewidth=1)
    for axis in detail_axes:
        axis.set_xlim(170, 285)
        axis.axvspan(219.4, 228.55, color="#fbbf24", alpha=0.2, label="Old track gap")
        axis.grid(alpha=0.2)
    window = (data["nodes"] >= 170) & (data["nodes"] <= 285)
    detail_axes[0].set_ylim(
        predicted_curve[window].min() / 1000 - 8, predicted_curve[window].max() / 1000 + 8
    )
    detail_axes[0].set_ylabel("Alias-lifted CFO (kHz)")
    detail_axes[0].legend(fontsize=8)
    detail_axes[1].set_ylabel("GLRT − full TLE prediction (Hz)")
    detail_axes[1].set_ylim(-2000, 2500)
    detail_axes[1].set_xlabel("Time within scan (s)")
    detail.suptitle(
        "CH1 / RX0 — full-curve support for candidate 66891\n"
        "Nonexclusive support: crossings and competing satellite identities remain unresolved"
    )
    detail.tight_layout(rect=(0, 0, 1, 0.93))
    detail.savefig(ROOT / "66891-full-curve.png", dpi=170)


if __name__ == "__main__":
    main()
