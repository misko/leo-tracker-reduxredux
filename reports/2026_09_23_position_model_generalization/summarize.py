"""Common reporting of conditional model comparisons; never selects an estimate."""

import hashlib
import json
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure


def main():
    root = Path(__file__).resolve().parent
    source = root.parent / "2026_09_23_regularized_position/results.json"
    doc = json.loads(source.read_text())
    figure = Figure(figsize=(11, 4.8), layout="constrained")
    frequency, position = figure.subplots(1, 2)
    summary = []
    for index, (tier, rows) in enumerate(doc["retrospective_validation"].items()):
        regularized = np.array(
            [r["selected_regularized"]["reserved_capped_weighted_rms_hz"] for r in rows]
        )
        baseline = np.array([r["lambda_0"]["reserved_capped_weighted_rms_hz"] for r in rows])
        error = np.array([r["selected_regularized"]["reference_error_km"] for r in rows])
        baseline_error = np.array([r["lambda_0"]["reference_error_km"] for r in rows])
        delta = regularized - baseline
        row = {
            "tier": tier,
            "window_count": len(rows),
            "mean_window_reserved_rms_regularized_hz": float(regularized.mean()),
            "mean_window_reserved_rms_baseline_hz": float(baseline.mean()),
            "median_paired_rms_change_hz": float(np.median(delta)),
            "windows_with_lower_regularized_rms": int(np.sum(delta < 0)),
            "regularized_median_error_km": float(np.median(error)),
            "baseline_median_error_km": float(np.median(baseline_error)),
            "windows": rows,
        }
        summary.append(row)
        jitter = np.linspace(-0.15, 0.15, len(rows)) if len(rows) > 1 else np.array([0])
        frequency.scatter(index + jitter, delta, alpha=0.7, s=22)
        frequency.plot([index - 0.2, index + 0.2], [np.median(delta)] * 2, "k-", linewidth=2)
        position.plot(index - 0.06, np.median(baseline_error), "o", color="tab:blue")
        position.plot(index + 0.06, np.median(error), "x", color="tab:orange", markersize=9)
    ticks = [
        f"{n} scans\n{len(rows)} windows"
        for n, rows in zip((1, 6, 18, 48), doc["retrospective_validation"].values(), strict=True)
    ]
    for ax in (frequency, position):
        ax.set_xticks(range(4), ticks)
        ax.grid(axis="y", alpha=0.3)
    frequency.axhline(0, color="black", linestyle="--", linewidth=1)
    frequency.set_ylabel("Regularized − baseline reserved RMS (Hz)")
    frequency.set_title("Negative favours regularization\nDots: paired windows; bars: median")
    position.plot([], [], "o", color="tab:blue", label="Unregularized")
    position.plot([], [], "x", color="tab:orange", label="Regularized")
    position.axhline(0.3, color="black", linestyle="--", label="300 m target")
    position.set_ylabel("Median reference error of selected fixed point (km)")
    position.set_title("Three existing geographic points only\nNo independent spatial recovery")
    position.legend()
    figure.suptitle(
        "Retrospective validation · training-only point selection\n"
        "Duration tiers reuse recordings; long-duration sample count is one"
    )
    figure.savefig(root / "regularized_comparison.png", dpi=160)
    result = {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "interpretation": "Conditional fixed-point mechanism diagnostic; not new position fits",
        "tiers": summary,
    }
    (root / "regularized_summary.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    main()
