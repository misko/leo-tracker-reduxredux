"""Render complete held-lane fractional outcomes from sealed native traces."""

import argparse
import csv
import gzip
import json
from pathlib import Path

import matplotlib

from ..__main__ import save_json
from .full_v5_check import MARGIN_GATE, _sha

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

MODES = ("stock", "causal", "sham")


def figures(folder):
    worker = json.loads((folder / "worker-lock.json").read_bytes())
    if any(_sha(folder / name) != sha for name, sha in worker["files"].items()):
        raise ValueError("recorded native worker bytes changed")
    summary = json.loads((folder / "summary.json").read_bytes())
    data = []
    for ident, totals in summary.items():
        source = folder / f"{ident}.json.gz"
        if _sha(source) != totals["worker_trace_sha256"]:
            raise ValueError("scoring and detector traces differ")
        rows = json.loads(gzip.decompress(source.read_bytes()))
        scores = {(x["visit"], x["receiver"]): x for x in totals["lanes"]}
        for row in rows:
            if row["status"] != "processed":
                continue
            for index, receiver in enumerate(row["receiver_ids"]):
                lane = scores[(row["visit"], receiver)]
                for mode in MODES:
                    candidates = row["result"]["payloads"][mode]["rows"][index]["candidates"]
                    margins = [
                        c["fractional_epoch"]["margin"]
                        for c in candidates
                        if c["fractional_epoch"]["status"] == "complete"
                    ]
                    active = lane["traces"][mode] if mode != "stock" else lane["traces"]["off"]
                    score = lane["against_archive"][mode]
                    data.append(
                        dict(
                            recording=ident,
                            visit=row["visit"],
                            receiver=receiver,
                            method=mode,
                            has_causal_hint=lane["hint"] is not None,
                            fourth_replaced=active["ordinary"] != active["selected"],
                            ordinary_active_epochs=lane["traces"]["off"]["active_epochs"],
                            active_epochs=active["active_epochs"],
                            candidate_count=len(candidates),
                            fractional_complete=len(margins),
                            best_fractional_margin=max(margins, default=None),
                            emitted_positives=score["native_positive"],
                            archived_positives=score["production_positive"],
                            archived_matches=len(score["positive_matches"]),
                        )
                    )

    csv_path = folder / "hinted-glrt.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)

    style = {
        "stock": ("#163246", "o", "Stock wide"),
        "causal": ("#007973", "s", "Causal hint"),
        "sham": ("#a65327", "^", "Uniform sham"),
    }
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.3), sharey=True)
    for ax, (ident, totals) in zip(axes, summary.items(), strict=True):
        lanes = sum(row["hint"] is not None for row in totals["lanes"])
        used = sum(
            r["recording"] == ident and r["method"] == "causal" and r["fourth_replaced"]
            for r in data
        )
        edge = "lower" if ident.startswith("DS26") else "upper"
        ax.set_title(f"{ident} · {edge} edge", loc="left", fontsize=12, fontweight="semibold")
        for i, mode in enumerate(MODES):
            series = [
                r["best_fractional_margin"]
                for r in data
                if r["recording"] == ident and r["method"] == mode
            ]
            measured = [
                (k + 1 + (i - 1) * 0.19, value)
                for k, value in enumerate(series)
                if value is not None
            ]
            color, marker, label = style[mode]
            if measured:
                x, y = zip(*measured, strict=True)
                ax.scatter(x, y, s=21, color=color, marker=marker, alpha=0.87, label=label)
        ax.axhline(
            MARGIN_GATE,
            lw=1.15,
            color="#4d535a",
            alpha=0.72,
            linestyle=(0, (5, 3)),
            label="Positive gate",
        )
        ax.set_xlim(0.35, 16.6)
        ax.set_ylim(-0.001, 0.029)
        ax.set_xticks(range(2, 17, 2))
        ax.set_xlabel(
            f"Receiver lane in chronological order\n{used}/{lanes} causal hints replaced center 4"
        )
        ax.grid(axis="y", alpha=0.18)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Best complete fractional GLRT margin")
    fig.suptitle(
        "Causal timing hints on 16 saved-IQ visits",
        x=0.09,
        y=0.991,
        ha="left",
        fontsize=16,
        fontweight="semibold",
    )
    fig.text(
        0.09,
        0.89,
        "Four-center budget per lane. Zero archived or emitted positives in the sealed panel.",
        fontsize=10,
    )
    items, labels = axes[1].get_legend_handles_labels()
    fig.legend(
        items, labels, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.002)
    )
    fig.subplots_adjust(left=0.09, right=0.982, top=0.805, bottom=0.225, wspace=0.15)
    fig.savefig(folder / "hinted-glrt.png", dpi=175)
    fig.savefig(folder / "hinted-glrt.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)

    names = (
        *worker["files"],
        "worker-lock.json",
        "summary.json",
        "hinted-glrt.csv",
        "hinted-glrt.png",
        "hinted-glrt.pdf",
    )
    save_json(
        folder / "result-lock.json",
        {
            "files": {name: _sha(folder / name) for name in names},
            "source_sha256": _sha(Path(__file__)),
            "scope": "first eight admissible proposed saved-IQ visits per edge, full detector",
        },
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("report", type=Path)
    figures(cli.parse_args().report)
