"""Plot matched DS30-0402 saved processes and both surveyed position errors."""

import argparse
import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load(path):
    with gzip.open(path, "rt") as stream:
        return json.load(stream)


def render(fitted_file, transfer_file, output, wider_file=None):
    exact, transfer = load(fitted_file), load(transfer_file)
    if not exact["paired_science_equal"] or transfer["case"] != "DS30-0402":
        raise ValueError("Expected the verified named and cumulative 0402 comparisons")
    labels = [
        "Original ALGO08v3",
        "Prepared checks",
        "Fixed-zero arm first",
        "Fitted arm first",
        "Cumulative solver",
    ]
    clocks = [
        exact[key]
        for key in (
            "stock_exit",
            "gate_only_exit",
            "archived_c0_first_exit",
            "combined_exit",
        )
    ]
    clocks.append(transfer["runs"]["cumulative"]["process"])
    scores = [exact["scores"]] * 4 + [transfer["scores"]["cumulative"]]
    if (
        any(clock["exit_code"] for clock in clocks)
        or exact["scores"] != transfer["scores"]["stock"]
    ):
        raise ValueError("Nonmatching stock reference or incomplete recording")
    fig, (time, error) = plt.subplots(
        1, 2, figsize=(10.8, 4), sharey=True, gridspec_kw={"width_ratios": [1.55, 1]}
    )
    fig.subplots_adjust(left=0.205, right=0.965, bottom=0.23, top=0.72, wspace=0.22)
    colors = ["#475569", "#236778", "#236778", "#0a7466", "#ad6523"]
    owner_note = "The first four runs retained all 4,821 assigned observations per arm. "
    if wider_file is not None:
        wider = load(wider_file)["candidate"]
        if (wider["terminal"] != exact["terminal"] or wider["old_exit"] != exact["combined_exit"]
                or not wider["role_equality"] or not wider["sidecars_equal"] or wider["new_exit"]["exit_code"]
                or not all(all(fields.values()) for fields in wider["figures"].values())):
            raise ValueError("The wider run must reproduce the same named scientific and visual output")
        labels.insert(-1, "Fitted first + wider fit")
        clocks.insert(-1, wider["new_exit"])
        scores.insert(-1, exact["scores"])
        colors.insert(-1, "#0a7466")
        owner_note = "The first five runs retained all 4,821 assigned observations per arm. "
    for i, (clock, score, color) in enumerate(zip(clocks, scores, colors, strict=True)):
        wall = clock["elapsed_s"]
        time.barh(i, wall, height=0.48, color=color)
        time.text(wall + 1, i, f"{wall:.2f}", va="center", fontsize=10)
        for arm, offset, marker, ink in (
            ("c0", -0.09, "o", "#203e64"),
            ("fitted_c", 0.09, "D", "#bf7132"),
        ):
            error.scatter(
                score[arm]["horizontal_error_km"],
                i + offset,
                marker=marker,
                s=37,
                color=ink,
                label=("Fixed zero" if arm == "c0" else "Fitted") if i == 0 else None,
            )
    time.set(yticks=range(len(labels)), yticklabels=labels, xlabel="Seconds", xlim=(0, 84))
    error.set(xlabel="Kilometers", xlim=(0.83, 0.982), xticks=[0.84, 0.88, 0.92, 0.96])
    error.legend(
        loc="upper left", bbox_to_anchor=(0, 1.22), ncol=2, frameon=False, fontsize=9
    )
    time.invert_yaxis()
    for ax, title in (
        (time, "Elapsed through publication and exit"),
        (error, "Horizontal position error"),
    ):
        ax.set_title(title, loc="left", fontsize=11, weight="bold", pad=3)
        ax.grid(axis="x", alpha=0.17)
        ax.set_axisbelow(True)
        ax.spines[["top", "left", "right"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    fig.text(
        0.04, 0.93, "DS30-0402 from identical saved detections", size=18, weight="bold"
    )
    fig.text(
        0.04,
        0.055,
        owner_note + "The cumulative solver retained 4,680.",
        size=10,
        color="#334155",
    )
    fig.savefig(output, dpi=155, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("fitted_receipt", "transfer_receipt", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--wider-receipt", type=Path)
    args = parser.parse_args()
    render(args.fitted_receipt, args.transfer_receipt, args.output, args.wider_receipt)
