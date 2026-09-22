"""Render the completed single-scan comparison from immutable report artifacts."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
rows = json.loads((root / "artifacts/three-region-single-evaluation-v1.json").read_text())["rows"]
controls = json.loads((root / "artifacts/reno-single-controls-v1.json").read_text())["arms"]
fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
axes[0].bar([r["region"].title() for r in rows], [r["horizontal_error_km"] for r in rows])
axes[0].axhline(1, color="red", linestyle="--", label="1 km target")
axes[0].set(ylabel="Evaluation horizontal error (km)", title="Same scan, three acquired basins")
axes[0].legend()
baseline = controls["original_orbit"]["heldout_log_predictive"]
axes[1].bar(["Original orbit", "Causal mean only", "Joint fit"], [0, controls["causal_mean_zero_rate"]["heldout_log_predictive"] - baseline, rows[1]["heldout_log_predictive"] - baseline])
axes[1].axhline(0, color="black", linewidth=0.7)
axes[1].set(ylabel="Held-out log-score change (higher is better)", title="Matched Reno control comparison")
fig.suptitle("300 s scan · 39 tracks · local shared-orbit refinement")
fig.savefig(root / "comparison.png", dpi=160)
