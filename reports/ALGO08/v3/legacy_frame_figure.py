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
FIX_WRITER = "c684ca974a93252c720e189fbe29247ecd67a138413bb4bafe67238b1ccf10bb"
SHORT_WRITER = "64fa809fcff4f146244db5e2a5bcc354fbaca14d5da558d52e76df8096a74cd8"
SHORT_ORIGINAL = "c86a21b1555be7d4cc6ef61e2f416dc9b89c40ab647e35eaaa55ea4c40289122"


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


def writer_pair(fix, short, original):
    """Return installed, original indexed, and revised indexed process clocks."""
    if not (fix["qualified"] and all(fix["checks"].values()) and short["qualified"]
            and short["same_encoder_bytes"] and short["same_audit_fields_except_live_measurements"]
            and original["qualified"] and fix["dedicated_audit"]["same_fields_and_non_timing_values"]):
        raise ValueError("Expected two complete, scientifically verified replay receipts")
    # The historic tiny receipt stores the baseline and per-case ratios, not both baseline clocks.
    study = original["cohort"]["elapsed_s"]
    gate = study["historical_child_gate"]
    rows = []
    for case, old, new in (
        ("DS30-0016", fix["dedicated_audit"]["prior_process"], fix["products"]["indexed"]["process"]),
        ("DS30-0107", short["prior_all_member"], short["fresh_process"]),
    ):
        before = old["elapsed_s"]
        if before != study["child"][case]:
            raise ValueError("The previous writer and the matched cohort differ")
        rows.append((before / gate["ratios"][case], before, new["elapsed_s"]))
    return rows


def render_writer_pair(rows, path):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.7), sharey=True)
    fig.subplots_adjust(left=.22, right=.97, top=.70, bottom=.22, wspace=.23)
    fig.suptitle(f"A lighter audit writer cut the withholding run to {rows[1][2]:.3f} s", x=.035, ha="left",
                 weight="bold", fontsize=16)
    fig.text(.036, .85, "Original DS30 waveforms   ·   one low-priority Gauss core   ·   elapsed seconds",
             color="#465767")
    for ax, times, title in zip(axes, rows, ("DS30-0016  ·  fix", "DS30-0107  ·  withheld")):
        ax.set_title(title, loc="left", fontsize=11)
        ax.barh(range(3), times, height=.55, color=["#344d68", "#75a89c", "#147768"])
        for i, val in enumerate(times):
            ax.text(val + .025 * max(times), i, f"{val:.3f}", va="center", fontsize=10,
                    bbox=dict(facecolor="white", edgecolor="none", pad=.3))
        ax.axvline(times[0]/2, ls="--", color="#aa5b29", lw=1.3)
        ax.set_xlim(0, max(times)*1.28)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    axes[0].invert_yaxis()
    axes[0].set_yticks(range(3), ["Installed ALGO08v3", "Indexed · previous writer", "Indexed · lighter writer"])
    fig.text(.036, .07, "Dashed lines mark half of installed runtime. Each bar times one process through exit with indexes ready.",
             fontsize=9)
    fig.savefig(path, dpi=155, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    base = HERE / "measurements"
    render(timings(load_seal(base / "legacy-block-raw-0016.json.gz", FIVE),
                   load_seal(base / "legacy-block-all-0016.json.gz", ALL)),
           HERE / "development/legacy-original-0016.png")
    render_writer_pair(writer_pair(load_seal(base / "legacy-map-writer-0016.json.gz", FIX_WRITER),
                                   load_seal(base / "lightweight-audit-0107.json.gz", SHORT_WRITER),
                                   load_seal(base / "legacy-block-all-0107.json.gz", SHORT_ORIGINAL)),
                       HERE / "development/legacy-writer-pair.png")
