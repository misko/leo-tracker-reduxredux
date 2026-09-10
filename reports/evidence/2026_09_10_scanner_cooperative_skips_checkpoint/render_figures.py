"""Rebuild checkpoint PNGs from retained metrics only; never opens RF or HTTP."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

root = Path(__file__).parent
figures = root.parent.parent / "figures" / root.name
profile = json.loads((root / "desktop-profile.json").read_text())["summary"]
production = json.loads((root / "production-summary.json").read_text())
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
colors = ["#1b9e77", "#377eb8"]
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
for ax, title, values in zip(
    axes,
    ["Valid IQ capture duty", "Dwells temporally screened"],
    [
        [94.5483, production["capture_duty_percent"]],
        [100, production["temporal_screening_percent"]],
    ],
    strict=True,
):
    bars = ax.bar(
        ["2.5 MS/s\nadaptive verification", "5 MS/s\nscheduled fixed order"],
        values,
        color=colors,
        width=0.6,
    )
    ax.bar_label(bars, labels=[f"{value:.2f}%" for value in values], padding=4)
    ax.set(ylim=(0, 112), ylabel="Percent", title=title)
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=0.2)
fig.suptitle("Capture continues even when advisory GLRT cannot keep up", fontweight="bold")
fig.savefig(figures / "capture-vs-screening.png", dpi=180)
plt.close(fig)

fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
rates = ("2500000", "5000000")
parts = [
    ("Ranking (six windows)", "ranking", "#1b9e77"),
    ("Coarse acquisition", "confirmation_coarse", "#377eb8"),
    ("Fine search", "confirmation_fine", "#984ea3"),
    ("Fractional confirmation", "confirmation_fractional", "#e69f00"),
]
left = np.zeros(2)
for label, key, color in parts:
    widths = np.array([profile[rate][key]["mean_ms"] for rate in rates])
    ax.barh([0, 1], widths, left=left, label=label, color=color, height=0.45)
    left += widths
total = np.array([profile[rate]["whole_dwell"]["mean_ms"] for rate in rates])
assert np.all(total >= left)
ax.barh(
    [0, 1],
    total - left,
    left=left,
    label="Conversion, other work and timing overhead",
    color="#999999",
    height=0.45,
)
for y, value in enumerate(total):
    ax.text(value + 0.025, y, f"{value:.3f} ms", va="center")
ax.set(
    yticks=[0, 1],
    yticklabels=["2.5 MS/s", "5 MS/s"],
    xlim=(0, 1.95),
    xlabel="Mean CPU milliseconds per 120 ms saved RX1 dwell — desktop FFTW only",
    title="Optimization map, not an ARM speed prediction\n"
    "Eight distinct saved dwells per rate; three measured repetitions per dwell",
)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False)
ax.set_axisbelow(True)
ax.grid(axis="x", alpha=0.2)
fig.savefig(figures / "desktop-stage-profile.png", dpi=180)
plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
targets = production["per_target"]
counts = np.array([target["screened"] for target in targets])
visits = np.array([target["visits"] for target in targets])
bars = ax.bar(np.arange(8), 100 * counts / visits, color=[colors[1]] * 4 + [colors[0]] * 4)
ax.bar_label(bars, labels=[f"{n}/{d}" for n, d in zip(counts, visits, strict=True)], padding=3)
ax.set(
    xticks=np.arange(8),
    xticklabels=[f"CH{i}{edge}" for edge in "LU" for i in range(1, 5)],
    ylim=(0, 45),
    ylabel="Screened visits / captured visits (%)",
    title="5 MS/s: balanced RF visits do not imply balanced GLRT coverage\n"
    "Existing scheduled fixed-order capture; no new prototype enabled",
)
ax.set_axisbelow(True)
ax.grid(axis="y", alpha=0.2)
fig.savefig(figures / "screening-by-target.png", dpi=180)
plt.close(fig)

items = []
for path in sorted([*root.iterdir(), *figures.iterdir()]):
    if path.is_file() and path.name != "index.json":
        payload = path.read_bytes()
        items.append(
            dict(
                path=str(path.relative_to(root.parent.parent)),
                bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
with (root / "index.json").open("w") as stream:
    json.dump(
        dict(
            artifacts=items,
            contents="Public metrics, recipes, tests and figures; no IQ or binaries.",
        ),
        stream,
        indent=2,
    )
print(f"Rendered 3 figures; indexed {len(items)} public artifacts.")
