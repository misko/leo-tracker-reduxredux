"""Show what the capture detector measured on probes admitted by the timing hint."""

import argparse
import csv
import io
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from ..__main__ import local_output, save_json, write
from . import differential_agreement as study
from .full_v5_check import _sha

LABELS = (
    "Matches the capture winner",
    "Matches another gated pilot",
    "Different timing or frequency",
    "Original detector was negative",
)


def render(out):
    lock = json.loads((out / "result-lock.json").read_bytes())
    if _sha(out / "summary.json") != lock["files"]["summary.json"]:
        raise ValueError("detector comparison changed")
    result = json.loads((out / "summary.json").read_bytes())
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5), gridspec_kw={"width_ratios": (1.4, 1)})
    fig.subplots_adjust(left=0.235, right=0.97, top=0.76, bottom=0.23, wspace=0.36)
    fig.suptitle(
        "What did the differential timing hint add?",
        x=0.035,
        ha="left",
        y=0.98,
        fontsize=17,
        fontweight="bold",
    )
    fig.text(
        0.035,
        0.86,
        "Two complete roof recordings, using the original detector as the pilot reference.",
        fontsize=10,
    )
    rows = []
    for i, (case, color) in enumerate(zip(study.CASES, ("#27365b", "#007c70"), strict=True)):
        item = result[case]
        counts = [item["gains_by_hint_label"].get(k, 0) for k in study.LABELS]
        bars = ax[0].barh(np.arange(4) + (i - 0.5) * 0.34, counts, 0.32, color=color, label=case)
        ax[0].bar_label(bars, labels=[str(v) for v in counts], padding=3, fontsize=8)
        den = item["capture_positive"]
        values = [item["winner_agreement"][role] / den * 100 for role in ("stock", "hinted")]
        ax[1].plot([0, 1], values, color=color, linewidth=2, marker="o", markersize=6)
        for j, role in enumerate(("stock", "hinted")):
            ax[1].annotate(
                f"{item['winner_agreement'][role]:,}/{den:,}",
                (j, values[j]),
                xytext=(0, 8 if i == 0 else -13),
                textcoords="offset points",
                ha="center",
                color=color,
                fontsize=9,
            )
        rows.append(
            dict(
                id=case,
                probes=item["probes"],
                gained=item["transitions"]["gained"],
                capture_positive=den,
                **dict(zip(study.LABELS, counts, strict=True)),
                **{f"{k}_matches": v for k, v in item["winner_agreement"].items()},
            )
        )
    ax[0].set(
        yticks=range(4), yticklabels=LABELS, xlim=(0, 300), xlabel="Newly positive receiver probes"
    )
    ax[0].invert_yaxis()
    ax[0].set_title("When stock was negative", loc="left", fontsize=11)
    ax[0].legend(
        frameon=False, ncols=2, loc="lower center", bbox_to_anchor=(0.5, -0.38), fontsize=9
    )
    ax[1].set(
        xlim=(-0.4, 1.42),
        ylim=(88.0, 96.2),
        xticks=(0, 1),
        xticklabels=("Stock wide", "With timing hint"),
        ylabel="Capture winners matched (%)",
    )
    ax[1].set_title("Across all positive capture probes", loc="left", fontsize=11)
    for axis in ax:
        axis.spines[["top", "right"]].set_visible(False)
        axis.set_axisbelow(True)
    ax[0].grid(axis="x", color="#e1e7eb")
    ax[1].grid(axis="y", color="#e1e7eb")
    fig.savefig(out / "agreement.png", dpi=165)
    fig.savefig(out / "agreement.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    buffer = io.StringIO(newline="")
    table = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    table.writeheader()
    table.writerows(rows)
    write(out / "stage.csv", buffer.getvalue().encode())
    files = ("agreement.png", "agreement.pdf", "stage.csv", "result-lock.json", "summary.json")
    save_json(
        out / "stage-lock.json",
        dict(files={n: _sha(out / n) for n in files}, plotter_sha256=_sha(Path(__file__))),
    )
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="differential-capture-agreement",
            title="Do new wide pilots agree with the original detector?",
            sample="27,060 valid receiver probes in two complete roof recordings",
            boundary="Stock wide, differential wide and capture-era native detector packets",
            note="A match requires timing and carrier agreement with an original gated pilot.",
            seal="stage-lock.json",
            image="agreement.png",
            pdf="agreement.pdf",
            csv="stage.csv",
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=study.REPORT)
    render(parser.parse_args().out)
