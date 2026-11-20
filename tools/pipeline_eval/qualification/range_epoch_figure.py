"""Render the sealed held-epoch evidence without rerunning the paired measurements."""

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from ..__main__ import ROOT, save_json
from .input_factor_bridge import _sha, check, read

OUT = ROOT / "reports/2026_11_19_receiver_screening/receiver-core/range-epoch"
SEALS = ("measurement-lock.json", "native-origin-lock.json", "reflected-spatial-lock.json")
CONTROLS = (
    ("clock_only", "Clock only", "#5C6579"),
    ("propagation", "+Range / c", "#BD5627"),
    ("reflected", "−Range / c", "#007F71"),
    ("delay_15s", "+15 s timestamp", "#C4AB70"),
    ("shuffled_epochs", "Shuffled epochs", "#B3B7C2"),
)


def generate(out=OUT):
    for name in SEALS:
        for file, digest in read(out / name)["files"].items():
            check(out / file, digest)
    measured = read(out / "scores.json")
    signs = read(out / "native-origin-results.json")["rows"]
    reflected = {r["id"]: r for r in read(out / "reflected-spatial.json")}
    rows = []

    def add(case, metric, model, point, value):
        rows.append(dict(case=case, metric=metric, model=model, point=point, value=value))

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.titleweight": "bold"})
    fig, axes = plt.subplots(2, 2, figsize=(14, 8.5), layout="constrained")
    fig.suptitle(
        "Held GLRT frame timing and surveyed-location discrimination\n"
        "Privileged original v5 identities · two development and two held · one measured roof",
        fontsize=18,
        fontweight="bold",
        color="#172b36",
    )
    ax = axes[0, 0]
    xs = np.arange(len(measured))
    for i, (key, label, color) in enumerate(CONTROLS):
        values = [r["controls"][key]["shared_clock"]["arc_median_mae"] for r in measured]
        ax.bar(xs + 0.15 * (i - 2), values, 0.14, label=label, color=color, zorder=3)
        for record, value in zip(measured, values, strict=True):
            add(record["id"], "held arc epoch MAE (samples)", key, "reference", value)
    ax.set_xticks(xs, [f"{r['id']}\n{r['cohort']}" for r in measured])
    ax.set_ylabel("Mean held-arc median error (samples)")
    ax.set_title("Chronological timing prediction at the surveyed site", loc="left")
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.0))
    ax.set_ylim(0, 2600)

    ax = axes[0, 1]
    for source, name, style in (
        ("injected actual pilot template", "Planted template, both sidebands", "o"),
        ("first archived DS26-0036 window", "Measured CI16 window", "x"),
    ):
        subset = [r for r in signs if r["source"] == source and r["available"]]
        ax.scatter(
            [r["circular_delay_samples"] for r in subset],
            [r["reported_epoch_delta_samples"] for r in subset],
            label=name,
            marker=style,
            s=45,
            alpha=0.65,
            zorder=3,
        )
        for row in subset:
            add(
                source,
                "reported native shift (samples)",
                row["edge"],
                row["circular_delay_samples"],
                row["reported_epoch_delta_samples"],
            )
    ax.plot([-10, 10], [-10, 10], ":", color="#7D8C91", lw=1)
    ax.set(
        xlabel="Imposed circular delay (samples)",
        ylabel="Reported epoch change (samples)",
        xticks=(-9, -4, 0, 4, 9),
        yticks=(-9, -4, 0, 4, 9),
    )
    ax.set_title("Compiled detector reports arrival-time sign", loc="left")
    ax.legend(frameon=False, loc="upper left", fontsize=8)

    ax = axes[1, 0]
    rankings = []
    for row in measured:
        a = row["rankings"]
        b = reflected[row["id"]]["rankings"]
        rankings.append(
            [x.index("reference") + 1 for x in (a["cfo"], a["frame"], a["joint"], b["joint"])]
        )
    ax.imshow(rankings, cmap="YlGnBu_r", vmin=1, vmax=9, aspect="auto")
    labels = ["CFO", "+Range epoch", "CFO + epoch", "CFO + reflected epoch"]
    for i, rank in enumerate(rankings):
        for j, value in enumerate(rank):
            ax.text(
                j,
                i,
                f"{value}/9",
                ha="center",
                va="center",
                color="white" if value < 4 else "#172b36",
                fontweight="bold",
            )
            add(measured[i]["id"], "reference rank of nine", labels[j], "reference", value)
    ax.set_xticks(range(len(labels)), labels, fontsize=8)
    ax.set_yticks(xs, [r["id"] for r in measured])
    ax.set_title("Surveyed-location rank among fixed alternatives", loc="left")

    ax = axes[1, 1]
    ax.axhline(0, lw=1, color="#7D8C91", linestyle=":")
    for i, row in enumerate(r for r in measured if r["cohort"] == "held"):
        values = reflected[row["id"]]["geometry"]
        baseline = values[0]["timing_shared"]["arc_median_mae"]
        shift = (i - 0.5) * 0.26
        dots = [v["timing_shared"]["arc_median_mae"] - baseline for v in values[1:]]
        ax.scatter([j + shift for j in range(8)], dots, label=row["id"], zorder=3)
        for v, d in zip(values[1:], dots, strict=True):
            add(row["id"], "relative timing loss (samples)", "reflected", v["location"], d)
    ax.set_xticks(
        range(8), [v["location"].replace(" km ", " km\n") for v in values[1:]], fontsize=8
    )
    ax.set_ylabel("Held timing loss − surveyed-site loss (samples)")
    ax.set_title("Exploratory reflected-sign sensitivity on the same rows", loc="left")
    ax.legend(frameon=False, fontsize=8)
    for target in (axes[0, 0], axes[0, 1], axes[1, 1]):
        target.grid(axis="y", color="#e2e6e7", linewidth=0.7, zorder=0)
        target.spines[["top", "right"]].set_visible(False)
    basename = out / "range-epoch"
    fig.savefig(basename.with_suffix(".png"), dpi=160)
    fig.savefig(basename.with_suffix(".pdf"), metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    with basename.with_suffix(".csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    names = (*SEALS, "range-epoch.png", "range-epoch.pdf", "range-epoch.csv")
    save_json(
        out / "chart-lock.json",
        dict(
            cases=[r["id"] for r in measured],
            files={name: _sha(out / name) for name in names},
            renderer_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    generate()
