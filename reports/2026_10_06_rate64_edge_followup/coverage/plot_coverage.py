"""Regenerate publication figures and frozen aggregate statistics."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
plt.rcParams.update(
    {
        "font.size": 11,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "#fafbfc",
        "savefig.dpi": 180,
    }
)


def main():
    data = json.loads((ROOT / "bandwidth-results.json").read_text())
    high = [r for r in data["rows"] if r["rate"] == 10000000]
    strong = [r for r in high if r["lane"].endswith("strong")]
    fig, axs = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={"width_ratios": [1, 1.15]})
    for split, color, marker in [("development", "#197e9c", "o"), ("evaluation", "#b0581b", "s")]:
        rows = [r for r in high if r["split"] == split]
        x = [r["baseline"]["margin"] for r in rows]
        y = [r["digitally_narrowed"]["margin"] for r in rows]
        axs[0].scatter(x, y, c=color, marker=marker, s=50, label=split.capitalize(), alpha=0.85)
        for r in rows:
            if not r["search_support_only_eligible"]:
                axs[0].scatter(
                    r["baseline"]["margin"],
                    r["digitally_narrowed"]["margin"],
                    s=125,
                    facecolor="none",
                    edgecolor="#c02640",
                    linewidth=1.3,
                )
    axs[0].plot([0, 0.86], [0, 0.86], color="#777", ls="--", lw=1)
    axs[0].axhline(0.025, color="#999", lw=0.8)
    axs[0].axvline(0.025, color="#999", lw=0.8)
    axs[0].set(
        xlabel="Original 10 MS/s GLRT margin",
        ylabel="Filtered 2.5 MS/s GLRT margin",
        title="Same IQ, unchanged epoch/CFO seed",
        xlim=(-0.015, 0.86),
        ylim=(-0.025, 0.86),
    )
    axs[0].legend(loc="upper left", frameon=False)
    axs[0].text(
        0.02,
        0.04,
        "Red ring: acquired seed outside ±429.7 kHz",
        transform=axs[0].transAxes,
        fontsize=9,
        color="#9f2440",
    )
    retention = np.array([r["measured_tone_neighborhood_energy_retention"] for r in strong])
    im = axs[1].imshow(
        retention, aspect="auto", vmin=0, vmax=1, cmap="viridis", interpolation="nearest"
    )
    labels = [
        f"{'Dev' if r['split'] == 'development' else 'Eval'} "
        f"{'L' if r['edge'] == 'lower' else 'U'} CH{r['channel']} RX{r['receiver_id']}"
        for r in strong
    ]
    axs[1].set_yticks(range(len(labels)), labels)
    axs[1].set_xticks(range(8), range(1, 9))
    axs[1].set(
        xlabel="Tone neighborhood, ascending frequency",
        title="Measured energy retained near predicted tones",
    )
    fig.colorbar(im, ax=axs[1], label="After / before FIR (±60 kHz bands)", fraction=0.04)
    fig.suptitle(
        "Bandwidth narrowing separates search exclusion from signal filtering", fontsize=15, y=1.01
    )
    fig.text(
        0.5,
        -0.035,
        "Selected strong/marginal winners; no unbiased yield estimate. "
        "Tone positions use the annotated CFO convention; "
        "neighborhood energy includes interference.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(ROOT / "bandwidth-paired.png", bbox_inches="tight")
    plt.close(fig)
    acquisition = json.loads((ROOT / "reacquisition-results.json").read_text())

    def maximum(row, label):
        return max(
            (
                c["fractional_glrt"]["fractional_margin"]
                if c["fractional_glrt"]["fractional_margin"] is not None
                else c["integer_glrt"]["margin"]
                for c in row[label]["candidates"]
            ),
            default=0,
        )

    def winner(row, label):
        candidates = row[label]["candidates"]
        c = max(
            candidates,
            key=lambda c: (
                c["fractional_glrt"]["fractional_margin"]
                if c["fractional_glrt"]["fractional_margin"] is not None
                else c["integer_glrt"]["margin"]
            ),
        )
        a = c["acquisition"]
        nominal = (
            0 if label == "digitally_narrowed" else (-312500 if row["edge"] == "lower" else 312500)
        )
        return dict(
            rank=a["rank"],
            acquired_pilot_relative_hz=a["absolute_cfo_hz"] - nominal,
            frame_support=a["frame_support"],
            refinement_status=c["fractional_glrt"]["status"],
        )

    real = [r for r in acquisition["rows"] if r["kind"] == "saved_iq"]
    fig, ax = plt.subplots(figsize=(11, 5))
    xx = np.arange(len(real))
    for i, (label, text, color) in enumerate(
        [
            ("full", "10 MS/s, ±800 kHz", "#197e9c"),
            ("search_only", "10 MS/s, ±400 kHz", "#ce912c"),
            ("digitally_narrowed", "Filtered 2.5 MS/s, ±400 kHz", "#9e4270"),
        ]
    ):
        ax.bar(
            xx + (i - 1) * 0.25,
            [maximum(r, label) for r in real],
            width=0.23,
            color=color,
            label=text,
        )
    ax.set_xticks(
        xx,
        [
            f"{'Dev' if r['split'] == 'development' else 'Eval'} "
            f"{'L' if r['edge'] == 'lower' else 'U'}\nCH{r['channel']} RX{r['receiver_id']}"
            for r in real
        ],
    )
    ax.axhline(0.025, color="#555", ls="--", lw=1, label="Fixed 0.025 margin gate")
    ax.set(
        ylabel="Strongest re-acquired candidate margin",
        title="Score-blind probe selection, same saved IQ and 8-candidate budget",
    )
    ax.legend(frameon=False, ncol=2, fontsize=10)
    fig.tight_layout()
    fig.savefig(ROOT / "reacquisition-paired.png", bbox_inches="tight")
    plt.close(fig)
    summary = dict(
        reproduced=len(data["rows"]),
        maximum_replay_margin_error=max(r["published_margin_error"] for r in data["rows"]),
        selected=[],
    )
    for split in ["development", "evaluation"]:
        for bucket in ["strong", "marginal"]:
            rows = [r for r in high if r["split"] == split and r["lane"].endswith(bucket)]
            summary["selected"].append(
                dict(
                    split=split,
                    bucket=bucket,
                    n=len(rows),
                    narrow_seed_excluded=sum(not r["search_support_only_eligible"] for r in rows),
                    original_pass=sum(r["baseline"]["passed"] for r in rows),
                    filtered_pass=sum(r["digitally_narrowed"]["passed"] for r in rows),
                    median_margin_change=float(
                        np.median(
                            [
                                r["digitally_narrowed"]["margin"] - r["baseline"]["margin"]
                                for r in rows
                            ]
                        )
                    ),
                )
            )
    summary["reacquisition"] = []
    for kind in ["saved_iq", "gaussian_null"]:
        for split in ["development", "evaluation"]:
            rows = [r for r in acquisition["rows"] if r["kind"] == kind and r["split"] == split]
            summary["reacquisition"].append(
                dict(
                    kind=kind,
                    split=split,
                    n=len(rows),
                    pass_counts={
                        label: sum(maximum(r, label) >= 0.025 for r in rows)
                        for label in ["full", "search_only", "digitally_narrowed"]
                    },
                    margins=[
                        dict(
                            edge=r["edge"],
                            receiver_id=r["receiver_id"],
                            channel=r["channel"],
                            winners={
                                label: winner(r, label)
                                for label in ["full", "search_only", "digitally_narrowed"]
                            },
                            **{
                                label: maximum(r, label)
                                for label in ["full", "search_only", "digitally_narrowed"]
                            },
                        )
                        for r in rows
                    ],
                )
            )
    summary["conditioned_null_pass"] = dict(
        n=len(high),
        full=sum(r["null_full"]["passed"] for r in high),
        narrow=sum(r["null_narrow"]["passed"] for r in high),
    )
    budget = json.loads((ROOT / "budget-results.json").read_text())
    transport = json.loads((ROOT / "transport-results.json").read_text())
    br = [r for r in budget["rows"] if r["kind"] == "saved_iq"]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    xx = np.arange(len(br))
    transport_values = []
    primary_values = []
    for r in br:

        def match(p, selected=r):
            return (
                p["session_id"] == selected["session_id"]
                and p["receiver_id"] == selected["receiver_id"]
            )

        primary_values.append(maximum(next(p for p in real if match(p)), "digitally_narrowed"))
        transport_values.append(
            next(p for p in transport["rows"] if match(p))["search_only"]["transported_score"][
                "margin"
            ]
        )
    for i, (label, values, color) in enumerate(
        [
            ("Fresh acquisition: 8 basins", primary_values, "#9e4270"),
            ("Fresh acquisition: 16 basins", [maximum(r, "16") for r in br], "#ce912c"),
            ("Fresh acquisition: 32 basins", [maximum(r, "32") for r in br], "#197e9c"),
        ]
    ):
        ax.bar(xx + (i - 1) * 0.23, values, width=0.21, label=label, color=color)
    ax.scatter(
        xx,
        transport_values,
        s=100,
        marker="_",
        linewidths=3,
        color="#222",
        label="High-rate narrow seed transported to same filtered IQ",
        zorder=5,
    )
    ax.axhline(0.025, color="#777", ls="--", lw=1)
    ax.set_xticks(
        xx,
        [
            f"{'Dev' if r['split'] == 'development' else 'Eval'} "
            f"{'lower' if r['edge'] == 'lower' else 'upper'} RX1\nCH{r['channel']}"
            for r in br
        ],
    )
    ax.set(
        ylabel="Strongest GLRT margin",
        title=(
            "Post hoc: more basins recover two misses; two remain despite passing seeded evidence"
        ),
    )
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(ROOT / "acquisition-diagnostic.png", bbox_inches="tight")
    plt.close(fig)
    summary["posthoc_budget_check"] = dict(
        elapsed_seconds=budget["elapsed_seconds"],
        real=[
            dict(
                split=r["split"],
                edge=r["edge"],
                budget16_margin=maximum(r, "16"),
                budget32_margin=maximum(r, "32"),
            )
            for r in br
        ],
        gaussian_null_pass={
            b: sum(maximum(r, b) >= 0.025 for r in budget["rows"] if r["kind"] == "gaussian_null")
            for b in ("16", "32")
        },
    )
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
