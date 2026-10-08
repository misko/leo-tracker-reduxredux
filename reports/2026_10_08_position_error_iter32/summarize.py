"""Summarize initialization probes and explicitly fixed-vector prior sensitivity."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    cases = {}
    stages = ("joint-100", "remove-5", "post-200", "drift-50", "control-refit", "slope-0.25")
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
    for i, (label, binding) in enumerate(plan["cases"].items()):
        cases[label] = {}
        original = json.loads((HERE.parent / binding["control"]).read_text())
        current = json.loads((HERE / "results" / f"{label}.json").read_text())
        for name, raw in (("original-start", original), ("zero-timing-start", current)):
            extended = raw["extended"] if "extended" in raw else raw["result"]
            rows = {**raw["upstream"]["stages"], **extended["stages"]}
            arms = {}
            for j, arm in enumerate(("fitted-c", "zero-c")):
                arms[arm] = {
                    s: dict(
                        error_km=rows[s][arm]["error_km"],
                        objective=rows[s][arm]["objective"],
                        rms_hz=rows[s][arm]["posterior_rms_hz"],
                        converged=rows[s][arm]["converged"],
                    )
                    for s in stages
                }
                axes[i, j].plot(
                    stages, [arms[arm][s]["error_km"] for s in stages], marker="o", label=name
                )
                axes[i, j].set(title=label + " " + arm, ylabel="Position error (km)")
                axes[i, j].axhline(1, color="gray", linewidth=1)
                axes[i, j].tick_params(axis="x", rotation=35, labelsize=8)
                axes[i, j].grid(alpha=0.2)
                axes[i, j].legend(fontsize=8)
            cases[label][name] = dict(arms=arms, removed=raw["upstream"].get("removed", []))
    fig.savefig(HERE / "start-comparison.png", dpi=160)
    decomposition = json.loads((HERE / "decomposition.json").read_text())["cases"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
    for ax, (label, arms) in zip(axes, decomposition.items(), strict=True):
        for arm, variants in arms.items():
            original = variants["original-start"]["fixed_vector_timing_sensitivity"]
            zero = variants["zero-timing-start"]["fixed_vector_timing_sensitivity"]
            sigma = np.array(sorted(float(s) for s in original))
            lookup = {float(s): original[s] - zero[s] for s in original}
            ax.plot(sigma, [lookup[s] for s in sigma], marker="o", label=arm)
        ax.axhline(0, color="gray", linewidth=1)
        ax.set(
            title=label + " — no reoptimization",
            xlabel="Relative timing sigma (s)",
            ylabel="Original-start minus zero-start objective",
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.savefig(HERE / "fixed-vector-sensitivity.png", dpi=160)
    (HERE / "summary.json").write_text(json.dumps(dict(cases=cases), indent=2) + "\n")
    for label, variants in cases.items():
        print(
            label,
            {
                v: {a: r["slope-0.25"] for a, r in values["arms"].items()}
                for v, values in variants.items()
            },
        )


if __name__ == "__main__":
    main()
