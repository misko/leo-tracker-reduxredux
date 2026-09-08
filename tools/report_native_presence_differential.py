#!/usr/bin/env python3
"""Render saved ARM runtime, development association, and tone-control evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from tools.report_native_presence_power import quality_counts


def tone_counts(rows, rate):
    controls = [
        r for r in rows if r["rate_hz"] == rate and r["provenance"]["kind"] == "tone_control"
    ]
    return (
        len(controls),
        sum(r["raw"]["detected"] for r in controls),
        sum(r["residual"]["detected"] for r in controls),
    )


def render(directory: Path, output: Path):
    if output.exists() or any(
        output.resolve().is_relative_to(Path(p)) for p in ("/mnt/qnap01", "/srv/bulk/leo")
    ):
        raise ValueError("new non-archive figure output required")
    summary = json.loads((directory / "arm-wide-summary.json").read_text())
    if not summary["all_candidate_outputs_match_desktop"]:
        raise ValueError("ARM parity must be established before plotting runtime")
    quality = json.loads((directory / "wide-native-ci16/results.json").read_text())
    tones = json.loads((directory / "tone-nuisance/results.json").read_text())
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
    rates, x = [2500000, 5000000], np.arange(2)
    for offset, field, label, color in (
        (-0.18, "total_cpu_ms", "Warmed CPU p99", "#207f87"),
        (0.18, "total_wall_ms", "Warmed wall p99", "#659cce"),
    ):
        values = [summary["rates"][str(r)]["warmed"][field]["p99"] for r in rates]
        bars = axes[0].bar(x + offset, values, width=0.34, label=label, color=color)
        axes[0].bar_label(bars, fmt="%.1f", padding=3)
    axes[0].axhline(100, linestyle="--", color="#a95336", label="100 ms CPU target")
    axes[0].set(title="ARM: identical CI16 detector build", ylabel="Milliseconds", ylim=(0, 140))
    axes[0].legend(loc="upper left", fontsize=8)
    counts = np.array([quality_counts(quality, summary["variant"], r) for r in rates])
    bottom = np.zeros(2)
    for column, label, color in (
        (0, "Reference-associated", "#207f87"),
        (1, "Positive; CFO/time mismatch", "#d9a24a"),
        (2, "No passing candidate", "#a95336"),
    ):
        bars = axes[1].bar(x, counts[:, column], bottom=bottom, color=color, label=label)
        axes[1].bar_label(
            bars,
            labels=[str(n) if n else "" for n in counts[:, column]],
            label_type="center",
            color="white",
            weight="bold",
        )
        bottom += counts[:, column]
    axes[1].set(
        title="Development RF: first 20 ms", ylabel="Reference-positive probes", ylim=(0, 17)
    )
    axes[1].legend(loc="upper left", fontsize=8)
    control = np.array([tone_counts(tones, r) for r in rates])
    for offset, column, label, color in (
        (-0.18, 1, "Unconditioned", "#a95336"),
        (0.18, 2, "After tone fitting", "#207f87"),
    ):
        bars = axes[2].bar(x + offset, control[:, column], width=0.34, label=label, color=color)
        axes[2].bar_label(
            bars,
            labels=[f"{n}/{d}" for n, d in zip(control[:, column], control[:, 0], strict=True)],
            padding=3,
        )
    axes[2].set(title="Desktop stationary-tone controls", ylabel="Positive flags", ylim=(0, 6))
    axes[2].legend(loc="upper left", fontsize=8)
    for ax in axes:
        ax.set_xticks(x, ["2.5 MS/s", "5 MS/s"])
        ax.spines[["right", "top"]].set_visible(False)
    met = all(summary["rates"][str(r)]["warmed"]["total_cpu_ms"]["p99"] <= 100 for r in rates)
    fig.suptitle(
        "Differential timing + tone-conditioned fractional GLRT\n"
        f"Warmed CPU target {'met' if met else 'not met'}; "
        "streaming and specificity remain unqualified",
        fontsize=14,
    )
    fast = summary["rates"]["5000000"]
    fig.supxlabel(
        f"{summary['execution_count']} saved-IQ executions; {len(quality)} development RF probes; "
        f"{control[:, 0].sum()} generated tone controls.\n"
        f"5 MS/s CPU max: {fast['warmed']['total_cpu_ms']['max']:.1f} ms warm / "
        f"{fast['first_execution']['total_cpu_ms']['max']:.1f} ms first execution. "
        "Reference agreement is not verified Starlink truth.",
        fontsize=9,
    )
    fig.savefig(output, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    render(args.directory, args.output)


if __name__ == "__main__":
    main()
