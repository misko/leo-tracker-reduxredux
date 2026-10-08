"""Separate smooth-gradient behavior from hard horizon discontinuities."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    results = json.loads((HERE / "results.json").read_text())
    summary = []
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    for row in results["rows"]:
        label = f"{row['hypothesis']} / {row['source_arm']} → {row['arm']}"
        selected = [t for t in row["trials"] if t["step"] == 1e-4]
        points = []
        for t in row["trials"]:
            for s in t["sides"]:
                if s["feasible"]:
                    points.append(s["delta"])
        item = dict(
            hypothesis=row["hypothesis"],
            source_arm=row["source_arm"],
            arm=row["arm"],
            converged=row["converged"],
            stationarity=row["reported_stationarity"],
            largest_fd_disagreement_at_1e4=max(
                abs(t["central_difference"] - t["analytic"]) for t in selected
            ),
            largest_visibility_flip_at_1e4=max(
                s["changed_visible_entries"] for t in selected for s in t["sides"]
            ),
            best_feasible_objective_delta=min(points),
        )
        summary.append(item)
        steps = sorted({t["step"] for t in row["trials"]})
        for ax, names in zip(
            axes, (("east", "north", "largest_timing"), ("c", "largest_clock")), strict=True
        ):
            errors = [
                max(
                    abs(t["central_difference"] - t["analytic"])
                    for t in row["trials"]
                    if t["step"] == step and t["direction"] in names
                )
                for step in steps
            ]
            ax.plot(
                steps,
                np.maximum(errors, 1e-12),
                marker="o",
                linestyle="--" if row["converged"] else "-",
                alpha=0.8,
                label=label,
            )
    for ax, title in zip(
        axes, ("Geometry/timing directions", "Frequency/clock directions"), strict=True
    ):
        ax.set(
            xscale="log",
            yscale="log",
            xlabel="Step in scaled coordinates",
            ylabel="|finite difference − analytic derivative|",
            title=title,
        )
        ax.grid(alpha=0.2)
    axes[0].legend(fontsize=6)
    fig.savefig(HERE / "gradient-discontinuity.png", dpi=160)
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    text = """# Iteration 49: hard horizon transitions explain the stationarity disagreement

**All four nonstationary fitted-c outputs from iteration46 lie at hard
horizon-visibility transitions.** At a 0.0001 scaled step, small geometric
perturbations change visibility for one or two observation/satellite entries.
All four converged zero-c controls have zero visibility flips at that same scale.
The analytic gradient is a within-visibility-region derivative; it does not
represent a finite score jump when a satellite crosses the horizon.

![Finite differences versus the analytic gradient](gradient-discontinuity.png)

## Controlled audit

Commit `609124810` froze this audit before execution. It evaluates all eight
saved outputs on the same 145-satellite bank and shared calibration from
iteration46. No optimization or position selection occurs. Directions cover
east, north, c where free, the largest timing-gradient coordinate, the largest
clock-gradient coordinate and the scaled negative-gradient direction. Both
signs are tested at steps 0.01, 0.001, 0.0001, 0.00001 and 0.000001. Constraints
are checked separately; infeasible trials are not counted as valid descent.

A 0.0001 east/north step is 0.1 m. Visibility is geometric above/below horizon,
not receiver-pair agreement. The likelihood includes a visibility-dependent
signal probability and no-detection normalization, so even a weakly associated
satellite can change the score when its visibility flag flips.

| Hypothesis | Seed arm | Arm | Stationarity | Max FD mismatch at 1e-4 | Visibility flips |
|---|---|---|---:|---:|---:|
"""
    for r in summary:
        text += (
            f"| {r['hypothesis']} | {r['source_arm']} | {r['arm']} | "
            f"{r['stationarity']:.6g} | {r['largest_fd_disagreement_at_1e4']:.6g} | "
            f"{r['largest_visibility_flip_at_1e4']} |\n"
        )
    text += """
For example, the ordinary fitted-seed/fitted-c result has east derivative 0.450
analytically but 63.740 by central difference at the 0.1 m step. The positive
step changes one visibility entry and raises the objective by 0.012765. Its c
and clock directions have no visibility changes and agree with finite differences
at this scale. The other fitted-c failures show the same geometric pattern.

The zero-c controls agree much more closely; their small derivative residuals
depend on step size because the likelihood has high timing curvature and finite
precision. These are numerical diagnostics, not a new convergence threshold.

## Consequence for the next experiment

This is evidence of a nonsmooth objective at the fitted-c endpoints, not evidence
that a larger time budget alone will fix the problem. The smooth stationarity
criterion cannot certify a discontinuous boundary as an ordinary smooth optimum.
The recorded failures remain failures under the frozen protocol; we do not
retroactively declare them converged or promote them into benchmark results.

The next useful model test is a physically motivated, differentiable horizon
detection taper, with derivatives of both the signal mixture and no-detection
normalization included. It should retain hard zero visibility below the horizon
and smoothly increase detection probability above it. Validate its gradients
through the transition before fitting, then use matched c arms, banks, starts,
priors and budgets. A smooth taper is a model change, not a harmless solver flag.

This audit does not resolve the independent zero-c ranking result: the converged
distant solution still scores better than the recovered one in iteration46.
It also does not alter the full DS16/DS17/DS18 comparison or substitute oracle
positions. No production, contract, golden-fixture, QNAP or RF-collection changes
were made. Runtime checks reproduced all eight saved objectives; Ruff passes.
[results.json](results.json) records every finite-difference trial, visibility
change, feasibility check and score delta.
"""
    (HERE / "README.md").write_text(text)


if __name__ == "__main__":
    main()
