"""Compare sealed spatial experiments on exactly matching validation windows."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
paths = [
    HERE.parent / "2026_09_23_training_position_search/results.json",
    HERE.parent / "2026_09_23_regularized_position_search/results.json",
]
baseline, regularized = [json.loads(p.read_text()) for p in paths]
assert baseline["dataset_digest"] == regularized["dataset_digest"]
other = {w["window_id"]: w for w in regularized["windows"]}
manifest = json.loads(
    (HERE.parent / "2026_09_23_position_train_val_test/dataset/manifest.json").read_text()
)
windows = {
    w["window_id"]: w
    for tier in manifest["partitions"]["development_validation"]["duration_tiers"].values()
    for w in tier["windows"]
}
rows = []
for window in baseline["windows"]:
    peer = other[window["window_id"]]
    authority = windows[window["window_id"]]
    assert authority["session_ids"] == window["session_ids"]
    assert window["session_ids"] == peer["session_ids"]
    assert window["authority_digest"] == peer["authority_digest"]
    for arm in window["arms"]:
        assert [f["seed"] for f in arm["fits"]] == peer["seeds"]
    arms = [(a["loss"], a["selected"], a["fits"]) for a in window["arms"]]
    arms.append(("regularized_timing_1000", peer["selected"], peer["fits"]))
    for method, selected, fits in arms:
        assert selected["training_rmse_hz"] == min(f["training_rmse_hz"] for f in fits)
        rows.append(
            {
                "window_id": window["window_id"],
            "scan_count": window["scan_count"],
            "elapsed_span_seconds": authority["elapsed_span_seconds"],
            "summed_nominal_capture_seconds": authority["summed_nominal_capture_seconds"],
                "method": method,
                "latitude_deg": selected["latitude_deg"],
                "longitude_deg": selected["longitude_deg"],
                "error_km": selected.get(
                    "evaluation_only_error_km", selected.get("reference_error_km")
                ),
                "reserved_capped800_rmse_hz": selected.get(
                    "common_reserved_capped800_rmse_hz", selected.get("reserved_capped800_rmse_hz")
                ),
                "reserved_uncapped_rmse_hz": selected.get(
                    "common_reserved_uncapped_rmse_hz", selected.get("reserved_uncapped_rmse_hz")
                ),
            }
        )
payload = {
    "schema": "position-spatial-comparison/v1",
    "scope": (
        "One predetermined nested retrospective window per tier; conditional candidates "
        "and seeds; not independent test accuracy"
    ),
    "source_sha256": {
        str(p.relative_to(HERE.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
    },
    "rows": rows,
}
(HERE / "spatial_comparison.json").write_text(json.dumps(payload, indent=2) + "\n")
with (HERE / "spatial_comparison.csv").open("w") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
for method, label in [
    ("capped800", "Baseline"),
    ("pseudo_huber_150hz", "Robust 150 Hz"),
    ("regularized_timing_1000", "Regularized timing"),
]:
    subset = [r for r in rows if r["method"] == method]
    for ax, key in zip(axes, ["error_km", "reserved_capped800_rmse_hz"], strict=True):
        ax.plot([r["scan_count"] for r in subset], [r[key] for r in subset], "o-", label=label)
axes[0].axhline(0.3, color="black", linestyle="--", label="300 m target")
axes[0].set_yscale("log")
axes[0].set_ylabel("Reference position error (km)")
axes[1].set_ylabel("Common reserved capped RMS (Hz)")
for ax in axes:
    ax.set_xscale("log")
    ax.set_xticks([1, 6, 18, 48], ["1", "6", "18", "48"])
    ax.set_xlabel("Scans in window")
    ax.grid(alpha=0.2)
    ax.legend()
fig.suptitle("Same recordings and seeds · one nested retrospective window per tier")
fig.tight_layout()
fig.savefig(HERE / "spatial_comparison.png", dpi=170)
