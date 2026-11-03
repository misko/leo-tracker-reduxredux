# Fixed-height joint greedy localization: 64 independent scans

The joint greedy prototype returns accepted location estimates for **63 of 64**
independent DS9/DS10/DS11 scans under the recorded two-stage procedure. Median
horizontal error is **2,058 m**, the 90th percentile is **5,899 m**, and the worst
accepted error is **12,308 m**. Kilometer-scale errors and competing satellite
assignments remain real limitations.

The remaining scan subsequently converged in a separately logged **14-second
polish**, taking its cumulative runtime to **143.7 seconds**. Its error is
2,067 m. Including that post-hoc diagnostic, all 64 scans have converged results
and the descriptive median error is **2,060 m**. The primary and two-stage
experiments remain unchanged; this is not a retrospective 64/64 claim for the
predeclared two-stage procedure.

Every scan independently starts with the same uniform 250 km disk around
Sacramento. Height is fixed at the user's specified **100 ft (30.48 m) above
mean sea level**, with NOAA GEOID18 conversion to approximate ellipsoid height
at each candidate location. Receiver GPS is used only after predictions are
sealed to evaluate error against the recorded, unsurveyed roof reference.

| Procedure | Accepted / planned | Median error | 90th percentile | Worst accepted error |
|---|---:|---:|---:|---:|
| Previous sequential greedy | 12 / 64 | 5,514 m | 191,786 m | 216,971 m |
| Joint Student-t, 90-second primary | 51 / 64 | 1,860 m | 4,109 m | 9,112 m |
| Primary plus one continuation, at most 180 seconds total | 63 / 64 | 2,058 m | 5,899 m | 12,308 m |

Errors summarize accepted results only; plots retain all 64 scans in their
denominators. Old acceptance was completion plus geographic-support gates;
new acceptance requires numerical convergence, sealed results, successful
execution, and the stated runtime budget. The model, prior representation,
optimizer, and acceptance criteria changed together, so this is not an isolated
height ablation or an equal-criteria accuracy comparison. On the 12 scans
accepted by both the old and two-stage methods, the new median is 2,143 m versus
5,514 m, with seven improved errors and five regressions.

| Dataset | Two-stage accepted / planned | Median error | Worst accepted error |
|---|---:|---:|---:|
| DS9 | 22 / 22 | 2,195 m | 12,308 m |
| DS10 | 21 / 21 | 1,946 m | 10,721 m |
| DS11 | 20 / 21 | 1,959 m | 4,009 m |

The primary runtime median is 80.3 seconds; the two-stage median is 81.6 seconds
and the longest total is 130.5 seconds. All 64 primary attempts executed and
produced sealed receipts. Thirteen winners were unresolved after the primary
budget; twelve converged during their one recorded continuation. In the
two-stage report, DS11-F087 is unresolved after 48 iterations on its best mode.
Its objective and state steps were still decreasing, and the 24-iteration cap was
reached before the overall time budget. A separately recorded remaining-budget
polish used 14 more iterations to satisfy the unchanged convergence threshold.
This identifies an iteration-allocation limitation, not a need to loosen the
threshold. See the [polish protocol](POLISH_PROTOCOL.md) and
[polish summary](polish-summary.json).

## What changed

Fixing height and extending causal orbit support alone made the sequential
controls execute but left them approximately 264–312 km wrong. The useful
improvement required a broad spatial search, distinct initializations, joint
refitting of all retained tracks and nuisance variables, repeated satellite
reassignment, and a robust Student-t likelihood. See the
[algorithm explanation](ALGORITHM.md) and [development results](DEVELOPMENT_RESULTS.md).

The Student-t has four degrees of freedom and uses the original Gaussian
covariance matrices as scale matrices. Its covariance is twice that scale;
this is an experimental model change, not calibrated uncertainty. The optimizer
selects the lowest objective across all attempted modes and reports unresolved
when that winner has not converged, even if a worse mode has. Continuation uses
the original priors and each observation once, without posterior-prior reuse.

The former geographic/height failure described uncertainty support extending
outside permitted bounds, not measured horizontal error. Fixed height removes
the vertical degree of freedom rather than weakening that check.

## Evidence and reproducibility

- [Primary evaluation](primary-evaluation.json), [continuation evaluation](continuation-evaluation.json), and [summary statistics](result-summary.json).
- [Per-scan errors in CSV](scan-errors.csv); the separate polish is in [polish-summary.json](polish-summary.json).
- [Primary audit](primary-audit.json) and [continuation audit](continuation-audit.json): all checks pass.
- [Independent polish audit](polish-audit.json): 39 checks pass, including original and extended orbit-time support, all 50 retained tracks, parent chain, original priors, objective descent, and cumulative runtime.
- [Frozen configuration](FREEZE.json), [protocol](PROTOCOL.md), and [continuation protocol](CONTINUATION_PROTOCOL.md).
- `primary-source/` and `continuation-source/` preserve exact source snapshots; `runs/` retains all attempts, failures, seals, and launch records.
- [Mode diagnostic](PRIMARY_MODE_DIAGNOSTIC.md): objective gaps are not calibrated confidence.
- [Orbit recovery](orbit-prep/DS10-F131-recovery.json): the failed preparation attempt is preserved. Two catalogue satellites crossed an export altitude-admission cutoff only outside the original time interval. Their propagated states remained valid and finite, and both were absent from frozen fit unions. No catalogue IDs or original orbit samples were dropped or changed.

Tests cover the numerical components, height conversion, orbit extension,
source/seal validation, budget-aware acceptance, and figure denominators.
The full pre-polish suite passed 58 tests; the four new polish tests and three
continuation plotting tests passed after the final tooling changes.
These 64 recordings are a regression panel that includes development examples,
not an untouched validation set. The prototype does not establish global
optimality or calibrated uncertainty and has not been deployed in the standard
analysis pipeline.

## Figures

![All procedures, with the final follow-up explicitly labeled post-hoc](figures/final-diagnostic-error-ecdf-all64.png)

![Primary errors with all 64 scans in the denominator](figures/primary-error-ecdf-all64.png)

![Primary accepted positions near the receiver](figures/primary-spatial-roof-zoom.png)

![Primary and continuation error distributions](figures/continuation-error-ecdf-all64.png)

![Every scan's error and acceptance status](figures/continuation-per-scan-errors-status.png)

The next useful improvement is to preserve distinct plausible modes and test
their ranking on independent data, while addressing residual and nuisance-model
bias. Tightening height further will not resolve the remaining kilometer-scale
errors by itself.
