import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
old = json.loads((HERE.parent / "2026_10_09_position_error_iter58/results.json").read_text())[
    "rows"
]
new = json.loads((HERE / "results.json").read_text())["rows"]
groups = {}
for row in old + new:
    for check in row["checks"]:
        key = f"{check['kind']}:{check['coordinate']}"
        groups.setdefault(key, {}).setdefault(check["step"], []).append(
            check["absolute_difference"]
        )
summary = {
    key: {
        str(step): dict(maximum=max(values), median=float(np.median(values)), count=len(values))
        for step, values in sorted(steps.items(), reverse=True)
    }
    for key, steps in groups.items()
}
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
for key, steps in groups.items():
    ordered = sorted(steps)
    ax.loglog(ordered, [max(steps[s]) for s in ordered], "o-", label=key)
ax.set(
    xlabel="Central-difference physical step",
    ylabel="Maximum absolute discrepancy across32 regions",
    title="Smooth joint objective: all fixed directions and all step sizes",
)
ax.legend(ncol=2, fontsize=8)
fig.savefig(HERE / "convergence.png", dpi=160)
text = """# Iteration59: smaller steps resolve the large timing-gradient discrepancy

This audit repeats the same32 ordinary endpoints and8 directions from iteration58
with steps10x and100x smaller. It evaluates no position error, performs no fitting,
and makes no adaptive endpoint selection. All three step levels are reported.

![Gradient discrepancies versus finite-difference step](convergence.png)

| Direction | Original step / max discrepancy | 10x smaller / max discrepancy | 100x smaller / max discrepancy |
|---|---:|---:|---:|
"""
for key, steps in summary.items():
    values = [f"{step} / {row['maximum']:.7g}" for step, row in steps.items()]
    text += "| " + key + " | " + " | ".join(values) + " |\n"
text += """
The original common-timing discrepancy was dominated by finite-step effects:
compare vector:7 across all three scales. Very small steps introduce numerical
cancellation, so improvement need not be monotonic at the smallest step. This is
evidence about evaluated derivatives, not proof that an optimizer has converged
or that a fitted position is accurate. The existing stationarity gate is unchanged.

The audit covers geographic, receiver slope, c, common/one relative timing and
one clock direction. It does not establish all-parameter accuracy on real scans;
the synthetic tests supply all-parameter coverage. Orbit interpolation retains
piecewise-linear node boundaries, so smoothing horizon visibility does not make
the entire model globally smooth. No independent validation claim is made.

The integrated prototype can now proceed to a bounded exploratory fit comparison
with the original convergence gate, while retaining failed fits. Hard/smooth runtime
differs: iteration58 measured4.45x evaluation cost. c0/fitted-c budgets must match;
any wall-time allowance difference between hard and smooth models must be disclosed.
Use the same ordinary seeds/bank and priors, choose winners by converged objective,
and measure position errors only afterward. This is a consumed diagnostic, not
permission for per-scan tuning or cohort-result replacement. A uniform policy on
all three datasets and new independent validation remain necessary.

Frozen audit source/protocol commit:a02e192c9. No production, contracts, fixtures,
RF collection, or existing immutable experiment sources changed.
"""
(HERE / "README.md").write_text(text)
