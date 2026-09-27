"""Rebuild publication figures from the included frozen JSON evidence.

Requires Python and matplotlib. Run from any directory: python plot.py.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
FIGURES = HERE / "figures"
FIGURES.mkdir(exist_ok=True)
plt.rcParams.update({"font.size": 11, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.facecolor": "white"})


def read(name):
    return json.loads((EVIDENCE / name).read_text())


def save(fig, name):
    fig.savefig(FIGURES / f"{name}.png", dpi=170, bbox_inches="tight")
    svg = FIGURES / f"{name}.svg"
    fig.savefig(svg, bbox_inches="tight")
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    plt.close(fig)


joint = read("joint-score.json")["trials"][0]["horizontal_error_m"]
fig, ax = plt.subplots(figsize=(10, 4))
ax.barh([1, 0], [809.029031551158, joint], color=["#aab4bf", "#087f8c"])
ax.set_yticks([1, 0], ["Inherited coordinate\n(no DS7 observations)", "All 88 recordings\n(frozen joint model)"])
for y, value in zip([1, 0], [809.029031551158, joint]):
    ax.text(value + 12, y, f"{value:,.1f} m", va="center")
ax.axvline(1000, color="#b34435", linestyle="--", label="1 km target")
ax.set(xlim=(0, 1160), xlabel="Horizontal error against unsurveyed reference (m)",
       title="Full DS7 pooled result: 677 m over a 10.3-hour capture span")
ax.legend(loc="lower right")
fig.text(.02, -.05, "Contextual comparison, not an isolated prior ablation. All three full88 position controls abstained.", fontsize=10)
save(fig, "pooled-result")

panels = read("group-panels.json")["panels"]
fig, ax = plt.subplots(figsize=(11, 5))
for key, label, color in [("scientific_joint", "Joint", "#087f8c"),
                          ("equal", "Equal mean", "#bb6730"),
                          ("inverse_rms2", "Inverse RMS²", "#7654a3"),
                          ("lowest_rms75", "Lowest RMS 75%", "#727b2d")]:
    ax.plot(range(1, 12), [p["methods"][key]["horizontal_error_m"] or float("nan")
                          for p in panels], marker="o", label=label, color=color)
ax.axhline(1000, color="#b34435", linestyle="--", label="1 km")
ax.annotate("Group 8: all three\ncontrols abstained", xy=(8, 1545), xytext=(8.2, 4650),
            arrowprops={"arrowstyle": "->", "color": "#555"}, fontsize=10)
ax.set(xticks=range(1, 12), xlabel="Chronological group (8 recordings each)",
       ylabel="Horizontal error (m)", title="Temporal variability remains: only 3 of 11 joint panels below 1 km")
ax.legend(ncol=3, loc="upper left")
ax.grid(axis="y", alpha=.2)
save(fig, "group-comparison")

trials = read("individual-outcomes.json")["trials"]
fig, ax = plt.subplots(figsize=(11, 4.5))
for qualified, label, color, marker in [(True, "Qualified (87)", "#087f8c", "o"),
                                       (False, "Boundary / unqualified (1)", "#b34435", "X")]:
    rows = [(i + 1, t["error_m"]) for i, t in enumerate(trials) if t["qualified"] == qualified]
    ax.scatter(*zip(*rows), label=label, color=color, marker=marker, s=30)
ax.axhline(1000, color="#b34435", linestyle="--", label="1 km")
ax.set(xlabel="Recording ordinal", ylabel="Horizontal error (m, log scale)", yscale="log",
       title="Individual recordings: 13 / 88 below 1 km; median returned error 2.57 km")
ax.legend(loc="upper left", ncol=3)
ax.grid(axis="y", alpha=.2)
save(fig, "individual-errors")
