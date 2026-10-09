# Iteration60: ordinary-start smooth-horizon pilot

**Partial: 1/32 fully paired regions.** Each region requires hard and
smooth results in both c arms before entering this comparison. All32 planned
regions remain in coverage. This is consumed DS18 development, not independent
validation; no result replaces a cohort error or establishes an operational fix.

![Paired position outcomes](comparison.png)

## Provisional score-selected winners and computation

| Model | Arm | Winner index | Error km | RMS Hz | Converged/failed | Median evaluations | Median seconds |
|---|---|---:|---:|---:|---:|---:|---:|
| hard | fitted-c | 0 | 267.787720 | 119.780 | 1/0 | 597.0 | 9.84 |
| hard | zero-c | 0 | 267.899140 | 120.434 | 1/0 | 630.0 | 10.39 |
| smooth | fitted-c | 0 | 267.955719 | 119.488 | 1/0 | 598.0 | 40.82 |
| smooth | zero-c | 0 | 267.966413 | 120.709 | 1/0 | 625.0 | 42.26 |

Winners minimize objective among converged fits, ties by ascending frozen index.
Reference errors are calculated afterward. Cross-model objectives are not treated
as localization improvements. The table's computational medians include failed
fits on the matched completed subset, not just successful winners.

Smooth uses90seconds/600iterations versus hard20seconds/600iterations, following
the measured4.45x evaluation cost. **This is not equal wall-time allowance.**
Both c arms share budgets within each model. No convergence gate is relaxed.
Shared inputs: common145 bank, ordinary calibration, sigma1/common3, joint100,
residual slopes60, local25km, identical ordinary seeds. Global1degree smoothstep
is the model change. No recovered joint seed or reference-guided selection is used.

One first feasible endpoint per successful region is the frozen pilot policy;
it does not use all187 feasible starts. All192 source endpoints,5infeasible and
the3earlier regional calibration failures remain in iterations41/53. Hard
controls use exactly the pilot indices from iteration55. This subset must not
be compared with the best winner over all192 endpoints as if budgets matched.
Prior tuning is consumed development. Uniform policy across DS16/17/18 and
independent validation remain required. Production/RF/contracts unchanged.

## Full pilot coverage

| Endpoint | Hard fitted-c | Hard c0 | Smooth fitted-c | Smooth c0 |
|---:|---|---|---|---|
| 0 | converged | converged | converged | converged |
| 6 | converged | converged | converged | pending |
| 12 | converged | failed | pending | pending |
| 18 | converged | failed | pending | pending |
| 24 | converged | failed | pending | pending |
| 30 | converged | converged | pending | pending |
| 36 | converged | failed | pending | pending |
| 42 | converged | failed | pending | pending |
| 48 | pending | pending | pending | pending |
| 54 | pending | pending | pending | pending |
| 60 | pending | pending | pending | pending |
| 66 | pending | pending | pending | pending |
| 72 | pending | pending | pending | pending |
| 78 | pending | pending | pending | pending |
| 84 | pending | pending | pending | pending |
| 90 | pending | pending | pending | pending |
| 96 | pending | pending | pending | pending |
| 102 | pending | pending | pending | pending |
| 108 | pending | pending | pending | pending |
| 114 | pending | pending | pending | pending |
| 120 | pending | pending | pending | pending |
| 126 | pending | pending | pending | pending |
| 132 | pending | pending | pending | pending |
| 138 | pending | pending | pending | pending |
| 144 | pending | pending | pending | pending |
| 150 | pending | pending | pending | pending |
| 156 | pending | pending | pending | pending |
| 162 | pending | pending | pending | pending |
| 168 | pending | pending | pending | pending |
| 174 | pending | pending | pending | pending |
| 180 | pending | pending | pending | pending |
| 186 | pending | pending | pending | pending |
