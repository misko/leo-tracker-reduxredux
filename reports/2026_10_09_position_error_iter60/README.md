# Iteration60: smooth-horizon pilot launched from ordinary regions

This is a frozen consumed-data development experiment on the DS18 failure,
not independent validation or a replacement for any cohort result. No accuracy
result is claimed in this launch receipt. Execution is in progress.

The32 selected starts are the first feasible ordinary endpoint in each successful
region from iteration53, exactly those audited in iterations58/59. No recovered
diagnostic joint seed is used. The full192-endpoint census and its5infeasible
endpoints remain preserved. This pilot intentionally uses one start per region,
not all187 feasible starts; it does not silently drop failed regions from coverage.
The3 earlier calibration failures remain documented in iteration41.

Each selected start gets fitted-c and c0, for64 planned fits. Shared settings:
common145 bank, ordinary calibration frame, relative timing sigma1/common3,
joint100 clock prior, residual slope60 and25km local disk. The only model change
is the global1degree smooth horizon from the derivative-qualified prototype.
Known receiver coordinates and errors never enter fit selection or its evaluator.

Comparison hard fits come from exactly the same endpoint indices in iteration55.
Only matched completed pairs should be compared. Each model selects its winner
using converged objective and ascending-index ties; cross-model objective values
are not localization accuracy. Report position error afterward, RMS separately,
all failures and actual evaluations/time. Keep all32 regions in coverage.

Smooth fits allow90seconds and600iterations; hard fits allow20seconds and600
iterations. This is an equal iteration cap, **not an equal wall-time comparison**.
The4.5x allowance follows the measured4.45x evaluation cost, not position error.
The two c arms have identical budgets within each model. No convergence gate is
relaxed. Results remain immutable and protocol-bound; resumption skips receipts.

![Prerequisite gradient step-size audit](../2026_10_09_position_error_iter59/convergence.png)

Iteration59 reduced maximum common-timing finite-difference discrepancy from
.003045 to.0000386 at the smallest step. This supports an exploratory fit, not
proof of optimizer convergence or accurate localization. Independent validation
and uniform frozen policy across DS16/DS17/DS18 remain required before any
generalization claim. Production, contracts, fixtures and RF are unchanged.
