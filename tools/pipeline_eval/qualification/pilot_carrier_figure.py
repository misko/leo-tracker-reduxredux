"""Plot folded and absolute CFO errors from the sealed single-epoch measurements."""

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from ..__main__ import local_output, save_json
from .full_v5_check import _sha
from .pilot_carrier_trial import REPORT

GROUPS = (("primary", "miss"), ("primary", "matched"), ("confirmation", "miss"))
LABELS = ("Original misses", "Retained controls", "Later misses")


def summarize(rows):
    matched = [
        r
        for r in rows
        if r.get("epoch_error_samples") and abs(float(r["epoch_error_samples"])) <= 2
    ]
    summaries = {}
    for col in ("folded_error_hz", "absolute_error_hz"):
        values = [abs(float(r[col])) for r in matched if r.get(col)]
        summaries[col] = dict(
            n=len(values),
            median_hz=float(np.median(values)) if values else None,
            within={str(hz): sum(x <= hz for x in values) for hz in (1000, 10000, 40000)},
        )
    return dict(
        n=len(rows),
        timing_within_2=len(matched),
        **summaries,
        nearest_bin=sum(float(r["bin_steps"]) == 0 for r in matched if r.get("bin_steps")),
        nearest_or_neighbor=sum(float(r["bin_steps"]) <= 1 for r in matched if r.get("bin_steps")),
    )


def generate(out):
    with (out / "carrier.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    primary = [r for r in rows if r["mode"] == "rank1"]
    groups = [[r for r in primary if (r["cohort"], r["kind"]) == g] for g in GROUPS]
    result = {name: summarize(g) for name, g in zip(LABELS, groups, strict=True)}
    all_measured = summarize(primary)
    save_json(
        out / "summary.json",
        dict(
            groups=result,
            all_rank1=all_measured,
            half_frame=summarize([r for r in rows if r["mode"] == "sham"]),
        ),
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": (1, 1.25)})
    fig.subplots_adjust(left=0.07, right=0.98, top=0.72, bottom=0.22, wspace=0.31)
    fig.suptitle(
        "How much carrier frequency does the pilot timing reveal?",
        x=0.045,
        ha="left",
        y=0.98,
        fontsize=17,
        fontweight="bold",
    )
    x = np.arange(len(groups))
    for off, color, label, counts in (
        (
            -0.2,
            "#293653",
            "Pilot time within 2 samples",
            [b["timing_within_2"] for b in result.values()],
        ),
        (
            0,
            "#007f73",
            "Folded CFO within 40 kHz",
            [b["folded_error_hz"]["within"]["40000"] for b in result.values()],
        ),
        (
            0.2,
            "#b35914",
            "Absolute CFO within 40 kHz",
            [b["absolute_error_hz"]["within"]["40000"] for b in result.values()],
        ),
    ):
        bars = axes[0].bar(x + off, counts, 0.19, color=color, label=label)
        axes[0].bar_label(bars, fontsize=8)
    axes[0].set(
        xticks=x,
        xticklabels=[f"{name}\n(n = {len(g)})" for name, g in zip(LABELS, groups, strict=True)],
        ylabel="Receiver visits",
        ylim=(0, max(8, max(b["timing_within_2"] for b in result.values()) + 1)),
    )
    axes[0].set_title("Blind first timing proposal", loc="left", fontsize=11)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        frameon=False,
        ncols=3,
        fontsize=9,
        loc="upper left",
        bbox_to_anchor=(0.04, 0.91),
    )
    selected = [
        r
        for r in primary
        if r.get("epoch_error_samples") and abs(float(r["epoch_error_samples"])) <= 2
    ]
    for col, label, color in (
        ("folded_error_hz", "Modulo 227.27 kHz", "#007f73"),
        ("absolute_error_hz", "Absolute frequency", "#b35914"),
    ):
        k = np.sort([abs(float(r[col])) / 1000 for r in selected if r.get(col)])
        if len(k):
            y = np.arange(1, len(k) + 1)
            axes[1].step(
                np.r_[0.2, k, 1000],
                np.r_[0, y, len(k)],
                where="post",
                color=color,
                linewidth=2,
                label=label,
            )
            axes[1].scatter(k, y, c=color, s=15)
    axes[1].axvline(40, color="#687784", linestyle=":", linewidth=1)
    axes[1].set(
        xscale="log",
        xlim=(0.2, 1000),
        ylim=(0, len(selected) + 1),
        xlabel="Absolute error (kHz)",
        ylabel="Cumulative visits",
    )
    axes[1].set_title(
        f"When the first timing proposal matched ({len(selected)} visits)", loc="left", fontsize=11
    )
    axes[1].legend(loc="upper left", frameon=False, fontsize=9)
    for ax in axes:
        ax.spines[["right", "top"]].set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(axis="y", color="#e3e9ec")
    fig.text(
        0.045,
        0.04,
        "The absolute estimate uses the 4-sample phase to choose an alias. "
        "The existing coarse frequency grid has 80 kHz spacing.",
        fontsize=9,
        color="#354753",
    )
    fig.savefig(out / "carrier.png", dpi=165)
    fig.savefig(out / "carrier.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    names = (
        "prediction-lock.json",
        "carrier.csv",
        "controls.csv",
        "summary.json",
        "carrier.png",
        "carrier.pdf",
    )
    save_json(
        out / "stage-lock.json",
        dict(files={n: _sha(out / n) for n in names}, plotter_sha256=_sha(Path(__file__))),
    )
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="pilot-carrier",
            title="Carrier frequency at the detected pilot time",
            sample="32 previously indexed receiver visits on four roof recordings",
            boundary="Saved raw IQ at blind pilot starts to carrier-frequency estimate",
            note="Frequency errors use the capture-era carrier. Position was unmeasured.",
            image="carrier.png",
            pdf="carrier.pdf",
            csv="carrier.csv",
            seal="stage-lock.json",
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--out", type=local_output, default=REPORT)
    generate(cli.parse_args().out)
