"""Plot frozen phase profiles and paired position receipts."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
TEAL, SLATE = "#087c82", "#5e6882"


def phase_curves():
    rows = json.loads((HERE / "diagnostic-phase-profiles.json").read_bytes())
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for data, (loss, family) in zip(rows, axes, strict=True):
        target = next(x for x in data["curves"] if x["graph_track"] == data["target"])
        for i, item in enumerate(target["finalists"][:4]):
            c = (
                TEAL
                if item["norad"] == data["published_norad"]
                else [SLATE, "#965e35", ".55"][i - 1]
            )
            loss.plot(
                data["phases"],
                item["cost_profile"],
                color=c,
                label=f"{item['norad']} · rank {item['rank']}",
            )
        basin = data["fitted_basin"]
        loss.axvline(basin["phase_s"], color=TEAL, ls="--", lw=1.1, label="Frozen family basin")
        loss.axvspan(-7.5, 7.5, color=".8", alpha=0.20, label="Nominal phase bounds")
        loss.set(
            title=f"{data['id']} · target Graph {data['target']}",
            xlabel="Orbit phase (s)",
            ylabel="Best sentinel cost",
            yscale="log",
            ylim=(0.025, 1000),
        )
        loss.legend(fontsize=8, ncol=2)
        for i, item in enumerate(data["curves"]):
            tie = item["expected_loss_at_shared_basin"]
            if tie is None:
                continue
            role = (
                "Noncurved"
                if not item["curved"]
                else (
                    "Downstream holdout"
                    if item["downstream_holdout"]
                    else ("Anchor check" if item["acquisition_check"] else "Anchor training")
                )
            )
            color = {
                "Noncurved": ".55",
                "Downstream holdout": "#9b6753",
                "Anchor check": SLATE,
                "Anchor training": TEAL,
            }[role]
            family.scatter(tie, i, s=44, color=color, label=role)
        family.axvline(6.25, ls="--", color=".6", label="Single-track cost limit")
        family.set(
            xlabel="Cost at single frozen orbit/phase/site basin",
            title="Published family components",
            xscale="log",
            xlim=(0.008, 9),
            yticks=range(len(data["curves"])),
            yticklabels=[f"Graph {r['graph_track']}" for r in data["curves"]],
        )
        handles, labels = family.get_legend_handles_labels()
        legend = dict(zip(labels, handles, strict=True))
        family.legend(legend.values(), legend.keys(), loc="upper left", fontsize=7)
    fig.savefig(HERE / "causal-phase-profiles.png", dpi=160)
    plt.close(fig)


def positions():
    rows = json.loads((HERE / "summary.json").read_bytes())["scores"]
    cases = list(dict.fromkeys(r["id"] for r in rows))
    figure, axes = plt.subplots(2, 2, figsize=(13, 7.5), constrained_layout=True)
    for arm, (position, frequency) in zip(("c0", "fitted_c"), axes, strict=True):
        for j, (method, color, label) in enumerate(
            (
                ("native_joint_orbits", SLATE, "Archived nominal joint"),
                ("phase_capture", TEAL, "Blind phase and joint"),
            )
        ):
            by_id = {r["id"]: r for r in rows if r["arm"] == arm and r["method"] == method}
            index = np.arange(len(cases)) + (j - 0.5) * 0.22
            published = [by_id[c]["error_km"] for c in cases]
            forced = [
                by_id[c]["forced_error_km"] if by_id[c]["error_km"] is None else None for c in cases
            ]
            position.scatter(index, published, color=color, label=label, s=30)
            position.scatter(index, forced, edgecolor=color, facecolor="none", s=34)
            frequency.scatter(
                index,
                [by_id[c]["conditional_rms_hz"] for c in cases],
                color=color,
                s=30,
                label=label,
            )
        position.set(
            ylabel="Distance to released GNSS (km)",
            title=("c=0" if arm == "c0" else "Fitted c") + " · position",
        )
        frequency.set(
            ylabel="RF residual RMS (Hz)",
            title=("c=0" if arm == "c0" else "Fitted c") + " · fitted observations",
        )
        for ax in (position, frequency):
            ax.axvline(1.5, color=".7", lw=1)
            ax.axvline(5.5, color=".7", lw=1)
            ax.set_xticks(
                range(len(cases)),
                [s.replace("-omitted", "\n(omitted)") for s in cases],
                rotation=34,
                ha="right",
                fontsize=8,
            )
    axes[0, 1].legend(fontsize=8)
    figure.suptitle(
        "Two diagnostics · four confirmation cases · two authentic omitted tiles\n"
        "Solid position markers published · hollow position markers forced"
    )
    figure.savefig(HERE / "paired-positions.png", dpi=160)
    plt.close(figure)


if __name__ == "__main__":
    phase_curves()
    positions()
    paths = sorted(p for p in HERE.iterdir() if p.is_file() and p.name != "artifact-lock.json")
    (HERE / "artifact-lock.json").write_text(
        json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}, indent=2)
        + "\n"
    )
