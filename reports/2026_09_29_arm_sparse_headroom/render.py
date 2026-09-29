"""Standalone measured headroom, phase-cost and stability figures."""

import json

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from execute import HERE, digest, save

matplotlib.use("Agg")


def main():
    data = json.loads((HERE / "comparison.json").read_text())["variants"]
    names = list(data)
    if len(names) > 5:
        names = [names[0], "sparse-uncached", "sparse-cached", "sparse-cached-pgo", names[-1]]
    display = {
        "fullprep-uncached": "Full-prep\ncontrol",
        "sparse-uncached": "20 ms\npreparation",
        "sparse-cached": "Exact rotation\ncache",
        "sparse-cached-pgo": "32-context\nPGO",
        "sparse-reuse-plans-pgo33": "Final source\n33-context PGO",
    }
    labels = [display.get(n, n.replace("-", "\n", 1)) for n in names]
    primary = [next(r for r in data[n]["rates"] if r["rate_hz"] == 2500000) for n in names]
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.hashsalt": "sparse-headroom-v1",
        }
    )
    artifacts = []

    def finish(fig, name):
        fig.tight_layout()
        for suffix in ("png", "svg"):
            path = HERE / f"{name}.{suffix}"
            options = {"metadata": {"Date": None}} if suffix == "svg" else {}
            fig.savefig(path, dpi=150, bbox_inches="tight", **options)
            if suffix == "svg":
                path.write_text("\n".join(s.rstrip() for s in path.read_text().splitlines()) + "\n")
            artifacts.append(path)
        plt.close(fig)

    x = np.arange(len(names))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for ax, key, title in zip(
        axes, ("call_cpu_ms", "call_wall_ms"), ("Detector CPU", "Detector wall"), strict=True
    ):
        for i, (quantile, color) in enumerate(
            zip(("p50", "p95", "max"), ("#216c7a", "#c89c39", "#b54a41"), strict=True)
        ):
            values = [r[key][quantile] for r in primary]
            bars = ax.bar(x + (i - 1) * 0.24, values, 0.24, color=color, label=quantile)
            ax.bar_label(bars, fmt="%.1f", fontsize=8, padding=2)
        ax.axhline(100, color="#397541", linestyle="--", label="100 ms headroom gate")
        ax.axhline(120, color="#b33", linestyle=":", label="120 ms dwell deadline")
        ax.set(title=title, xticks=x, xticklabels=labels, ylabel="Milliseconds / dual-RX dwell")
    axes[0].legend(fontsize=8)
    fig.suptitle(
        "PLUTO+ CPU0 · 2.5 MS/s · first 20 ms per RX only\n"
        "Same 152 saved dwells × 10 repeats; persistent RAM API"
    )
    finish(fig, "latency")

    fig, ax = plt.subplots(figsize=(10, 5))
    bottom = np.zeros(len(names))
    for phase, color in zip(
        ("allocation", "preparation", "proposals", "search", "cleanup"),
        ("#888888", "#dc9d38", "#4286a8", "#39816e", "#b5b5b5"),
        strict=True,
    ):
        values = np.array([r["stages"][phase + "_cpu_ms"]["mean"] for r in primary])
        ax.bar(x, values, bottom=bottom, label=phase, color=color)
        bottom += values
    overhead = [
        max(0, r["call_cpu_ms"]["mean"] - base) for r, base in zip(primary, bottom, strict=True)
    ]
    ax.bar(x, overhead, bottom=bottom, color="#6d5b84", label="outer overhead")
    ax.set(
        xticks=x,
        xticklabels=labels,
        ylabel="Mean CPU milliseconds / dwell",
        title="Measured disjoint outer phases\n"
        "Preparation includes buffer allocations; nested FFT timings are separate",
    )
    ax.legend()
    finish(fig, "phases")

    fig, ax = plt.subplots(figsize=(10, 5))
    for label, r in zip(names, primary, strict=True):
        rounds = sorted(int(k) for k, v in r["by_repeat"].items() if v is not None)
        ax.plot(
            rounds,
            [r["by_repeat"][str(i)]["p95"] for i in rounds],
            marker="o",
            label=label + " p95",
        )
        ax.plot(
            rounds,
            [r["by_repeat"][str(i)]["max"] for i in rounds],
            linestyle=":",
            label=label + " max",
        )
    ax.axhline(100, color="#397541", linestyle="--")
    ax.axhline(120, color="#b33", linestyle="--")
    ax.set(
        xlabel="Repeat ordinal within bounded RAM batches",
        ylabel="Detector wall milliseconds",
        title="Repeated-run stability across all 152 dwells\n"
        "Rounds aggregate successive batches; this is not a continuous-time axis",
    )
    ax.legend(fontsize=8)
    finish(fig, "stability")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    values = [primary[0], primary[-1]]
    short = ["Native control", "Final measured variant"]
    for i, (field, label) in enumerate(
        (
            ("candidate_entries", "All candidate entries"),
            ("positive_candidates", "Positive native candidates"),
            ("original_hits_recovered", "Matched original scheduled hits"),
            ("projected_entries", "Diagnostic projected entries"),
        )
    ):
        bars = axes[0].bar(
            np.arange(2) + (i - 1.5) * 0.18, [v[field] for v in values], 0.18, label=label
        )
        axes[0].bar_label(bars, fontsize=8)
    axes[0].set(
        xticks=range(2),
        xticklabels=short,
        ylabel="Count across 152 unique dwells",
        title="Scientific output: same scheduled windows",
    )
    axes[0].legend(fontsize=8, loc="lower left")
    final = primary[-1]
    denominators = [final["original_scheduled_hits"], final["original_dense_hits"]]
    recovered = final["original_hits_recovered"]
    bars = axes[1].bar(range(2), [100 * recovered / n for n in denominators], color="#39816e")
    axes[1].bar_label(
        bars,
        labels=[f"{recovered}/{n}\n{100 * recovered / n:.1f}%" for n in denominators],
        padding=3,
    )
    axes[1].set(
        xticks=range(2),
        xticklabels=[
            "Original hits in scheduled\nfirst-20-ms windows",
            "All frozen dense\noriginal hits",
        ],
        ylim=(0, 110),
        ylabel="Original candidate hits recovered (%)",
        title="Denominator matters: sparse coverage remains sparse",
    )
    fig.suptitle("Counts are not interchangeable with positive-window counts or satellite tracks")
    finish(fig, "science")

    stress_path = HERE / "local/final-stress/stress.jsonl"
    if stress_path.exists():
        calls = [json.loads(line)["result"] for line in stress_path.read_text().splitlines()
                 if '"result"' in line]
        blocks = [calls[i:i + 16] for i in range(0, len(calls), 16)]
        fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
        rounds = np.arange(1, len(blocks) + 1)
        axes[0].plot(rounds, [max(c["call_wall_ms"] for c in b) for b in blocks],
                     color="#216c7a", label="Maximum detector wall time per 16-dwell round")
        axes[0].axhline(100, linestyle="--", color="#397541", label="100 ms gate")
        axes[0].axhline(120, linestyle=":", color="#b33", label="120 ms deadline")
        axes[0].set(ylabel="Milliseconds", ylim=(80, 123))
        axes[0].legend(fontsize=8)
        axes[1].plot(rounds, [max(c["thermal_millidegrees_after"] for c in b) / 1000
                              for b in blocks], color="#c89c39", label="Maximum XADC temperature")
        axes[1].set(ylabel="SoC temperature (°C)", xlabel="Successive shuffled repeat (16 dwells)")
        axes[1].legend(fontsize=8)
        fig.suptitle("Sustained candidate-heavy test: 1,600 calls in one persistent process\n"
                     "Final native source + tail-aware PGO; no capture")
        finish(fig, "stress-stability")
    save(
        HERE / "figure-manifest.json",
        {
            "comparison_sha256": digest(HERE / "comparison.json"),
            "stress_sha256": digest(stress_path) if stress_path.exists() else None,
            "files": {p.name: digest(p) for p in artifacts},
        },
    )


if __name__ == "__main__":
    main()
