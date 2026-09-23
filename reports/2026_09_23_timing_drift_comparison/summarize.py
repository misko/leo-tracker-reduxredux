"""Render the completed timing experiment; no new inference or model selection."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
source = HERE.parent / "2026_09_23_fractional_timing_position/results.json"
data = json.loads(source.read_text())
rows = []
for i, window in enumerate(data["windows"]):
    for arm in window["arms"]:
        selected = arm["selected"]
        rows.append(
            {
                "window_index": i,
                "window_id": window["window_id"],
                "scan_count": len(window["session_ids"]),
                "method": arm["method"],
                "latitude_deg": selected["latitude_deg"],
                "longitude_deg": selected["longitude_deg"],
                "error_km": selected["reference_error_km"],
                "reserved_capped800_rmse_hz": selected["reserved_capped800_rmse_hz"],
                "reserved_uncapped_rmse_hz": selected["reserved_uncapped_rmse_hz"],
                "boundary_fraction": selected["support_boundary_tau_fraction"],
            }
        )
(HERE / "comparison.json").write_text(
    json.dumps(
        {
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "scope": (
                "Random retrospective validation groups; nested singleton views; "
                "conditional candidates"
            ),
            "rows": rows,
        },
        indent=2,
    )
    + "\n"
)
with (HERE / "comparison.csv").open("w") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
for i, method in enumerate(dict.fromkeys(r["method"] for r in rows)):
    selected = [r for r in rows if r["method"] == method]
    axes[0].bar(
        np.arange(4) + (i - 1) * 0.23, [r["error_km"] for r in selected], width=0.23, label=method
    )
    full = [r for r in selected if r["scan_count"] > 1]
    axes[1].plot([0, 1], [r["reserved_capped800_rmse_hz"] for r in full], "o-", label=method)
axes[0].set_yscale("log")
axes[0].axhline(0.3, linestyle="--", color="black", label="300 m target")
axes[0].set_ylabel("Reference error (km)")
axes[0].set_xticks(range(4), ["10 scans", "First scan", "12 scans", "First scan"])
axes[1].set_xticks([0, 1], ["Sep22 · 10 scans", "Sep23 · 12 scans"])
axes[1].set_ylabel("Reserved capped RMS (Hz)")
for ax in axes:
    ax.grid(axis="y", alpha=0.2)
axes[0].legend(fontsize=8)
fig.suptitle("Fractional timing improves frequency fit; geographic improvement does not generalize")
fig.tight_layout()
fig.savefig(HERE / "comparison.png", dpi=180)
