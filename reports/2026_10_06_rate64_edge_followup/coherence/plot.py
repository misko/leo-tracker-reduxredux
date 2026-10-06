"""Render the report's frozen comparison and clearly labeled exploration."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
plt.rcParams.update(
    {
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
    }
)
COLORS = {"development": "#64748b", "evaluation": "#006b8f"}


def main():
    primary = json.loads((ROOT / "results.json").read_text())
    r = primary["results"]
    exploration = json.loads((ROOT / "exploratory_cfo_results.json").read_text())
    secondary = exploration["results"]
    out = ROOT / "figures"
    out.mkdir(exist_ok=True)
    fig, axs = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for i, group in enumerate(("strong", "marginal")):
        for split in ("development", "evaluation"):
            rows = [x for x in r if x["split"] == split and x["lane"].endswith(group)]
            axs[i, 0].scatter(
                [x["legacy"]["best"]["margin"] for x in rows],
                [x["physical"]["best"]["margin"] for x in rows],
                c=COLORS[split],
                label=f"{split} (n={len(rows)})",
                alpha=0.85,
                s=40,
            )
        bounds = (0, 0.86) if group == "strong" else (0, 0.026)
        axs[i, 0].plot(bounds, bounds, c="#94a3b8", lw=1)
        axs[i, 0].set(
            xlim=bounds,
            ylim=bounds,
            xlabel="Current-template margin, matched timing",
            ylabel="Continuous-mixer margin, matched timing",
            title=f"Selected {group} examples",
        )
        axs[i, 0].legend(frameon=False, fontsize=9)
        groups = [(2500000, "lower"), (2500000, "upper"), (10000000, "lower"), (10000000, "upper")]
        for j, (rate, edge) in enumerate(groups):
            for split, offset in (("development", -0.12), ("evaluation", 0.12)):
                rows = [
                    x
                    for x in r
                    if x["rate"] == rate
                    and x["edge"] == edge
                    and x["split"] == split
                    and x["lane"].endswith(group)
                ]
                values = [
                    x["physical"]["best"]["margin"] - x["legacy"]["best"]["margin"] for x in rows
                ]
                axs[i, 1].scatter(
                    j + offset + np.linspace(-0.05, 0.05, len(values)),
                    values,
                    c=COLORS[split],
                    s=38,
                    alpha=0.85,
                )
                axs[i, 1].plot(
                    [j + offset - 0.08, j + offset + 0.08],
                    [np.median(values)] * 2,
                    c=COLORS[split],
                    lw=3,
                )
        axs[i, 1].axhline(0, c="#94a3b8", lw=1)
        axs[i, 1].set(
            xticks=range(4),
            xticklabels=["2.5M lower", "2.5M upper", "10M lower", "10M upper"],
            ylabel="Physical − current margin",
            title="Dots: examples; bars: group medians",
        )
    fig.suptitle(
        "Frozen timing-only comparison: same selected seeds, seven timing cells and GLRT grid",
        fontsize=14,
    )
    fig.savefig(out / "template_comparison.png", dpi=170)
    plt.close(fig)

    # All 31 strong selected examples retain their individual lane identity.
    rows = sorted(
        [x for x in r if x["lane"].endswith("strong")],
        key=lambda x: (x["rate"], x["edge"], x["channel"], x["receiver_id"], x["split"]),
    )
    labels = [
        f"{x['rate'] / 1e6:g}M {x['edge'][:1]} CH{x['channel']} "
        f"RX{x['receiver_id']} {x['split'][:3]}"
        for x in rows
    ]
    fig, axs = plt.subplots(1, 2, figsize=(11, 12), layout="constrained")
    amplitude = np.array([x["projection"]["tone_relative_amplitude_db"] for x in rows])
    coherence = np.array([x["projection"]["tone_coherence_median"] for x in rows])
    a = axs[0].imshow(amplitude, aspect="auto", cmap="RdBu_r", vmin=-10, vmax=10)
    b = axs[1].imshow(coherence, aspect="auto", cmap="viridis", vmin=0, vmax=1)
    axs[0].set_yticks(range(len(rows)), labels=labels)
    axs[1].set_yticks(range(len(rows)), labels=[])
    for ax in axs:
        ax.set(
            xticks=range(8),
            xticklabels=range(1, 9),
            xlabel="Tone in ascending pilot-frequency order",
        )
    axs[0].set_title("Empirical complex-gain amplitude\ndB relative to each example's median tone")
    axs[1].set_title(
        "Median within-frame per-tone coherence\n|sum over 64 symbols| / sum magnitudes"
    )
    fig.colorbar(a, ax=axs[0], label="dB; colors clipped at ±10 dB", shrink=0.55)
    fig.colorbar(b, ax=axs[1], label="coherence", shrink=0.55)
    fig.suptitle(
        "Eight-tone projection after physical CFO/timing correction\n"
        "Selected strong candidates; signal/channel/noise/timing all contribute",
        fontsize=14,
    )
    fig.savefig(out / "empirical_tone_response.png", dpi=160)
    plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(12, 4.7), layout="constrained")
    for kind, color in (("strong", "#006b8f"), ("marginal", "#b45309")):
        selected = [x for x in r if x["lane"].endswith(kind)]
        axs[0].scatter(
            [x["projection"]["amplitude_spread_db"] for x in selected],
            [np.median(x["projection"]["tone_coherence_median"]) for x in selected],
            s=40,
            c=color,
            label=f"selected {kind}",
            alpha=0.75,
        )
        axs[1].scatter(
            [x["physical"]["best"]["margin"] for x in selected],
            [x["plus_symbol_physical"]["best"]["margin"] for x in selected],
            s=40,
            c=color,
            alpha=0.75,
        )
    axs[0].set(
        xlabel="Projected tone amplitude max/min spread (dB)",
        ylabel="Median projected per-tone coherence",
        title="Strong and marginal projections differ",
    )
    axs[0].legend(frameon=False)
    axs[1].axhline(0.025, c="#b91c1c", ls="--", label="published gate .025")
    axs[1].set(
        xlabel="Selected candidate's physical-template margin",
        ylabel="One-symbol-shift optimized margin",
        title="Same seven-cell optimization for shifted controls",
    )
    axs[1].legend(frameon=False)
    fig.suptitle(
        "Empirical projection and specificity controls; "
        "selected data do not calibrate false alarms",
        fontsize=13,
    )
    fig.savefig(out / "coherence_and_controls.png", dpi=170)
    plt.close(fig)

    fig, axs = plt.subplots(1, 3, figsize=(15, 4.7), layout="constrained")
    for split in ("development", "evaluation"):
        rows = [x for x in secondary if x["split"] == split and x["lane"].endswith("strong")]
        original = {(x["session_id"], x["lane"]): x for x in r}
        axs[0].scatter(
            [original[(x["session_id"], x["lane"])]["physical"]["best"]["margin"] for x in rows],
            [x["physical"]["best"]["margin"] for x in rows],
            c=COLORS[split],
            label=split,
            s=40,
        )
    axs[0].plot([0, 0.9], [0, 0.9], c="#94a3b8", lw=1)
    axs[0].set(
        xlabel="Primary physical margin (timing only)",
        ylabel="Exploratory physical margin (timing + CFO)",
        title="All selected strong examples",
    )
    axs[0].legend(frameon=False)
    outliers = sorted(
        [x for x in r if x["lane"].endswith("strong")],
        key=lambda x: x["physical"]["best"]["margin"] - x["legacy"]["best"]["margin"],
    )[:2]
    by_key = {(x["session_id"], x["lane"]): x for x in secondary}
    for ax, o in zip(axs[1:], outliers, strict=True):
        e = by_key[(o["session_id"], o["lane"])]
        for key, color in (("legacy", "#64748b"), ("physical", "#006b8f")):
            for delta, style in ((-20000, "--"), (0, "-"), (20000, ":")):
                a = [x for x in e[key]["trials"] if x["acquired_cfo_offset_hz"] == delta]
                ax.plot(
                    [x["offset_samples"] for x in a],
                    [x["margin"] for x in a],
                    color=color,
                    ls=style,
                    label=f"{key} {delta / 1000:+g} kHz",
                )
        ax.set(
            xlabel="Timing offset from saved fractional seed (samples)",
            ylabel="Margin",
            title=f"2.5M upper RX1 {o['split']}\n{o['lane']} visit {o['visit_index']}",
        )
        ax.legend(frameon=False, fontsize=7)
    fig.suptitle(
        "Exploratory CFO extension: identical ±20 kHz / 0 cells, "
        "all candidates and shifted controls\n"
        "Chosen after evaluation inspection; this is not held-out validation",
        fontsize=13,
    )
    fig.savefig(out / "exploratory_cfo_alias_boundary.png", dpi=170)
    plt.close(fig)

    # Fully machine-readable aggregates; retain all row-level trial results.
    summary = {
        "primary_count": len(r),
        "primary_elapsed_seconds": primary["elapsed_seconds"],
        "exploratory_elapsed_seconds": exploration["elapsed_seconds"],
        "max_reproduction_error": max(max(x["saved_reproduction_max_errors"].values()) for x in r),
        "groups": [],
    }
    for label, data in (("primary", r), ("exploratory", secondary)):
        for split in ("development", "evaluation"):
            for kind in ("strong", "marginal"):
                rows = [x for x in data if x["split"] == split and x["lane"].endswith(kind)]
                delta = np.array(
                    [x["physical"]["best"]["margin"] - x["legacy"]["best"]["margin"] for x in rows]
                )
                summary["groups"].append(
                    {
                        "analysis": label,
                        "split": split,
                        "kind": kind,
                        "n": len(rows),
                        "margin_delta_median": float(np.median(delta)),
                        "margin_delta_mean": float(np.mean(delta)),
                        "positive_delta_count": int(np.sum(delta > 0)),
                        "physical_margin_max_shifted_control": max(
                            x["plus_symbol_physical"]["best"]["margin"] for x in rows
                        ),
                        "tone_coherence_median": float(
                            np.median(
                                [np.median(x["projection"]["tone_coherence_median"]) for x in rows]
                            )
                        ),
                        "tone_spread_db_median": float(
                            np.median([x["projection"]["amplitude_spread_db"] for x in rows])
                        ),
                    }
                )
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
