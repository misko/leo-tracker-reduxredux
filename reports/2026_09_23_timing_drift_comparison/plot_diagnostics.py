"""Render saved training diagnostics without opening new recording evidence."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
drift = json.loads(
    (HERE.parent / "2026_09_23_receiver_drift_audit/receiver_drift.json").read_text()
)
timing = json.loads((HERE / "training_timing.json").read_text())
assert [r["session_id"] for r in drift["scans"]] == [r["session_id"] for r in timing["rows"]]
x = np.arange(1, len(timing["rows"]) + 1)
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
for key, label in [
    ("base_reserved_rms_hz", "Unchanged"),
    ("shared_slope_reserved_rms_hz", "Training-fitted scan slope"),
]:
    axes[0].plot(x, [r[key] for r in drift["scans"]], "o-", label=label)
axes[0].set_ylabel("Inner reserved RMS (Hz)")
axes[0].legend()
half = np.array([r["timing"]["first_sample_bracket_width_ns"] for r in timing["rows"]]) / 2e9
axes[1].plot(x, half, "o-", label="Half host capture-start bracket")
axes[1].axhline(5, linestyle="--", color="orange", label="Current per-track tau limit")
axes[1].set_yscale("log")
axes[1].set_ylabel("Timing half-width / search limit (seconds)")
axes[1].legend()
for ax in axes:
    ax.set_xlabel("Training scan index")
    ax.grid(alpha=0.2)
fig.suptitle("Training-only diagnostics · host bracket does not certify absolute UTC")
fig.tight_layout()
fig.savefig(HERE / "training_diagnostics.png", dpi=180)
