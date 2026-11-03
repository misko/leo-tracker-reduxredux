"""Render the frozen detector comparison without changing thresholds or fits."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
METHODS = {
    "current_glrt64_margin": ("Current GLRT64 margin", "#1f2937"),
    "gaussian_glrt64": ("Gaussian GLRT64", "#2563eb"),
    "gaussian_glrt64_margin": ("Gaussian + control subtraction", "#38bdf8"),
    "adaptive_nmf64": ("Adaptive whitened filter", "#059669"),
    "segmented_glrt32": ("Two 32-symbol segments", "#d97706"),
    "differential_lag1": ("Lag-one differential", "#be185d"),
}
ENVIRONMENTS = {
    "white": "White Gaussian noise",
    "correlated_ar": "Correlated Gaussian noise (AR coefficient 0.85)",
    "coherent_tone": "Coherent tone interference (10 dB INR)",
    "phase_decoherence": "Within-frame phase random walk",
}


def descriptive_roc_point(null, signal, target_fpr=0.01) -> dict:
    """Evaluation-set ROC point; never a new calibrated operating threshold.

    Select an order statistic permitting at most floor(n*target_fpr) strict
    exceedances. Ties make this conservative rather than exceeding the target.
    """
    null, signal = np.asarray(null), np.asarray(signal)
    if (null.ndim != 1 or signal.ndim != 1 or not null.size or not signal.size
            or not np.all(np.isfinite(null)) or not np.all(np.isfinite(signal))
            or not 0 <= target_fpr < 1):
        raise ValueError("invalid finite samples or false-alarm target")
    allowed = int(np.floor(len(null) * target_fpr))
    threshold = float(np.sort(null)[-allowed - 1])
    return {"threshold_from_evaluation_nulls": threshold,
            "false_alarms": int(np.sum(null > threshold)), "null_count": len(null),
            "achieved_false_alarm_rate": float(np.mean(null > threshold)),
            "detections": int(np.sum(signal > threshold)), "signal_count": len(signal),
            "detection_rate": float(np.mean(signal > threshold))}


def render() -> None:
    summary = json.loads((HERE / "synthetic/pooled14/summary.json").read_text())
    figures = HERE / "figures"
    figures.mkdir(exist_ok=True)
    nulls = np.load(HERE / "synthetic/pooled14/heldout_null_scores.npz", allow_pickle=False)
    signals = np.load(HERE / "synthetic/pooled14/heldout_signal_scores.npz", allow_pickle=False)
    roc = {"scope": "Descriptive evaluation-set ROC; not frozen operating thresholds",
           "target_false_alarm_rate": 0.01, "environments": {}}
    for environment, results in summary["environments"].items():
        roc["environments"][environment] = {
            snr: {method: descriptive_roc_point(
                nulls[f"{environment}__{method}"],
                signals[f"{environment}__snr_{snr}__{method}__score"],
            ) for method in METHODS} for snr in results["signals"]
        }
    (HERE / "descriptive_roc.json").write_text(json.dumps(roc, indent=2, sort_keys=True) + "\n")
    for joint in (False, True):
        fig, axes = plt.subplots(2, 2, figsize=(13, 8.5), sharex=True, sharey=True)
        for ax, (environment, title) in zip(axes.flat, ENVIRONMENTS.items(), strict=True):
            data = summary["environments"][environment]
            snrs = sorted(float(snr) for snr in data["signals"])
            for method, (label, color) in METHODS.items():
                items = [data["signals"][str(int(snr))][method] for snr in snrs]
                key = "detected_and_cfo_within_1khz_rate" if joint else "rate"
                ax.plot(snrs, [item[key] for item in items], "o-", ms=4,
                        linewidth=1.7, color=color, label=label)
                if not joint:
                    ci = np.asarray([item["wilson_95"] for item in items])
                    ax.fill_between(snrs, ci[:, 0], ci[:, 1], color=color, alpha=0.06)
            ax.set_title(title, fontsize=11)
            ax.grid(alpha=0.17)
            ax.set_ylim(-0.025, 1.025)
            ax.set_xticks(snrs)
        for ax in axes[1]:
            ax.set_xlabel("Per-symbol correlation SNR (dB)")
        for ax in axes[:, 0]:
            ax.set_ylabel("Detection and CFO within 1 kHz" if joint else "Threshold exceedance")
        title = "Correct-frequency acquisition" if joint else "Conditional signal detection"
        fig.suptitle(f"{title}: 14 frames × 64 pilot symbols", fontsize=15, y=0.98)
        handles, labels = axes[0, 0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=3,
                   bbox_to_anchor=(0.5, 0.035), frameon=False, fontsize=10)
        fig.text(0.5, 0.013,
                 "Fixed acquired epoch; independent 1% target calibration per environment. "
                 "Achieved false-alarm rates vary; see report.",
                 ha="center", fontsize=9, color="#444444")
        fig.tight_layout(rect=(0, 0.115, 1, 0.945))
        stem = "correct_frequency" if joint else "detection"
        fig.savefig(figures / f"{stem}.png", dpi=160)
        fig.savefig(figures / f"{stem}.pdf")
        plt.close(fig)


if __name__ == "__main__":
    render()
