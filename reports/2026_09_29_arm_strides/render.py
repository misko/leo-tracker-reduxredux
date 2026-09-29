"""Render measured ARM stride comparisons; never infer ARM time from host time."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from experiment import HERE, save, sha


def main():
    data = json.loads((HERE / "comparison.json").read_text())
    rows = data["aggregates"]
    rates = (2500000, 5000000, 7500000, 10000000)
    strides = (10, 20, 120)
    colors = ("#355c9a", "#159580", "#df7130")
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.hashsalt": "arm-strides-v1"})

    def group(stride):
        return [
            next(r for r in rows if r["rate_hz"] == rate and r["stride_ms"] == stride)
            for rate in rates
        ]

    def finish(fig, name):
        fig.tight_layout()
        for suffix in ("png", "svg"):
            destination = HERE / f"{name}.{suffix}"
            options = {"metadata": {"Date": None}} if suffix == "svg" else {}
            fig.savefig(destination, dpi=150, bbox_inches="tight", **options)
            if suffix == "svg":
                destination.write_text(
                    "\n".join(line.rstrip() for line in destination.read_text().splitlines()) + "\n"
                )
        plt.close(fig)

    x = np.arange(4)
    width = 0.25
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), gridspec_kw={"width_ratios": [1, 2]})
    axes[0].bar([str(s) for s in strides], [22, 12, 2], color=colors)
    for i, count in enumerate((22, 12, 2)):
        axes[0].text(i, count + 0.4, str(count), ha="center")
    axes[0].set(xlabel="Probe stride (ms)", ylabel="Search windows per dual-RX dwell", ylim=(0, 25))
    for i, stride in enumerate(strides):
        values = [r["mean_detector_cpu_ms"] for r in group(stride)]
        bars = axes[1].bar(
            x + (i - 1) * width, values, width, color=colors[i], label=f"{stride} ms stride"
        )
        axes[1].bar_label(bars, labels=[f"{v:.1f}" for v in values], fontsize=8, padding=2)
    axes[1].axhline(120, color="#b33", linestyle="--", label="120 ms dwell budget")
    axes[1].set(
        xticks=x,
        xticklabels=["2.5", "5", "7.5", "10"],
        xlabel="Sample rate (MS/s)",
        ylabel="Mean detector CPU time (ms/dwell)",
    )
    axes[1].legend(fontsize=8)
    fig.suptitle(
        "Measured PLUTO+ CPU0 — saved 120 ms dual-RX dwells\n"
        "Preparation + proposals + search; setup, I/O, serialization and capture excluded"
    )
    finish(fig, "arm-runtime")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    for i, stride in enumerate(strides):
        selected = group(stride)
        for ax, denominator in zip(
            axes,
            ("original_scheduled_positive_hits", "original_dense_positive_hits"),
            strict=True,
        ):
            values = [
                100 * r["original_hits_recovered"] / r[denominator] if r[denominator] else 0
                for r in selected
            ]
            ax.bar(x + (i - 1) * width, values, width, color=colors[i], label=f"{stride} ms stride")
            ax.set(
                xticks=x,
                xticklabels=["2.5", "5", "7.5", "10"],
                xlabel="Sample rate (MS/s)",
                ylim=(0, 105),
            )
    axes[0].set(
        title="Recovery within scheduled windows",
        ylabel="Frozen original positive hits recovered (%)",
    )
    axes[1].set(title="Recovery across full dense inventory\nOmitted windows remain in denominator")
    axes[0].legend(fontsize=8)
    fig.suptitle(
        "Hit recovery and coverage are different measurements\n"
        "Frozen eight-candidate reference; not the deployed fractional detector"
    )
    finish(fig, "hit-recovery")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for i, stride in enumerate(strides):
        selected = group(stride)
        for ax, key in zip(
            axes,
            ("native_positive_hits", "projected_candidate_entries"),
            strict=True,
        ):
            ax.bar(
                x + (i - 1) * width,
                [r[key] for r in selected],
                width,
                color=colors[i],
                label=f"{stride} ms stride",
            )
            ax.set(xticks=x, xticklabels=["2.5", "5", "7.5", "10"], xlabel="Sample rate (MS/s)")
    axes[0].set(title="Raw native positive candidate entries", ylabel="Count over tested dwells")
    axes[1].set(
        title="After unchanged tracker overlap policy", ylabel="Projected candidate entries"
    )
    axes[0].legend(fontsize=8)
    fig.suptitle(
        "Do not equate raw detections with downstream observations\n"
        "Tracking-policy diagnostic uses zero fractional offsets and synthetic UTC, "
        "not production publication"
    )
    finish(fig, "tracking-observations")

    names = [
        f"{stem}.{suffix}"
        for stem in ("arm-runtime", "hit-recovery", "tracking-observations")
        for suffix in ("png", "svg")
    ]
    save(
        HERE / "figure-manifest.json",
        {
            "comparison_sha256": sha(HERE / "comparison.json"),
            "files": {name: sha(HERE / name) for name in names},
        },
    )
    body = "".join(
        f'<img alt="{stem}" src="{stem}.png" style="max-width:100%">'
        for stem in ("arm-runtime", "hit-recovery", "tracking-observations")
    )
    (HERE / "comparison.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>ARM GLRT stride comparison</title>'
        '<main style="max-width:1400px;margin:2em auto;font:16px system-ui">'
        "<h1>ARM GLRT stride comparison</h1><p>Opt-in native runtime, not the deployed "
        "fractional detector or live capture worker. Identical saved dwells on PLUTO+ CPU0; "
        "no RF collection. See README.md for provenance, exact hit counts, and limitations.</p>"
        + body
        + "</main>"
    )


if __name__ == "__main__":
    main()
