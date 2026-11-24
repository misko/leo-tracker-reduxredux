"""Plot verified original-file process clocks and separately measured map creation."""

import gzip
import json
from hashlib import sha256
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
FIVE = "7e5f44b388a0674ab276282478122d218ef39adf9985acb31ef3e5a4d3b6afa0"
ALL = "9a13cc45e8933106a6be91c5ddfd575c87c311773499420131a094b44113b557"


def load_seal(path, digest):
    raw = gzip.decompress(path.read_bytes())
    if sha256(raw).hexdigest() != digest:
        raise ValueError(f"Unexpected result digest for {path.name}")
    return json.loads(raw)


def timings(five, complete):
    if (not five["qualified"] or not complete["qualified"] or not all(complete["checks"].values())
            or complete["ordinary_control_sha256"] != FIVE or five["case"] != complete["case"]
            or complete["input"]["totals"]["authenticated_encoded_bytes"] != 991734597):
        raise ValueError("Expected the fully scored DS30-0016 original-file comparisons")
    part = five["prices"]["elapsed_s"]
    full = complete["prices"]["elapsed_s"]
    if part["ordinary"] != full["ordinary"] or part["prepared"] != full["five_maps"]:
        raise ValueError("The original reader and five-map comparisons must be shared")
    return [
        ("Installed ALGO08v3", part["installed_prior"], 0),
        ("Candidate · ordinary reader", part["ordinary"], 0),
        ("Candidate · 5 files indexed", part["prepared"], part["measured_full_preparation"]),
        ("Candidate · 13 files indexed", full["all_members"],
         full["prior_complete_five_map_validation"] + full["measured_incremental_preparation"]),
    ]


def render(rows, path):
    fig, ax = plt.subplots(figsize=(9, 4.3))
    fig.subplots_adjust(left=.29, right=.94, top=.78, bottom=.26)
    fig.suptitle("Time to publish a position from the original recording", x=.035, ha="left",
                 weight="bold", fontsize=17)
    fig.text(.037, .84, "DS30-0016   ·   808 visits   ·   one low-priority core", color="#465767")
    for i, (_, ready, setup) in enumerate(rows):
        color = "#344d68" if i == 0 else "#16776b"
        ax.barh(i, ready, color=color, height=.57)
        ax.text(ready-.09, i, f"{ready:.2f} s", va="center", ha="right", color="white", weight="bold")
        if setup:
            ax.barh(i, setup, left=ready, height=.57, color="#dfebe7", edgecolor="#63837b", hatch="//")
            ax.text(ready+setup+.08, i, f"{ready+setup:.2f} s", va="center", color="#294b44")
    ax.set_yticks(range(len(rows)), [row[0] for row in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 13.5)
    ax.set_xlabel("Elapsed seconds")
    ax.axvline(rows[0][1]/2, ls="--", lw=1.3, color="#aa5b29", zorder=3)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#e4e9ec")
    fig.text(.036, .12, "Solid bars show analysis through process exit. Hatching adds measured map preparation.", fontsize=9)
    fig.text(.036, .066, "Dashed line marks half the installed time. Candidate runs used an existing orbit index.", fontsize=9)
    fig.savefig(path, dpi=155, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    base = HERE / "measurements"
    render(timings(load_seal(base / "legacy-block-raw-0016.json.gz", FIVE),
                   load_seal(base / "legacy-block-all-0016.json.gz", ALL)),
           HERE / "development/legacy-original-0016.png")
