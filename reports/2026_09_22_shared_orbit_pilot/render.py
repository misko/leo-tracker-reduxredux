"""Rebuild the completed pilot comparison from saved numerical outputs."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent


def read(name):
    return json.loads((ROOT / "artifacts" / name).read_text())


controls = read("3bee-fixed-sac-controls-v1.json")["arms"]
baseline = controls["original_orbit"]["heldout_log_predictive"]
values = [baseline, controls["causal_mean_zero_rate"]["heldout_log_predictive"],
          read("3bee-fixed-sac-exact-v1.json")["heldout_log_predictive"],
          read("3bee-joint-sac-exact-v1.json")["heldout_log_predictive"]]
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
axes[0].bar(["Original\norbit", "Causal mean\nonly", "Shared rates\nfixed position",
             "Shared rates\njoint position"], [v - baseline for v in values])
axes[0].axhline(0, color="black", linewidth=.7)
axes[0].set_ylabel("Held-out log predictive gain over original orbit")
checks = [read("qualification-receipt.json")["maximum_doppler_error_hz"],
          read("3bee-fixed-sac-exact-v1.json")["maximum_doppler_error_hz"],
          read("3bee-joint-sac-exact-v1.json")["maximum_doppler_error_hz"]]
axes[1].bar(["Off-node\nvalidation", "Fixed-position\nfinalist", "Joint-position\nfinalist"], checks)
axes[1].set_yscale("log")
axes[1].axhline(.2, color="red", linestyle="--", label="0.2 Hz tolerance")
axes[1].set_ylabel("Maximum Doppler error vs exact propagation (Hz)")
axes[1].legend()
fig.suptitle("19-track exploratory pilot · predictive improvement ≠ sub-km accuracy\n"
             "Joint position evaluation error: 5.89 km · no geometric-phase claim")
fig.savefig(ROOT / "comparison.png", dpi=160)
