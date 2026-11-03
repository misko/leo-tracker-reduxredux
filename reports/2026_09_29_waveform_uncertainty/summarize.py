import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ARMS = ("cached_ols", "refined_ols", "cached_wls", "refined_wls", "cached_held")


def track_mean(row, arm):
    return float(np.mean([np.mean(h["arms"][arm]["frame_nmse"]) for h in row["held"]]))


def main():
    data = json.loads((HERE / "results.json").read_text())
    lines = [
        "| Dataset | Tracks | Held visits | Cached OLS | Refined OLS | Cached WLS | "
        "Refined WLS | Cached held | OLS refinement wins |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for ds, s in data["summary"].items():
        values = " | ".join(f"{s['mean_nmse'][arm]:.6f}" for arm in ARMS)
        lines.append(
            f"| {ds} | {s['returned']}/{s['planned']} | {s['held_visits']} | {values}"
            f" | {s['comparisons']['refinement_ols']['improved']} |"
        )
    lines += [
        "",
        "Equal-track means of held-visit pilot NMSE; lower is better.",
        "",
        "| Panel | RX | Status | Held visits | Cached OLS | Refined OLS | "
        "Cached WLS | Refined WLS | Cached held |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    valid = []
    for row in data["rows"]:
        prefix = f"| {row['panel_id']} | {row['receiver_id']} | {row['status']}"
        if row["status"] != "ok":
            lines.append(prefix + " | — | — | — | — | — | — |")
            continue
        valid.append(row)
        values = " | ".join(f"{track_mean(row, arm):.6f}" for arm in ARMS)
        lines.append(prefix + f" | {len(row['held'])} | {values} |")
    lines += [
        "",
        "| Panel | RX | Training visit | Residual Hz | Frame jackknife sigma Hz | "
        "Weight floor applied |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in valid:
        for t in row["training"]:
            lines.append(
                f"| {row['panel_id']} | {row['receiver_id']} | {t['visit']}"
                f" | {t['residual_frequency_hz']:.3f} | {t['sigma_hz']:.3f}"
                f" | {t['sigma_hz'] < 25} |"
            )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(13, 7), sharey=True)
    for ax, (a, b, title) in zip(
        axes,
        (
            ("cached_ols", "refined_ols", "Frequency refinement with equal weights"),
            ("refined_ols", "refined_wls", "Additional effect of uncertainty weighting"),
        ),
        strict=True,
    ):
        gains = [track_mean(r, a) - track_mean(r, b) for r in valid]
        ax.barh(
            np.arange(len(valid)), gains, color=["#25826c" if g > 0 else "#b44d3f" for g in gains]
        )
        ax.axvline(0, color="black", linewidth=0.7)
        ax.set_title(title)
        ax.set_xlabel("Held pilot NMSE reduction (positive is better)")
    axes[0].set_yticks(
        np.arange(len(valid)), [f"{r['panel_id']} RX{r['receiver_id']}" for r in valid]
    )
    fig.suptitle("Four training visits; up to two later held visits per track")
    fig.tight_layout()
    fig.savefig(HERE / "comparison.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
