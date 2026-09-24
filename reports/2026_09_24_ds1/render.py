"""Render every DS1 result, including failures, without selecting methods."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    path = HERE / "evaluation.json"
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        == path.with_suffix(".sha256").read_text().strip()
    )
    result = json.loads(path.read_text())
    dataset = json.loads((HERE / "dataset.json").read_text())
    rows = result["rows"]
    lookup = {(r["case_id"], r["prior"], r["model"]): r for r in rows}
    cases = dataset["cases"]
    labels = [f"{c['partition']} {c['group_id']} | {c['scan_count']} scans" for c in cases]
    fig, axes = plt.subplots(1, 3, figsize=(17, 11), sharey=True, constrained_layout=True)
    for ax, prior in zip(axes[:2], ("sacramento", "reno"), strict=True):
        for i, case in enumerate(cases):
            for model, color, offset in (
                ("baseline", "#2878b5", -0.12),
                ("shared_time", "#df7417", 0.12),
            ):
                row = lookup[(case["case_id"], prior, model)]
                if row["status"] == "completed":
                    ax.scatter(
                        row["reference_error_km"],
                        i + offset,
                        color=color,
                        s=30,
                        label=model.replace("_", " ") if i == 0 else None,
                    )
                else:
                    ax.text(
                        0.03,
                        i,
                        "input failure",
                        transform=ax.get_yaxis_transform(),
                        color="#777777",
                        va="center",
                    ) if model == "baseline" else None
        ax.set_xscale("log")
        ax.axvline(0.3, color="#999999", linestyle="--", label="300 m target")
        ax.set_title(prior.title())
        ax.set_xlabel("Reference position error (km; log scale)")
        ax.grid(axis="x", alpha=0.25)
        ax.legend(loc="upper right", fontsize=8)
    for i, case in enumerate(cases):
        for prior, marker, color, offset in (
            ("sacramento", "o", "#2878b5", -0.12),
            ("reno", "x", "#df7417", 0.12),
        ):
            row = lookup[(case["case_id"], prior, "shared_time")]
            if row["status"] == "completed":
                axes[2].scatter(
                    row["tau_s"],
                    i + offset,
                    marker=marker,
                    color=color,
                    label=prior if i == 0 else None,
                )
    axes[2].axvline(0, color="#999999", linestyle="--")
    axes[2].set_xlim(-5.2, 5.2)
    axes[2].set_title("Selected shared receive-time shift")
    axes[2].set_xlabel("Time shift (s; uncalibrated)")
    axes[2].legend(loc="upper right", fontsize=8)
    axes[0].set_yticks(range(len(cases)), labels, fontsize=8)
    axes[0].invert_yaxis()
    for ax in axes:
        for boundary in (3.5, 7.5, 11.5, 15.5):
            ax.axhline(boundary, color="#bbbbbb", linewidth=0.8)
    fig.suptitle(
        "DS1 · baseline versus shared-time local refinement\n"
        "Frozen 1/6/16/all prefixes · randomized inner holdouts · exposed regression cohort"
    )
    fig.savefig(HERE / "position_comparison.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    successful = []
    for case in cases:
        for prior in ("sacramento", "reno"):
            base, shifted = (
                lookup[(case["case_id"], prior, model)] for model in ("baseline", "shared_time")
            )
            if base["status"] != "completed" or shifted["status"] != "completed":
                continue
            successful.append((base, shifted))
            color = {"train": "#2878b5", "validation": "#df7417", "test": "#4a9d49"}[
                case["partition"]
            ]
            axes[0].scatter(base["reference_error_km"], shifted["reference_error_km"], color=color)
            axes[1].scatter(base["held_capped_rms_hz"], shifted["held_capped_rms_hz"], color=color)
    for ax, label in zip(
        axes, ("Position error (km)", "Randomized held capped RMS (Hz)"), strict=True
    ):
        if ax is axes[0]:
            ax.set_xscale("log")
            ax.set_yscale("log")
        limits = (*ax.get_xlim(), *ax.get_ylim())
        lo, hi = min(limits), max(limits)
        ax.plot([lo, hi], [lo, hi], "--", color="gray")
        ax.set_xlabel("Baseline: " + label)
        ax.set_ylabel("Shared time: " + label)
        ax.grid(alpha=0.2)
    fig.suptitle(
        "DS1 paired comparisons · below diagonal favors shared time\n"
        "Blue TRAIN; orange validation; green exposed TEST · correlated cases"
    )
    fig.savefig(HERE / "paired_comparison.png", dpi=170)
    plt.close(fig)

    summary = []
    for partition in ("train", "validation", "test"):
        pairs = [(b, s) for b, s in successful if b["partition"] == partition]
        summary.append(
            {
                "partition": partition,
                "completed_pairs": len(pairs),
                "position_improved": sum(
                    s["reference_error_km"] < b["reference_error_km"] for b, s in pairs
                ),
                "held_improved": sum(
                    s["held_capped_rms_hz"] < b["held_capped_rms_hz"] for b, s in pairs
                ),
                "baseline_median_error_km": float(
                    np.median([b["reference_error_km"] for b, _ in pairs])
                ),
                "shared_median_error_km": float(
                    np.median([s["reference_error_km"] for _, s in pairs])
                ),
            }
        )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    table = [
        "| Partition / UTC group | Scans | Sacramento baseline → time (km) | "
        "Reno baseline → time (km) | Time shift Sac / Reno (s) |",
        "|---|---:|---:|---:|---:|",
    ]
    for case in cases:
        columns, shifts = [], []
        for prior in ("sacramento", "reno"):
            b, s = (
                lookup[(case["case_id"], prior, model)] for model in ("baseline", "shared_time")
            )
            if b["status"] != "completed" or s["status"] != "completed":
                columns.append("Input failure")
                shifts.append("—")
            else:
                columns.append(f"{b['reference_error_km']:.3f} → {s['reference_error_km']:.3f}")
                shifts.append(f"{s['tau_s']:+.2f}")
        table.append(
            f"| {case['partition']} / {case['group_id']} | {case['scan_count']} | "
            + " | ".join(columns)
            + " | "
            + " / ".join(shifts)
            + " |"
        )
    (HERE / "RESULTS_TABLE.md").write_text("\n".join(table) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
