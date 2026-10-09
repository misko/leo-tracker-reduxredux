import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "results.json").read_text())["rows"]
hard = np.array([r["evaluation_seconds"]["hard"] for r in rows])
smooth = np.array([r["evaluation_seconds"]["smooth"] for r in rows])
absolute = [max(c["absolute_difference"] for c in r["checks"]) for r in rows]
normalized = [
    max(c["absolute_difference"] / max(1, abs(c["analytic"])) for c in r["checks"]) for r in rows
]
summary = dict(
    regions=len(rows),
    checks=sum(len(r["checks"]) for r in rows),
    max_absolute_difference=max(absolute),
    max_normalized_difference=max(normalized),
    median_hard_seconds=float(np.median(hard)),
    median_smooth_seconds=float(np.median(smooth)),
    ratio_of_medians=float(np.median(smooth) / np.median(hard)),
)
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
regions = [r["region"] for r in rows]
axes[0].semilogy(regions, absolute, "o-", label="Absolute")
axes[0].semilogy(regions, normalized, "o-", label="Divided by max(1, |gradient|)")
axes[0].set(ylabel="Maximum derivative discrepancy", xlabel="Ordinary region index")
axes[1].plot(regions, hard * 1000, "o-", label="Hard horizon")
axes[1].plot(regions, smooth * 1000, "o-", label="Smooth horizon")
axes[1].set(ylabel="Median full evaluation time (ms)", xlabel="Ordinary region index")
for ax in axes:
    ax.legend(fontsize=8)
fig.savefig(HERE / "audit.png", dpi=160)
(
    HERE / "README.md"
).write_text(f"""# Iteration58: smooth joint objective integrated; runtime and gradient limits

The research objective now integrates smooth horizon likelihood with joint
position, receiver clocks, fitted c and satellite timing. All eight synthetic
tests across iterations56–58 pass, including every joint parameter gradient,
unchanged priors, reporting shape and horizon-boundary geometry.

![Ordinary-region numerical audit](audit.png)

A separately frozen, non-optimizing audit checked the first feasible ordinary
endpoint in each of32 successful regions on the common145 bank. No recovered
joint seed or receiver reference error was used. Eight derivative coordinates
per region cover east/north, both receiver slopes, c, common/one relative timing,
and one clock coefficient: **{summary["checks"]} real-data derivative checks**.
This is directional coverage, not all-parameter real-data verification.

Maximum absolute discrepancy is{summary["max_absolute_difference"]:.6g}; maximum
discrepancy divided by max(1,abs(analytic_gradient)) is
{summary["max_normalized_difference"]:.6g}. Central steps are0.001 for position,
slopes,c,clock and0.0001 for timing. Several absolute discrepancies exceed0.001;
these finite-step diagnostics must not be presented as proof of stationarity
accuracy. A step-size convergence study is required before optimizer qualification.
No pass threshold was retroactively selected from these results.

Median evaluation cost is{1000 * summary["median_hard_seconds"]:.2f}ms for hard
horizon versus{1000 * summary["median_smooth_seconds"]:.2f}ms for smooth, a
{summary["ratio_of_medians"]:.2f}x ratio. Each timing is a median of3 full
evaluations under the same running workload; it is not a dedicated performance
benchmark. The NumPy elevation helper duplicates orbit-position work and allocates
large arrays. A20second smooth fit would therefore get fewer objective evaluations
than the hard model; any comparison must expose both budgets and actual work.

## What changed and what remains

SmoothJointObjective retains the existing joint-clock class and priors, adds
elevation derivatives to the position and satellite timing gradients, and returns
the existing WindowLikelihood interface for frequency residual reporting.
Reference coordinates are absent from its inputs. The fixed1degree taper remains
an unvalidated global model choice, not a per-scan accuracy-tuned setting.

Next: check gradient convergence with smaller finite-difference steps, then freeze
a bounded matched c0/fitted-c experiment with disclosed hard/smooth computational
costs. Independent validation and a uniform bank/selection policy across all three
datasets remain required. This iteration reports no optimized position or accuracy
gain, replaces no cohort outcome, and changes no production/RF/contracts/fixtures.
Frozen numerical source and protocol are committed before the real-data audit.
""")
