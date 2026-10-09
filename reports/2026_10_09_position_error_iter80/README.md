# Iteration80: complete ordinary clock-start experiment

**All 63 feasible ordinary sources completed. Score-selected position errors are
4.465721 km fitted-c and 0.889093 km c=0**, versus 58.398433 and 58.639244 km
for matched direct controls. Both workers exited0. No reference-guided recovered
seed or reference-error winner selection entered the experiment.

This is DS18-022 (`scan-fw-f1a32cacd910c005`, previously `RESERVED-001`), a consumed
development case. It does not establish a uniform full-cohort improvement or
independent validation. The unchanged full148 means remain1.360148 km fitted-c
and1.738896 km c=0. No result here is spliced into those means.

![Complete matched ordinary-source results](../2026_10_09_position_error_iter71/comparison.png)

| Arm | Stage | Selected source | Objective | Error km | Frequency RMS Hz |
|---|---|---:|---:|---:|---:|
| fitted-c | Direct | 180 | 30030.854328 | 58.398433 | 97.599 |
| fitted-c | Clock proposals | 180 | 29983.252593 | 56.567544 | 99.786 |
| fitted-c | Complete-state continuation | 126 | 29558.389743 | 4.465721 | 100.789 |
| c=0 | Direct | 180 | 30102.360078 | 58.639244 | 102.908 |
| c=0 | Clock proposals | 115 | 29442.158624 | 0.889093 | 93.170 |
| c=0 | Complete-state continuation | 115 | 29442.158624 | 0.889093 | 93.170 |

The fitted winner has a worse frequency RMS despite much better positioning.
RMS and mixture-model score are distinct, and neither alone proves localization
accuracy. Position errors were calculated only after score-based selection.

## Coverage, failures and compute

All64 planned slots are accounted for:63 feasible sources and1 unavailable
zero-timing source (infeasible in both source c arms). They originate from32
successful regional calibrations; three parent calibration failures remain
documented. All882 requested fits completed, including155 unqualified fits;
150 of those reported optimizer success but failed the independent stationarity
check. They remain ineligible. The longest fit took71.964 seconds, none reached
the90-second allowance. Summed fit time is9757.029 seconds across two workers.
Extra proposals and recentered continuation disks add computation; this is not
an equal-total-budget comparison with direct fitting.

Both arms used the same145-satellite union, observations, sigma1 timing prior,
clock prior, receiver slope bounds, starts and per-stage budgets. The bank was
built from the reference-free inventory; its32-region budget was developed on
this already consumed failure. The ordinary inventory and complete-state
continuation are reference-free at execution, not independently validated.
The historical1.15 km recovered seed retains its reference-guided ancestry.

| Arm | Stage vs direct | Improved / regressed / tied | Gained / lost convergence |
|---|---|---:|---:|
| fitted-c | Proposals | 16 / 14 / 21 | 12 / 0 |
| fitted-c | Continuation | 18 / 18 / 15 | 12 / 0 |
| c=0 | Proposals | 14 / 16 / 15 | 18 / 0 |
| c=0 | Continuation | 18 / 18 / 9 | 18 / 0 |

Paired position counts require both alternatives qualified, with1m tie tolerance.
Convergence gains are separate, not silently counted as positional improvements.
These sources are hypotheses for one recording, not independent samples.

## Longer controls and unresolved fitted-c stopping

Of126 direct controls,124 reproduce historical20-second objective and convergence
within1e-6. Two old deadline-limited failures now pass the independent check:
source90 c=0 takes31.016s; source132 fitted-c takes33.245s. The latter returns a
qualified objective0.014268 higher than the old unqualified minimum; accepting a
stationary point rather than a lower-score unfinished trial is deliberate. Its
optimizer success flag remains false, reinforcing that the independent gate,
not the solver status alone, determines qualification. New90-second controls
remain the paired comparators throughout.

The lowest-objective unqualified fitted-c result is source115 continuation6:
objective29403.224325, stationarity0.660512 versus required0.001, solver-success
true,9.708s. It is lower than the qualified winner but remains ineligible. It is
not deadline-limited, and its largest clock coefficient285.036 Hz is far inside
the2000 Hz nuisance bound. This narrows the next question to convergence and
derivative behavior rather than simply increasing time or accepting the result.

Next, any recovery test must select failed attempts by score/convergence across
the entire completed inventory, never by reference proximity. Preserve the
original results and freeze an explicit retry/gradient-check protocol first.
The prepared full148 slope-prior sensitivity experiment78 remains ready, using
two workers only after this run. No production settings, RF collection, or
POST18-reserve outcomes changed. The persistent below1km goal is unachieved.

The [complete source report](../2026_10_09_position_error_iter71/RESULTS.md) and
[summary](../2026_10_09_position_error_iter71/summary.json) retain every source,
raw receipt, paired comparison and historical-control difference. This report's
integrity file pins the complete882-receipt snapshot and all63 completion markers.
