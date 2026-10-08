"""Descriptive diagnostic-probe results; never open DS17 validation outcomes."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
rows = [json.loads(p.read_text()) for p in sorted((HERE / "probes").glob("*.json"))]
assert len(rows) == 7
variants = [
    "matched-control",
    "satellite-bias-50",
    "satellite-bias-150",
    "satellite-bias-150-tight-timing",
]
labels = [r["label"] for r in rows]
summary = {
    "probe_scans": labels,
    "selection": "purposefully selected failures and controls; not a representative mean",
    "arms": {},
}
figure, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
for axis, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
    values = {
        v: [
            next(c for c in row["candidates"] if c["variant"] == v and c["arm"] == arm)
            for row in rows
        ]
        for v in variants
    }
    paired = np.array([all(values[v][i]["converged"] for v in variants) for i in range(len(rows))])
    summary["arms"][arm] = {
        "paired_labels": [
            label for label, accepted in zip(labels, paired, strict=True) if accepted
        ],
        "models": {},
    }
    for index, variant in enumerate(variants):
        results = values[variant]
        errors = np.array([r["error_km"] for r in results])
        rms = np.array([r["posterior_rms_hz"] for r in results])
        summary["arms"][arm]["models"][variant] = {
            "converged": sum(r["converged"] for r in results),
            "attempted": len(results),
            "paired_mean_error_km": float(np.mean(errors[paired])),
            "paired_mean_frequency_rms_hz": float(np.mean(rms[paired])),
            "elapsed_s": float(sum(r["elapsed_s"] for r in results)),
            "by_scan": {
                label: {
                    "error_km": r["error_km"],
                    "rms_hz": r["posterior_rms_hz"],
                    "converged": r["converged"],
                }
                for label, r in zip(labels, results, strict=True)
            },
        }
        plotted = [r["error_km"] if r["converged"] else np.nan for r in results]
        axis.bar(np.arange(len(rows)) + (index - 1.5) * 0.2, plotted, width=0.19, label=variant)
    axis.set(
        xticks=np.arange(len(rows)),
        xticklabels=labels,
        ylabel="Position error (km)",
        title=f"{arm}: stationary fits only",
    )
    axis.axhline(1, color="black", linestyle="--", linewidth=1)
    axis.grid(axis="y", alpha=0.25)
axes[0].legend(ncol=2, fontsize=9)
figure.savefig(HERE / "model-probes.png", dpi=160)
plt.close(figure)

cohort = HERE.parent / "2026_10_08_hard60_bounded_recovery/cohort"
points = np.array(
    [
        [row["arms"]["fitted-c"]["actual"][key] for key in ("east_km", "north_km")]
        for row in [json.loads(p.read_text()) for p in sorted(cohort.glob("*.json"))]
    ]
)
reference = np.array([-87.03579588322492, -80.99086034665267])
delta = points - reference
figure, axis = plt.subplots(figsize=(7, 6), layout="constrained")
axis.scatter(delta[:, 0], delta[:, 1], label="48 independent scan estimates")
axis.plot(0, 0, "k+", markersize=12, label="Evaluation reference")
axis.plot(*delta.mean(0), "rD", label="All-scan mean (retrospective)")
axis.plot(*np.median(delta, axis=0), "gs", label="Coordinate median (retrospective)")
axis.add_patch(plt.Circle((0, 0), 1, fill=False, linestyle="--", color="gray"))
axis.set(
    xlabel="East error (km)",
    ylabel="North error (km)",
    title="DS16 error spread: potential for stationary multi-scan fusion",
    aspect="equal",
)
axis.legend(fontsize=8)
axis.grid(alpha=0.3)
figure.savefig(HERE / "spatial-errors.png", dpi=160)
plt.close(figure)
summary["retrospective_fusion_diagnostic"] = {
    "all_scan_mean_error_km": float(np.linalg.norm(delta.mean(0))),
    "coordinate_median_error_km": float(np.linalg.norm(np.median(delta, axis=0))),
    "limitation": (
        "Uses all scans, including future measurements. "
        "Not a causal filter result or independent validation."
    ),
}
protocol = json.loads((HERE / "protocol.json").read_text())
development = {r["label"] for r in protocol["membership"] if r["group"] == "development"}
available = {p.stem for p in (HERE / "baseline").glob("*.json")}
assert available <= development, "validation lock"
summary["ds17_baseline_readiness"] = {
    "development": 17,
    "available": len(available),
    "pending": sorted(development - available),
    "validation_unopened": 34,
}
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(
    json.dumps(
        {
            arm: {
                v: {
                    k: d[k]
                    for k in ("converged", "paired_mean_error_km", "paired_mean_frequency_rms_hz")
                }
                for v, d in data["models"].items()
            }
            for arm, data in summary["arms"].items()
        },
        indent=2,
    )
)
