"""All-member operational comparison and stationary matched controls."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    cases = []
    for label in protocol["labels"]:
        doc = json.loads((HERE / "results" / f"{label}.json").read_text())
        arms = {}
        for arm in ("fitted-c", "zero-c"):
            baseline = next(a["selected"] for a in doc["baseline_arms"] if a["name"] == arm)
            joint = next(
                r for r in doc["candidates"] if r["variant"] == "joint-wide" and r["arm"] == arm
            )
            control = next(
                r
                for r in doc["candidates"]
                if r["variant"] == "matched-control" and r["arm"] == arm
            )
            arms[arm] = dict(
                baseline_km=baseline["horizontal_error_m"] / 1000,
                joint_km=joint["error_km"],
                control_km=control["error_km"],
                operational_km=joint["error_km"]
                if joint["converged"]
                else baseline["horizontal_error_m"] / 1000,
                joint_converged=joint["converged"],
                control_converged=control["converged"],
                baseline_rms=baseline["posterior_rms_hz"],
                joint_rms=joint["posterior_rms_hz"],
                control_rms=control["posterior_rms_hz"],
            )
        cases.append(dict(label=label, arms=arms))
    aggregate = {}
    for arm in ("fitted-c", "zero-c"):
        rows = [c["arms"][arm] for c in cases if c["label"].startswith("NEW-")]
        before = np.array([r["baseline_km"] for r in rows])
        after = np.array([r["operational_km"] for r in rows])
        stationary = [r for r in rows if r["joint_converged"] and r["control_converged"]]
        aggregate[arm] = dict(
            count=len(rows),
            baseline_mean=float(before.mean()),
            operational_mean=float(after.mean()),
            baseline_median=float(np.median(before)),
            operational_median=float(np.median(after)),
            baseline_p95=float(np.percentile(before, 95)),
            operational_p95=float(np.percentile(after, 95)),
            baseline_worst=float(before.max()),
            operational_worst=float(after.max()),
            improved=int((after < before - 0.001).sum()),
            worsened=int((after > before + 0.001).sum()),
            fallback=sum(not r["joint_converged"] for r in rows),
            stationary_pairs=len(stationary),
            matched_control_mean=float(np.mean([r["control_km"] for r in stationary])),
            matched_joint_mean=float(np.mean([r["joint_km"] for r in stationary])),
            matched_control_rms=float(np.mean([r["control_rms"] for r in stationary])),
            matched_joint_rms=float(np.mean([r["joint_rms"] for r in stationary])),
        )
    (HERE / "summary.json").write_text(
        json.dumps(dict(cases=cases, aggregate=aggregate), indent=2) + "\n"
    )
    newer = [c for c in cases if c["label"].startswith("NEW-")]
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), layout="constrained")
    for ax, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
        for i, variant in enumerate(("baseline_km", "control_km", "operational_km")):
            ax.bar(
                np.arange(8) + (i - 1) * 0.25,
                [c["arms"][arm][variant] for c in newer],
                0.25,
                label={
                    "baseline_km": "Baseline",
                    "control_km": "Matched local control",
                    "operational_km": "Joint-wide with fallback",
                }[variant],
            )
        ax.set_xticks(np.arange(8), [c["label"] for c in newer])
        ax.set(title=arm, ylabel="Position error (km)")
        ax.axhline(1, color="black", linestyle="--", linewidth=1)
        ax.grid(axis="y", alpha=0.2)
        ax.legend()
    fig.savefig(HERE / "newer-comparison.png", dpi=160)
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
