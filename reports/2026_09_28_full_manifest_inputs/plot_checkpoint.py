"""Plot explicit validated versus pending complete-manifest membership."""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
folder = HERE / "checkpoints" / sys.argv[1]
groups = json.loads((folder / "panel-inputs.json").read_text())["groups"]
assert not (folder / "coverage.png").exists()
fig, ax = plt.subplots(figsize=(8, 4), layout="constrained")
labels = [g["dataset_id"] for g in groups]
ready = [g["validated_records"] for g in groups]
missing = [g["requested_records"] - g["validated_records"] for g in groups]
ax.barh(labels, ready, color="tab:green", label="Validated scientific inputs")
ax.barh(labels, missing, left=ready, color="lightgray", label="Still pending")
for index, group in enumerate(groups):
    ax.text(
        group["requested_records"] + 1,
        index,
        f"{group['validated_records']}/{group['requested_records']}",
        va="center",
    )
ax.set_xlim(0, max(g["requested_records"] for g in groups) + 18)
ax.set_xlabel("Recording count in frozen dataset manifest")
ax.set_title("Full-manifest input readiness — " + sys.argv[1])
ax.invert_yaxis()
ax.legend(loc="lower right", fontsize=8)
fig.savefig(folder / "coverage.png", dpi=170)
fig.savefig(folder / "coverage.svg")
