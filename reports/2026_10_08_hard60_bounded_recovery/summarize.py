"""Summarize paired integrated DS16 regression, separating fit from position."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
rows = [json.loads(p.read_text()) for p in sorted((HERE / "cohort").glob("S*.json"))]
assert [r["label"] for r in rows] == [f"S{i:02}" for i in range(1, 49)]
assert len({r["configuration_sha256"] for r in rows}) == 1
summary = {
    "scans": 48,
    "configuration_sha256": rows[0]["configuration_sha256"],
    "failed_coarse": sum(r["failed_points"] for r in rows),
    "recovered_coarse": sum(r["recovered_points"] for r in rows),
    "added_finals": sum(r["added_finals"] for r in rows),
    "qualification": "baseline stage replay plus fresh integrated recovery; not a cold search",
    "position_tolerance_km": 0.001,
    "objective_tolerance": 0.001,
    "arms": {},
}
figure, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")
for axis, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
    values = {
        kind: np.array([r["arms"][arm][kind]["horizontal_error_m"] / 1000 for r in rows])
        for kind in ("baseline", "actual")
    }
    statistics = {}
    for kind, data in values.items():
        statistics[kind] = {
            "mean_km": float(data.mean()),
            "median_km": float(np.median(data)),
            "p95_km": float(np.quantile(data, 0.95)),
            "max_km": float(data.max()),
        }
        axis.plot(np.sort(data), np.arange(1, 49) / 48, label=kind)
    difference = values["actual"] - values["baseline"]
    statistics.update(
        improved=int(np.sum(difference < -0.001)),
        regressed=int(np.sum(difference > 0.001)),
        unchanged=int(np.sum(abs(difference) <= 0.001)),
    )
    statistics["frequency_and_score"] = [
        {
            "label": r["label"],
            **{
                kind: {
                    key: r["arms"][arm][kind][key]
                    for key in ("selection_score", "posterior_rms_hz")
                }
                for kind in ("baseline", "actual")
            },
        }
        for r in rows
        if r["added_finals"]
    ]
    summary["arms"][arm] = statistics
    axis.set(
        xscale="log",
        xlabel="Reference position error (km)",
        ylabel="Fraction of scans",
        title=f"DS16: {arm}, 48 paired scans",
    )
    axis.grid(alpha=0.3)
    axis.legend()
figure.savefig(HERE / "comparison.png", dpi=160)
plt.close(figure)
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
