import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "results.json").read_text())["rows"]
summary = []
fig, axes = plt.subplots(3, 2, figsize=(11, 9), layout="constrained")
for row, ax in zip(rows, axes.flat, strict=True):
    path = row["path"]
    values = [p["numpy_objective"] for p in path]
    summary.append(
        dict(
            index=row["index"],
            arm=row["arm"],
            all_feasible=all(p["feasible"] for p in path),
            endpoint_objective_delta=values[-1] - values[0],
            sampled_peak_above_higher_endpoint=max(values) - max(values[0], values[-1]),
            max_objective_disagreement=max(p["objective_difference"] for p in path),
            max_parameter_gradient_disagreement=max(
                p["parameter_gradient_difference"] for p in path
            ),
            max_clock_gradient_disagreement=max(p["clock_gradient_difference"] for p in path),
        )
    )
    for name, style in [("numpy", "-"), ("native", "--")]:
        ax.plot(
            [p["alpha"] for p in path],
            [p[name + "_objective"] - values[0] for p in path],
            style,
            label=name,
        )
    ax.set(
        title=f"{row['index']} {row['arm']}",
        xlabel="Interpolation: NumPy endpoint to native endpoint",
        ylabel="Objective relative to NumPy endpoint",
    )
    ax.legend(fontsize=7)
fig.savefig(HERE / "paths.png", dpi=160)
(HERE / "summary.json").write_text(json.dumps(dict(rows=summary), indent=2) + "\n")
text = """# Iteration63: divergent fits follow different paths on the same evaluated objective

Both implementations returned **identical objective values at all126 sampled
points** across the six fit pairs. Parameter gradients differed only at floating-
point roundoff scale. All connecting-path samples satisfied the existing position,
timing, affine and clock bounds, and saved endpoint scores were reproduced.

![Objectives along the six connecting segments](paths.png)

| Endpoint | Arm | Native minus NumPy score | Peak above endpoints | Max gradient difference |
|---:|---|---:|---:|---:|
"""
for r in summary:
    text += (
        f"| {r['index']} | {r['arm']} | {r['endpoint_objective_delta']:.9g} | "
        f"{r['sampled_peak_above_higher_endpoint']:.9g} | "
        f"{r['max_parameter_gradient_disagreement']:.3g} |\n"
    )
text += """
## Interpretation

The three trajectory-qualification failures have sampled straight-line barriers
above both endpoints: about0.286,1.497 and13.173 objective units. Their native
endpoint scores are respectively0.018better,2.141worse and8.712better. The other
three pairs coincide within the frozen qualification tolerances; their plotted
score differences are at numerical precision. Axis scales differ deliberately.

This supports optimizer path sensitivity rather than a mathematical-model
mismatch at the sampled locations. Tiny evaluation-order differences can affect
iterative line-search decisions in a nonconvex problem. The audit does not trace
every optimization step, establish a unique causal iteration, prove distinct
topological basins, or exclude a lower curved path between endpoints. It does
not establish global optimality or better localization. No reference coordinates
or position errors enter this analysis, and score differences are not accuracy.

The failed drop-in qualification remains failed. Do not replace frozen NumPy
results with native endpoints or choose between implementations by receiver error.
Any future native experiment requires its own fixed implementation, ordinary
starts, score-based selection and matched c arms. The existing multistart pilots
continue unchanged and are the relevant tests of finding/selecting useful regions.

Protocol/source freeze7583f0029. All6fit pairs were retained, each evaluated at
21equally spaced parameter/clock interpolation points. Position/timing feasibility
uses the original seed-centered constraints; clock coefficients retain the2000Hz
bound. No fitting, production, public-contract, fixture or RF changes occurred.
"""
(HERE / "README.md").write_text(text)
