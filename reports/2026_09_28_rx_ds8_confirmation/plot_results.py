"""Plot the fixed DS8 panel's equal-record held-period score contrasts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

FAMILIES = ("uniform", "causal")
COLORS = {"uniform": "#4477AA", "causal": "#CC6677"}


def _summary(document: dict, key: str) -> tuple[dict[str, float], float]:
    row = document["aggregate_equal_record"][key]
    values = {str(k): float(v) for k, v in row["records"].items()}
    return values, float(row["equal_record_mean"])


def _labels(readiness: dict) -> dict[str, str]:
    labels = {}
    for row in readiness["selected"]:
        rate = row["sample_rate_hz"] / 1e6
        rate_text = f"{rate:g}M"
        labels[row["session_id"]] = f"{rate_text}\n{row['session_id'].removeprefix('scan-fw-')}"
    return labels


def plot(results: dict, readiness: dict, output: Path) -> None:
    if results.get("schema") != "rx-ds8-geometry-score/v1" or results.get("status") != "complete":
        raise ValueError("results must be a complete DS8 geometry score")
    labels = _labels(readiness)
    sessions = list(results["eligible_sessions"])
    if set(sessions) != set(labels):
        raise ValueError("plot requires all four fixed readiness sessions to be eligible")
    sessions.sort(
        key=lambda sid: next(
            r["sample_rate_hz"] for r in readiness["selected"] if r["session_id"] == sid
        )
    )
    x = np.arange(len(sessions), dtype=float)
    fig, axes = plt.subplots(3, 2, figsize=(12.5, 12), constrained_layout=True)

    for column, family in enumerate(FAMILIES):
        ax = axes[0, column]
        for offset, arm in zip((-0.18, 0.0, 0.18), ("D", "S", "T"), strict=True):
            values, mean = _summary(results, f"held_frequency:{family}_{arm}-causal_reference")
            y = [values[sid] for sid in sessions]
            ax.scatter(x + offset, y, s=42, label=f"{arm} (mean {mean:+.3f})")
        ax.axhline(0, color="0.25", lw=1)
        ax.set_title(f"{family.capitalize()} frozen family vs causal reference")
        ax.set_ylabel("relative log score (nats/window)")
        ax.legend(frameon=False, fontsize=9)

        ax = axes[1, column]
        comparisons = (("D", "T−D"), ("S", "T−S"), ("T_swap", "T−swap"), ("T_reverse", "T−reverse"))
        for offset, (right, label) in zip(np.linspace(-0.24, 0.24, 4), comparisons, strict=True):
            values, mean = _summary(results, f"held_frequency:{family}_T-{right}")
            ax.scatter(
                x + offset, [values[sid] for sid in sessions], s=38, label=f"{label} ({mean:+.3f})"
            )
        ax.axhline(0, color="0.25", lw=1)
        ax.set_title(f"{family.capitalize()} family T contrasts")
        ax.set_ylabel("paired contrast (nats/window)")
        ax.legend(frameon=False, fontsize=9, ncol=2)

    gain, gain_mean = _summary(results, "held_frequency:causal_reference-uniform_reference")
    ax = axes[2, 0]
    ax.bar(x, [gain[sid] for sid in sessions], color="#228833", width=0.65)
    ax.axhline(0, color="0.25", lw=1)
    ax.set_title(f"Causal reference − uniform reference (mean {gain_mean:+.3f})")
    ax.set_ylabel("reference gain (nats/window)")

    ax = axes[2, 1]
    width = 0.34
    for offset, family in zip((-width / 2, width / 2), FAMILIES, strict=True):
        values, mean = _summary(results, f"held_frequency:{family}_T-causal_reference")
        ax.bar(
            x + offset,
            [values[sid] for sid in sessions],
            width=width,
            color=COLORS[family],
            label=f"{family} T (mean {mean:+.3f})",
        )
    ax.axhline(0, color="0.25", lw=1)
    ax.set_title("Frozen T families under the shared causal reference")
    ax.set_ylabel("relative log score (nats/window)")
    ax.legend(frameon=False, fontsize=9)

    for ax in axes.flat:
        ax.set_xticks(x, [labels[sid] for sid in sessions], fontsize=8)
        ax.grid(axis="y", color="0.9", lw=0.7)
    fig.suptitle("DS8 held-period receiver-geometry assessment", fontsize=15)
    fig.text(
        0.5,
        -0.01,
        "Points/bars are recording scores; parenthetical means weight recordings equally.",
        ha="center",
        fontsize=9,
    )
    fig.savefig(output.with_suffix(".png"), dpi=180, bbox_inches="tight")
    fig.savefig(output.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(json.loads(args.results.read_text()), json.loads(args.readiness.read_text()), args.output)


if __name__ == "__main__":
    main()
