"""Join the sealed experiments by exact recording membership, without refitting."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
paths = [
    ROOT.parent / f"2026_09_23_{name}/results.json"
    for name in ("grouped_robust_position", "soft_candidate_position")
]
grouped, soft = [json.loads(p.read_text()) for p in paths]
manifest = json.loads(
    (ROOT.parent / "2026_09_23_position_random_group_split/manifest.json").read_text()
)
test = set(manifest["partitions"]["test"]["session_ids"])
peer = {tuple(w["session_ids"]): w for w in soft["windows"]}
rows = []
for i, window in enumerate(grouped["windows"]):
    other = peer[tuple(window["session_ids"])]
    assert not set(window["session_ids"]) & test
    assert window["seeds"] == other["seeds"]
    for arm in window["arms"] + other["arms"]:
        selected = arm["selected"]
        rows.append(
            {
                "window_index": i,
                "window_id": window["window_id"],
                "scan_count": len(window["session_ids"]),
                "elapsed_span_seconds": other["elapsed_span_seconds"],
                "nominal_capture_seconds": other["nominal_capture_seconds"],
                "method": arm["method"],
                "latitude_deg": selected["latitude_deg"],
                "longitude_deg": selected["longitude_deg"],
                "error_km": selected.get(
                    "reference_error_km", selected.get("evaluation_only_error_km")
                ),
                "common_reserved_capped800_rmse_hz": selected.get(
                    "reserved_capped800_rmse_hz", selected.get("common_reserved_capped800_rmse_hz")
                ),
                "common_reserved_uncapped_rmse_hz": selected.get(
                    "reserved_uncapped_rmse_hz", selected.get("common_reserved_uncapped_rmse_hz")
                ),
            }
        )
output = {
    "scope": (
        "Two random validation groups and nested first scans; retrospective conditional "
        "refinement; no test evidence"
    ),
    "rows": rows,
    "source_sha256": {
        str(p.relative_to(ROOT.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
    },
}
(ROOT / "comparison.json").write_text(json.dumps(output, indent=2) + "\n")
with (ROOT / "comparison.csv").open("w") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
methods = list(dict.fromkeys(r["method"] for r in rows))
labels = [
    "Duration capped",
    "Duration robust",
    "Equal-scan robust",
    "Equal-track hard",
    "Soft mixture",
]
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
for j, (method, label) in enumerate(zip(methods, labels, strict=True)):
    values = [r for r in rows if r["method"] == method]
    axes[0].bar(
        np.arange(4) + (j - 2) * 0.15, [r["error_km"] for r in values], width=0.15, label=label
    )
    full = [r for r in values if r["scan_count"] > 1]
    axes[1].plot([0, 1], [r["common_reserved_capped800_rmse_hz"] for r in full], "o-", label=label)
axes[0].axhline(0.3, color="black", linestyle="--", label="300 m target")
axes[0].set_yscale("log")
axes[0].set_ylabel("Reference error (km)")
axes[0].set_xticks(
    range(4), ["Sep22\n10 scans", "Sep22\nfirst scan", "Sep23\n12 scans", "Sep23\nfirst scan"]
)
axes[1].set_xticks([0, 1], ["Sep22 · 10 scans", "Sep23 · 12 scans"])
axes[1].set_ylabel("Common reserved capped RMS (Hz)")
for ax in axes:
    ax.grid(axis="y", alpha=0.2)
axes[0].legend(fontsize=8)
fig.suptitle("Random-group validation · same recordings and seeds · conditional candidate pools")
fig.tight_layout()
fig.savefig(ROOT / "comparison.png", dpi=180)
