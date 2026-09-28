"""Verify preflight bindings and distances, then plot the two individual scores."""

import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "plan.json").read_text())
scores = json.loads((HERE / "scores.json").read_text())
assert [r["unit_id"] for r in scores["rows"]] == [r["unit_id"] for r in plan["captures"]]
bindings = {}
for launch in (HERE / "receipts").glob("*/*/launch.json"):
    assert launch.with_name("exit-code.txt").read_text().strip() == "0"
    bindings.update(json.loads(launch.read_text())["sha256"])
for path in (HERE / "solver").glob("*/fit-seal.json"):
    bindings.update(json.loads(path.read_text())["sha256"])
for name, expected in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
scored = [r for r in scores["rows"] if r["state"] == "scored"]
assert len(scored) == 2 and sum(r["state"] == "pending" for r in scores["rows"]) == 14


def vector(lat, lon):
    a, b = np.radians([lat, lon])
    return np.array([np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)])


for row in scored:
    source = next(s for s in plan["sources"] if s["dataset_id"] == row["dataset_id"])
    manifest_path = ROOT / source["path"]
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == source["sha256"]
    pose_path = manifest_path.parent / "pose" / (row["session_id"] + ".json")
    assert "sha256:" + hashlib.sha256(pose_path.read_bytes()).hexdigest() == row["pose_file_sha256"]
    authority = json.loads(pose_path.read_text())["pose_authority"]
    a = vector(row["estimate"]["latitude_deg"], row["estimate"]["longitude_deg"])
    b = vector(authority["latitude_deg"], authority["longitude_deg"])
    alternative = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b))
    assert abs(alternative - row["horizontal_error_m"]) < 1e-4
    held = json.loads((HERE / "solver" / row["unit_id"] / "held-evaluation.json").read_text())
    assert abs(sum(t["held_log_score"] for t in held["tracks"]) - row["held_log_score"]) < 1e-8
audit = {
    "status": "pass",
    "bindings_checked": len(bindings),
    "scored": 2,
    "pending": 14,
    "scope": (
        "Binding, membership and independent distance arithmetic; no second fit implementation."
    ),
}
audit_path = HERE / "audit-summary.json"
if audit_path.exists():
    assert json.loads(audit_path.read_text()) == audit
else:
    with audit_path.open("x") as stream:
        json.dump(audit, stream, indent=2)
fig, ax = plt.subplots(figsize=(7, 4), constrained_layout=True)
values = [r["horizontal_error_m"] / 1000 for r in scored]
bars = ax.bar([r["unit_id"] for r in scored], values, color=["#347c91", "#c99742"], width=0.5)
ax.bar_label(bars, labels=[f"{v:.3f} km" for v in values], padding=5)
ax.axhline(1, color="black", linewidth=1, linestyle=":", label="1 km target")
ax.set(
    ylabel="Horizontal error (km)",
    ylim=(0, 10),
    title="Baseline preflight: first chronological record per dataset",
    xlabel="Individual-record budget; remaining 14 panel records pending",
)
ax.text(
    0.98,
    1.12,
    "1 km target",
    transform=ax.get_yaxis_transform(),
    ha="right",
    va="bottom",
    bbox={"facecolor": "white", "edgecolor": "none"},
)
fig.savefig(HERE / "preflight.png", dpi=170)
fig.savefig(HERE / "preflight.svg")
print(json.dumps(audit, indent=2))
