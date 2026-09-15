"""Describe supported native feedback without claiming raw-IQ accuracy."""

import hashlib, json, statistics
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = Path(__file__).parent
root = BASE / "live-scan64-30-v1"
source = root / "native-epoch-estimate-review.json"
review = json.loads(source.read_text())
assert review["status"] == "pass" and review["native_results"] == 1500
episode = review["episodes"][0]
rows = episode["estimates"]
streak = maximum = 0
for row in rows:
    streak = streak + 1 if row["rejection"] else 0
    maximum = max(maximum, streak)
classes = []
for phase in range(3):
    selected = [r for r in rows if r["frame"] % 3 == phase]
    classes.append(
        dict(
            frame_modulo_3=phase,
            count=len(selected),
            supported=sum(r["rejection"] == 0 for r in selected),
            median_coherence=statistics.median(r["coherence"] for r in selected),
        )
    )
observer = [json.loads(line) for line in (root / "observer.jsonl").read_text().splitlines()]
observations = [r for r in observer if r["kind"] == "measurement"]
result = dict(
    native_results=len(rows),
    supported=review["supported"],
    maximum_consecutive_rejections=maximum,
    first_frame=episode["first_frame"],
    final_frame=episode["final_frame"],
    last_supported_frame=episode["last_supported_frame"],
    controller_result=episode["controller_result"],
    frame_budget_seconds=len(rows) / 750,
    classes=classes,
    observer_measurements=len(observations),
    observer_supported=sum(r["accepted"] for r in observations),
    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
)
with (root / "support-summary.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True, layout="constrained")
origin = rows[0]["frame"]
for phase, color in enumerate(["#0072B2", "#D55E00", "#CC79A7"]):
    selected = [r for r in rows if r["frame"] % 3 == phase]
    axes[0].scatter(
        [(r["frame"] - origin) / 750 for r in selected],
        [r["coherence"] for r in selected],
        s=8,
        alpha=0.7,
        color=color,
        label=f"frame % 3 = {phase}: {classes[phase]['supported']}/500 supported",
    )
axes[1].scatter(
    [(r["frame"] - origin) / 750 for r in observations],
    [r["coherence"] for r in observations],
    s=10,
    color="#009E73",
    label="ARM observer: 200/200 supported",
)
for ax in axes:
    ax.axhline(0.05, color="black", ls="--", lw=1, label="Existing 0.05 gate")
    ax.set_ylabel("Power coherence")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8, loc="upper right")
axes[0].set_title(
    "30 MS/s live native feedback: 1,500 results, 972 supported, maximum rejection run 3"
)
axes[1].set_xlabel("Seconds relative to first native frame")
axes[1].set_xlim(-0.025, 2)
fig.savefig(root / "support.png", dpi=160)
print(json.dumps(result))
