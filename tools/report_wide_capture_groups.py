import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

parser = argparse.ArgumentParser(description="Evaluate and plot sealed acquisition-group fits")
for name in ["inference", "reference", "output"]:
    parser.add_argument("--" + name, type=Path, required=True)
args = parser.parse_args()
out = args.output
out.mkdir(exist_ok=False)
source = args.inference
sealed = hashlib.sha256(source.read_bytes()).hexdigest()
r = json.loads(source.read_text())
reference = args.reference
truth = json.loads(reference.read_text())
a, b = map(math.radians, [truth["latitude_deg"], truth["longitude_deg"]])
rows = []
for m in r["models"]:
    if "latitude_deg" not in m:
        continue
    c, d = map(math.radians, [m["latitude_deg"], m["longitude_deg"]])
    h = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
    rows.append(
        dict(
            grouping=m["grouping"],
            group=m["group"],
            cohort=m["cohort"],
            clock_fitted=m["clock_fitted"],
            error_m=12742017.6 * math.asin(math.sqrt(h)),
            north_m=6371008.8 * (c - a),
            east_m=6371008.8 * math.cos(a) * (d - b),
        )
    )
(out / "evaluation.json").write_text(
    json.dumps(
        dict(
            inference_sha256=sealed,
            reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
            rows=rows,
        ),
        indent=2,
    )
    + "\n"
)
shutil.copy2(source, out / "inference.json")
fig, axes = plt.subplots(1, 2, figsize=(14, 6), layout="constrained", sharex=True, sharey=True)
keys = list(dict.fromkeys((r["grouping"], r["group"]) for r in rows))
colors = {k: plt.cm.tab10(i) for i, k in enumerate(keys)}
for ax, clock in zip(axes, [False, True], strict=True):
    for row in rows:
        if row["clock_fitted"] != clock:
            continue
        key = (row["grouping"], row["group"])
        label = (
            str(int(row["group"]) // 1000000) + " MS/s"
            if key[0] == "sample_rate_hz"
            else "CH" + row["group"]
            if key[0] == "channel"
            else row["group"][5:13].replace("T", " ") + " UTC"
            if key[0] == "utc_6h"
            else row["group"]
        )
        ax.scatter(
            row["east_m"] / 1000,
            row["north_m"] / 1000,
            c=[colors[key]],
            marker="o" if row["cohort"] == "all" else "x",
            label=label if row["cohort"] == "all" else None,
        )
    ax.add_patch(plt.Circle((0, 0), 1, fill=False, color="gray", ls="--"))
    ax.plot(0, 0, "k*", ms=12)
    ax.set(
        title="Shared clock ±0.5 s" if clock else "Fixed recorded UTC",
        xlabel="East of reference (km)",
        ylabel="North of reference (km)",
        aspect="equal",
    )
    ax.grid(alpha=0.2)
axes[1].legend(fontsize=8, ncol=3)
fig.suptitle(
    "Independent-wide assignments: acquisition-group sensitivity\n"
    "Circles: all retained tracks; crosses: frozen quality selection; dashed circle: 1 km"
)
fig.savefig(out / "group-positions.png", dpi=160)
plt.close(fig)
(out / "sha256.json").write_text(
    json.dumps(
        {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()},
        indent=2,
    )
    + "\n"
)
