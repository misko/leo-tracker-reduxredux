import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "results.json").read_text())["rows"]
times = {
    name: np.array([r["evaluation_seconds"][name] for r in rows]) for name in ("numpy", "native")
}
summary = dict(
    regions=len(rows),
    median_seconds={k: float(np.median(v)) for k, v in times.items()},
    max_differences={
        k: max(r["differences"][k] for r in rows)
        for k in ("objective", "gradient", "clock_gradient")
    },
)
summary["speedup"] = summary["median_seconds"]["numpy"] / summary["median_seconds"]["native"]
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
fig, ax = plt.subplots(figsize=(9, 4), layout="constrained")
for name, values in times.items():
    ax.plot([r["region"] for r in rows], values * 1000, "o-", label=name)
ax.set(
    xlabel="Ordinary region index",
    ylabel="Full smooth-objective evaluation time (ms)",
    title="Equivalent native elevation removes NumPy geometry overhead",
)
ax.legend()
fig.savefig(HERE / "runtime.png", dpi=160)
(
    HERE / "README.md"
).write_text(f"""# Iteration61: native elevation halves smooth-objective evaluation time

The private native elevation helper passed all32 ordinary-region equivalence
checks for the complete smooth objective, parameter/clock gradients and candidate
responsibilities. Median evaluation time changed from
{summary["median_seconds"]["numpy"] * 1000:.2f}ms to
{summary["median_seconds"]["native"] * 1000:.2f}ms, a
**{summary["speedup"]:.2f}x speedup**. This is a computational improvement, not a
localization improvement or an optimization-trajectory equivalence claim.

![Evaluation costs on the same32 ordinary endpoints](runtime.png)

The measured4.45x slowdown in iteration58 motivated this narrow helper. It ports
the verified NumPy elevation interpolation and derivatives into one double-
precision loop, without fast-math. The receiver chart derivatives, likelihood,
clock terms and priors are unchanged. No RF or reference coordinates are used
to choose starts or tune the numerical implementation.

Maximum absolute differences across32 endpoints:

| Quantity | Maximum difference |
|---|---:|
| Objective | {summary["max_differences"]["objective"]:.9g} |
| Parameter gradient | {summary["max_differences"]["gradient"]:.9g} |
| Clock gradient | {summary["max_differences"]["clock_gradient"]:.9g} |

Frozen tolerances: objective/gradients atol1e-7,rtol1e-9; responsibilities
atol1e-10,rtol1e-9. All passed. Each reported timing is a median of3 full
evaluations under the running workload, not a dedicated performance benchmark.
The two synthetic tests also pass: geometry equivalence including a near-zenith
case, and explicit rejection of invalid shapes/nonfinite/out-of-support inputs.

Build manually with `g++ -std=c++17 -O3 -fPIC -shared elevation.cpp -o
local/elevation.so` from this report directory. The local binary is excluded
from Git; protocol.json binds its actual SHA256 as well as source hashes.
No runtime compilation or silent fallback is used. Missing binary is an explicit
failure. Rebuilding with another compiler may require a new qualification receipt.

This helper is research-only. Existing production and every running frozen
experiment remain unchanged. In particular, iteration60 continues using NumPy
with its recorded90second allowance. A future use of the native helper must
freeze its implementation and budgets separately; current results cannot be
retroactively relabeled as faster-native results. Fit-trajectory qualification
and independent validation remain outstanding. No public contract or fixture changed.
""")
