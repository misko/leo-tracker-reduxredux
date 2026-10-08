"""Stratify saved clock residuals without satellite or position selection."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def stats(values, null):
    bins = np.arange(-113750, 114251, 500)
    counts, _ = np.histogram(values, bins)
    control, _ = np.histogram(null, bins)
    i = int(np.argmax(counts))
    return dict(
        n=len(values),
        peak_center_hz=float((bins[i] + bins[i + 1]) / 2),
        peak_count=int(counts[i]),
        null_at_peak=int(control[i]),
        within250=int(np.sum(abs(values) <= 250)),
    )


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["sha256"].items():
        assert hashlib.sha256((HERE.parent / name).read_bytes()).hexdigest() == digest
    output = HERE / "results.json"
    if output.exists():
        raise FileExistsError("Preserve first stratified audit")
    results = []
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    for k, label in enumerate(protocol["labels"]):
        data = json.loads(
            (HERE.parent / "2026_10_08_position_error_iter34/results" / f"{label}.json").read_text()
        )
        times = np.array([p["time_s"] for p in data["pairs"]])
        times -= times.min()
        rf = np.array([p["rf_hz"] for p in data["pairs"]])
        split = float(np.median(times))
        masks = [
            ("all", np.ones(len(times), dtype=bool)),
            ("early", times <= split),
            ("late", times > split),
        ]
        for frequency in sorted(set(rf)):
            for period, mask in masks[:3]:
                masks.append((f"RF={frequency:g}/{period}", mask & (rf == frequency)))
        for row in data["candidates"]:
            residual = np.asarray(row["residual_hz"])
            null = np.asarray(row["null_residual_hz"])
            groups = {name: stats(residual[mask], null[mask]) for name, mask in masks if mask.any()}
            results.append(
                dict(
                    label=label,
                    arm=row["arm"],
                    initialization=row["initialization"],
                    relative_sigma_s=row["relative_sigma_s"],
                    time_split_s=split,
                    groups=groups,
                )
            )
            if row["relative_sigma_s"] == 2 and row["arm"] == "fitted-c":
                j = int(row["initialization"] == "zero-timing-start")
                ax = axes[k, j]
                for frequency in sorted(set(rf)):
                    mask = rf == frequency
                    ax.scatter(
                        times[mask],
                        residual[mask],
                        s=8,
                        alpha=0.65,
                        label=f"{frequency / 1e9:.4f} GHz",
                    )
                ax.axvline(split, color="grey", linestyle="--")
                ax.axhline(0, color="grey", linewidth=0.7)
                ax.set(
                    ylim=(-15000, 15000),
                    xlabel="Seconds after first pair",
                    ylabel="Signed residual (Hz)",
                    title=f"{label} / {row['initialization']}",
                )
                ax.legend(fontsize=7)
    fig.suptitle(
        "Saved sigma 2 s fitted-c clock hypotheses: residuals by time and RF\n"
        "Zoom ±15 kHz; numerical tables retain the full alias interval"
    )
    fig.savefig(HERE / "time-rf.png", dpi=150)
    output.write_text(json.dumps(results, indent=2) + "\n")
    print(f"Audited {len(results)} hypotheses; no fits performed")


if __name__ == "__main__":
    main()
