"""Score a frozen development rule; retain all cases and failed convergence."""

import json
from pathlib import Path

import matplotlib
import numpy as np
from influence_policy import choose

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
INITIAL = ["S10", "S16", "S24", "DS17-004", "DS17-045", "DS17-048", "DS17-051"]


def main():
    expansion = json.loads((HERE / "expansion-protocol.json").read_text())["labels"]
    labels = INITIAL + expansion
    documents = {
        label: json.loads((HERE / "influence" / f"{label}.json").read_text()) for label in labels
    }
    results = []
    for label, doc in documents.items():
        control = {r["arm"]: r for r in doc["candidates"] if r["removed_satellite"] is None}
        policy = choose(doc)
        fitted = [
            r
            for r in doc["candidates"]
            if r["arm"] == "fitted-c" and r["removed_satellite"] is not None and r["converged"]
        ]
        results.append(
            dict(
                label=label,
                session_id=doc["session_id"],
                removed_satellite=policy["fitted-c"]["removed_satellite"],
                maximum_displacement_km=max(r["displacement_km"] for r in fitted),
                best_deletion_error_km=min(r["error_km"] for r in fitted),
                worst_deletion_error_km=max(r["error_km"] for r in fitted),
                arms={
                    arm: dict(
                        before_km=control[arm]["error_km"],
                        after_km=policy[arm]["error_km"],
                        before_converged=control[arm]["converged"],
                        after_converged=policy[arm]["converged"],
                        before_full_rms_hz=control[arm]["full_posterior_rms_hz"],
                        after_full_rms_hz=policy[arm]["full_posterior_rms_hz"],
                    )
                    for arm in control
                },
            )
        )
    aggregates = {}
    for name, members in {
        "initial": INITIAL,
        "expansion": expansion,
        "ds17_development": [label for label in labels if label.startswith("DS17-")],
    }.items():
        aggregates[name] = {}
        for arm in ("fitted-c", "zero-c"):
            paired = [
                r
                for r in results
                if r["label"] in members
                and r["arms"][arm]["before_converged"]
                and r["arms"][arm]["after_converged"]
            ]
            before = np.array([r["arms"][arm]["before_km"] for r in paired])
            after = np.array([r["arms"][arm]["after_km"] for r in paired])
            aggregates[name][arm] = dict(
                paired_labels=[r["label"] for r in paired],
                mean_before_km=float(before.mean()),
                mean_after_km=float(after.mean()),
                worst_before_km=float(before.max()),
                worst_after_km=float(after.max()),
                improved=int((after < before - 0.001).sum()),
                worsened=int((after > before + 0.001).sum()),
            )
    summary = dict(
        cases=results,
        aggregates=aggregates,
        warning="Development-only influence rule; best deletion is a hindsight diagnostic",
    )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(2, 1, figsize=(13, 9), layout="constrained")
    for ax, members, title in zip(
        axes,
        [INITIAL, expansion],
        [
            "Initial diagnostics (rule development)",
            "Additional DS17 development scans (rule frozen beforehand)",
        ],
        strict=True,
    ):
        selected = [r for r in results if r["label"] in members]
        x = np.arange(len(selected))
        ax.bar(
            x - 0.18, [r["arms"]["fitted-c"]["before_km"] for r in selected], 0.36, label="Control"
        )
        ax.bar(
            x + 0.18,
            [r["arms"]["fitted-c"]["after_km"] for r in selected],
            0.36,
            label="Delete most influential group only if movement >2 km",
        )
        ax.set_xticks(x, [r["label"] for r in selected], rotation=35, ha="right")
        ax.set(title=title, ylabel="Fitted-c position error (km)")
        ax.axhline(1, color="black", linestyle="--", linewidth=1)
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.2)
    fig.savefig(HERE / "comparison.png", dpi=150)
    plt.close(fig)
    print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()
