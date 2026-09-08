"""Render saved screen experiments without treating unresolved RF as negatives."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from tools.qualify_native_presence import write_json


def historic_summary(rows):
    selected = [
        r
        for r in rows
        if r["mode"] == "blind"
        and r["bins"] == 512
        and r["timing_bins"] == (2048 if r["rate_hz"] == 2500000 else 4096)
    ]
    identities = [(r["session"], r["visit"]) for r in selected]
    if not selected or len(set(identities)) != len(identities):
        raise ValueError("nonempty unique historical dwell inventory required")
    positive = [r for r in selected if any(r["reference_positive"])]
    unresolved = [r for r in selected if not any(r["reference_positive"])]
    return {
        "dwells": len(selected),
        "reference_positive": len(positive),
        "reference_positive_flagged": sum(r["observations"][0]["detected"] for r in positive),
        "reference_associated": sum(r["observations"][0]["associated"] for r in positive),
        "unresolved": len(unresolved),
        "unresolved_flagged": sum(r["observations"][0]["detected"] for r in unresolved),
    }


def control_summary(rows):
    identities = [
        tuple(r["truth"][k] for k in ("rate_hz", "edge", "seed", "kind", "window")) for r in rows
    ]
    if not rows or len(set(identities)) != len(identities):
        raise ValueError("nonempty unique control inventory required")
    positive = [r for r in rows if r["truth"]["starlink_model_present"]]
    negative = [r for r in rows if not r["truth"]["starlink_model_present"]]
    return {
        "positive": len(positive),
        "positive_flagged": sum(r["flags"][0] for r in positive),
        "negative": len(negative),
        "negative_flagged": sum(r["flags"][0] for r in negative),
    }


def render(evidence: Path, output: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    output = output.resolve()
    if any(output.is_relative_to(Path(p)) for p in ("/mnt/qnap01", "/srv/bulk/leo")):
        raise ValueError("report output cannot be beneath archive storage")
    output.mkdir(parents=True, exist_ok=False)
    quality = {}
    for name in ("point", "area", "hybrid"):
        rows = {}
        for kind in ("historic", "controls"):
            with gzip.open(evidence / f"{kind}-{name}/results.jsonl.gz", "rt") as stream:
                rows[kind] = [json.loads(line) for line in stream]
        quality[name] = {
            "historic": historic_summary(rows["historic"]),
            "controls": control_summary(rows["controls"]),
        }
    write_json(output / "quality-summary.json", quality)
    colors = ("#3676a5", "#bc7340", "#27816d")
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.3), layout="constrained")
    metrics = (
        ("controls", "positive_flagged", "positive", "Injected pilots"),
        (
            "historic",
            "reference_positive_flagged",
            "reference_positive",
            "Flag in reference-positive dwell",
        ),
        ("historic", "reference_associated", "reference_positive", "Timing/CFO association"),
    )
    for ax, (group, key, denominator, title) in zip(axes, metrics, strict=True):
        values = [quality[name][group] for name in quality]
        heights = [100 * r[key] / r[denominator] for r in values]
        bars = ax.bar(list(quality), heights, color=colors)
        ax.bar_label(bars, labels=[f"{r[key]}/{r[denominator]}" for r in values], padding=4)
        ax.set(title=title, ylim=(0, 115), ylabel="Observed fraction (%)")
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(
        "One confirmation after a complete 120 ms RX1 screen\n"
        "Development data, not held-out sensitivity or satellite identity",
        fontsize=13,
    )
    control_counts = "; ".join(
        f"{name}: {r['controls']['negative_flagged']}/{r['controls']['negative']}"
        for name, r in quality.items()
    )
    fig.supxlabel(
        f"Negative-control flags — {control_counts}. Unreferenced RF remains unresolved.",
        fontsize=10,
    )
    fig.savefig(output / "screen-quality.png", dpi=170)
    plt.close(fig)
    variants = ("fftw", "hybrid", "hybrid-v2", "hybrid-v3")
    labels = ("Point + FFTW", "Hybrid", "Cached geometry", "Contiguous fold")
    summaries = [
        json.loads((evidence / "arm" / f"verified-{v}.json").read_text()) for v in variants
    ]
    fig, ax = plt.subplots(figsize=(10, 4.5), layout="constrained")
    x = np.arange(len(variants))
    for i, rate in enumerate((2500000, 5000000)):
        values = [
            r["statistics"][f"{rate}:blind"]["prefixes"]["1"]["prefix_cpu_ms"]["p99"]
            for r in summaries
        ]
        bars = ax.bar(
            x + (i - 0.5) * 0.36, values, 0.36, label=f"{rate / 1e6:g} MS/s", color=colors[i]
        )
        ax.bar_label(bars, fmt="%.1f", padding=3)
    ax.axhline(100, color="#b33c42", linestyle="--", label="100 ms target")
    ax.set(
        xticks=x,
        xticklabels=labels,
        ylabel="Complete screen + one blind confirmation CPU p99 (ms)",
        ylim=(0, 140),
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower right")
    ax.set_title(
        "Actual ARM saved-IQ replay: 12 observations per rate/policy\n"
        "Small-sample p99; not a worst-case or live-duty guarantee"
    )
    fig.savefig(output / "arm-screen-runtime.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    render(args.evidence, args.output)
