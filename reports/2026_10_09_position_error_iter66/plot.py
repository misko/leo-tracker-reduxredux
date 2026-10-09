"""Provenance diagram; not an accuracy plot or new experimental result."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
fig, ax = plt.subplots(figsize=(13, 7), layout="constrained")
ax.set(xlim=(0, 13), ylim=(0, 7))
ax.axis("off")


def box(x, y, text, color):
    ax.text(
        x,
        y,
        text,
        ha="center",
        va="center",
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.6", facecolor=color, edgecolor="#53616a"),
    )


def arrow(x0, y0, x1, y1):
    ax.annotate(
        "", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="->", color="#53616a", lw=1.7)
    )


ax.text(
    6.5,
    6.7,
    "Shared satellite inventory does not erase seed ancestry",
    ha="center",
    fontsize=17,
    weight="bold",
)
box(2.2, 5.4, "Reference-guided region\nLocal bank + zero-timing source", "#ffe0cc")
box(6.5, 5.4, "Receiver-pair clock proposals\nBoth anchors, both c arms", "#ffe0cc")
box(10.7, 5.4, "Selected zero-c joint solution\nContinue with c free", "#ffe0cc")
arrow(3.9, 5.4, 4.6, 5.4)
arrow(8.2, 5.4, 9.0, 5.4)
box(2.2, 3.35, "Ordinary regional inventory\nUnion of 145 satellites", "#dceef7")
box(6.5, 3.35, "Common bank + clock frame\nRecovered joint seed refit", "#ffe0cc")
box(10.7, 3.35, "1.15 km fitted-c\nDIAGNOSTIC ONLY", "#ffe0cc")
arrow(3.9, 3.35, 4.65, 3.35)
arrow(10.7, 4.8, 7.5, 3.95)
arrow(8.25, 3.35, 9.25, 3.35)
box(2.2, 1.3, "Ordinary regional endpoints\nNo recovered joint seed", "#dceef7")
box(6.5, 1.3, "Direct common-bank fits\nHard / smooth pilots running", "#dceef7")
box(10.7, 1.3, "Next: apply clock proposals +\ncross-arm continuation uniformly", "#e4f2df")
arrow(2.2, 2.75, 2.2, 1.9)
arrow(3.9, 1.3, 4.7, 1.3)
arrow(8.25, 1.3, 8.85, 1.3)
ax.text(
    6.5,
    0.15,
    "Known receiver coordinates: evaluation only, after operational selection",
    ha="center",
    fontsize=11,
)
fig.savefig(HERE / "lineage.png", dpi=160)
