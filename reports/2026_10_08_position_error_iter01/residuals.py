"""Development residual diagnostics; associations/weights frozen at fitted state."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from probe import load

HERE = Path(__file__).resolve().parent


def run(label):
    case, document, objective, vector = load(label)
    observations = objective.observations
    _, _, terms = objective.evaluate(vector)
    mass = terms.responsibilities.sum(axis=1)
    residual = np.sum(terms.responsibilities * terms.residual_hz, axis=1) / np.maximum(mass, 1e-12)
    frequency = (observations.rf_hz - observations.rf_center_hz) / 1e9
    centered_time = observations.times_s - observations.time_center_s
    rows, satellites = [], []
    figure, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
    for rx in (0, 1):
        mask = (observations.receiver == rx) & (mass >= 0.8)
        design = np.column_stack([np.ones(mask.sum()), centered_time[mask], frequency[mask]])
        weights = np.sqrt(mass[mask])
        coefficients = np.linalg.lstsq(
            design * weights[:, None], residual[mask] * weights, rcond=None
        )[0]
        bins = []
        for channel in np.unique(observations.channel[mask]):
            selected = mask & (observations.channel == channel)
            bins.append(
                {
                    "channel": int(channel),
                    "rf_ghz": float(np.mean(observations.rf_hz[selected]) / 1e9),
                    "windows": int(selected.sum()),
                    "mean_hz": float(np.average(residual[selected], weights=mass[selected])),
                    "median_hz": float(np.median(residual[selected])),
                }
            )
        rows.append(
            {
                "receiver": rx,
                "linear_coefficients_offset_time_rf": coefficients.tolist(),
                "bins": bins,
                "supported_windows": int(mask.sum()),
            }
        )
        axes[rx].scatter(observations.rf_hz[mask] / 1e9, residual[mask], s=3, alpha=0.12)
        axes[rx].plot(
            [b["rf_ghz"] for b in bins], [b["mean_hz"] for b in bins], "o-", color="black"
        )
        axes[rx].axhline(0, color="gray", linewidth=0.8)
        axes[rx].set(
            xlabel="RF (GHz)",
            ylabel="Responsibility-weighted residual (Hz)",
            title=f"RX{rx}: residual RF slope {coefficients[2]:.1f} Hz/GHz",
        )
        axes[rx].grid(alpha=0.2)
    figure.suptitle(f"{label}: residuals at selected fitted-c estimate")
    folder = HERE / "residuals"
    folder.mkdir(exist_ok=True)
    figure.savefig(folder / f"{label}.png", dpi=150)
    plt.close(figure)
    for index, number in enumerate(objective.bank.numbers):
        weight = terms.responsibilities[:, index]
        satellites.append(
            {
                "number": int(number),
                "mass": float(weight.sum()),
                "timing_s": float(vector[7] + (objective.basis @ vector[8:])[index]),
                "mean_residual_hz": float(
                    np.sum(weight * terms.residual_hz[:, index]) / max(weight.sum(), 1e-12)
                ),
            }
        )
    result = {
        "label": label,
        "receivers": rows,
        "satellites": satellites,
        "warning": "Conditional residual diagnostics, not causal hardware attribution",
    }
    (folder / f"{label}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(label, [round(r["linear_coefficients_offset_time_rf"][2], 2) for r in rows], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("labels", nargs="+")
    for label in parser.parse_args().labels:
        run(label)
