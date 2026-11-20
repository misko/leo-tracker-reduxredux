"""Render stage-only acquisition evidence from the sealed causal-scout scores."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ..__main__ import save_json
from .causal_track_scout_stride import CASES as STRIDE
from .causal_track_scout_trial import ORDER, REPORT
from .input_factor_bridge import _sha, check, read


def percent(row, count, denom):
    return 100 * row[count] / row[denom]


def render():
    scores = read(REPORT / "score-lock.json")
    for n, h in scores["files"].items():
        check(REPORT / n, h)
    cases = read(REPORT / "scores.json")["cases"]
    ids = (*ORDER, *STRIDE)
    rows = [cases[i]["capture-family-missed/all"] for i in ids]
    d = tuple(range(len(ids)))
    fig, panels = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")

    ax = panels[0]
    for ys, label, color in (
        ([percent(row, "eligible", "targets") for row in rows], "Any causal start", "#bfd0e0"),
        ([percent(row, "hit_20", "targets") for row in rows], "Within 20 samples", "#46799e"),
        ([percent(row, "hit_2", "targets") for row in rows], "Within 2 samples", "#153d63"),
    ):
        ax.bar(d, ys, width=0.75, label=label, color=color)
    ax.set_title("Among all capture families missed by wide", loc="left", fontsize=11)
    ax.set_ylabel("Percent of missed capture families")
    ax.legend(loc="upper right", frameon=False, fontsize=8)

    ax = panels[1]
    a = [percent(row, "paired_hit_2", "paired") for row in rows]
    b = [percent(row, "null_hit_2", "paired") for row in rows]
    ax.bar([x - 0.18 for x in d], a, 0.34, color="#153d63", label="Causal start")
    ax.bar([x + 0.18 for x in d], b, 0.34, color="#c88853", label="Time-shift control")
    ax.set_title("Within 2 samples on matched eligible probes", loc="left", fontsize=11)
    ax.set_ylabel("Percent of probes with a permutation partner")
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    for axes in panels:
        axes.set_xticks(d, [i.removeprefix("DS") for i in ids], rotation=38, ha="right")
        axes.tick_params(axis="both", labelsize=8)
        axes.spines[["top", "right"]].set_visible(False)
        axes.set_axisbelow(True)
        axes.yaxis.grid(True, color="#dfe5ec", linewidth=0.6)
    fig.suptitle("Causal pilot-start proposals on saved four-start wide streams", x=0.01, ha="left")
    for suffix in ("png", "pdf"):
        fig.savefig(REPORT / f"causal-track-scout.{suffix}", dpi=170)
    plt.close(fig)
    files = {
        n: _sha(REPORT / n)
        for n in (
            "scores.csv",
            "scores.json",
            "score-lock.json",
            "causal-track-scout.png",
            "causal-track-scout.pdf",
        )
    }
    save_json(
        REPORT / "stage-figure-manifest.json",
        dict(
            id="causal-track-scout",
            scope="detector stage",
            position_attempted=False,
            cases=list(ids),
            files=files,
            publisher_sha256=_sha(Path(__file__)),
        ),
    )
    save_json(
        REPORT / "stage-figure-lock.json",
        dict(
            files=files
            | {"stage-figure-manifest.json": _sha(REPORT / "stage-figure-manifest.json")},
        ),
    )


if __name__ == "__main__":
    render()
