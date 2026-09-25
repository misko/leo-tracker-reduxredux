# DS1 iteration 24: TRAIN-only cross-fitted rate identifiability

## Decision

**No-go for the prospective fixed-coordinate rate model, and no geographic
basin is authorized.** Of 80 support-eligible sources, 65 pass every frozen
cross-fit gate and 15 fail. All 15 failures have worse aggregate omitted-track
robust loss than zero rate; eight also switch sign basin across folds, and one
also exceeds the `2 * RATE_SIGMA = 0.1835323183 s/hour` fold-range gate.

This decision uses TRAIN rows only. HELD values were never read or scored by
the fold analysis and never controlled support, coordinates, source
membership, rate, CFO, optimization, scoring, gates, or the decision. No truth
was used. The fixed coordinates and tau, the deterministic profile code, and
the full-TRAIN diagnostic rates come from the sealed iteration 23 artifact and
code.

## Method

The audit leaves one complete TRAIN track out for each eligible source. It
profiles one source rate on the remaining TRAIN tracks over diagnostic
`+/-1 s/hour`, using iteration 23's source-specific phase grid, interleaved
half-step scan, refinement of every sampled local minimum, explicit endpoints
and zero, and deterministic tie breaks. The fit objective is the sum of
pseudo-Huber observation losses with `250 Hz` scale after a separate TRAIN CFO
fit for every remaining track, plus the frozen Gaussian rate penalty.

The omitted track is then scored on TRAIN rows with only one new CFO fitted.
Its predictive score contains observation loss only. Aggregate comparison sums
the omitted-track loss over all folds, so every eligible TRAIN observation is
scored exactly once.

A source is eligible only with at least three TRAIN tracks, at least 24 total
TRAIN rows, and at least two tracks and 24 rows left in every fold. Every
ineligible source is assigned exactly `0 s/hour` in the prospective mapping.
An eligible source passes only when all folds converge, pass direct causal
SGP4 replay within `0.2 Hz`, remain interior to `+/-1`, select the same nonzero
sign basin, span no more than `0.1835323183 s/hour`, and improve aggregate
omitted-track robust loss against zero.

## Support coverage

| Group | Fixed latitude | Fixed longitude | Tau (s) | TRAIN rows | Eligible rows | Eligible sources / folds | Passing sources | Ineligible sources |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `20260921_00` | 37.903710 | -122.412040 | -0.3 | 4,785 | 3,808 | 46 / 349 | 40 | 70 |
| `20260921_16` | 37.845404 | -122.461842 | -1.1 | 5,692 | 3,159 | 34 / 137 | 25 | 101 |
| **Total** | — | — | — | **10,477** | **6,967** | **80 / 486** | **65** | **171** |

All 486 fold profiles converged, all 486 exact replays passed, and all 486
winners were interior. The largest exact-replay error was `0.000753 Hz`, far
below the `0.2 Hz` gate. Seventy-two sources kept one nonzero sign basin across
folds; 79 met the fold-range gate. The predictive aggregate gate was the
binding failure: 65 passed and 15 failed.

NORADs 57248 and 58683 each have four TRAIN rows in one track. Each fails all
four support checks relevant to that configuration, receives no folds, and is
set to exactly `0 s/hour` in the prospective mapping.

## NORAD 68739

NORAD 68739 is eligible with 134 TRAIN observations in five tracks. Every fold
selects the positive basin, remains interior, converges, passes exact replay,
and retains a resolved losing negative local minimum.

| Fold | Omitted TRAIN rows | Rate (s/h) | Best negative rate (s/h) | Negative-minus-winning fit objective | Exact max error (Hz) | Omitted fitted-minus-zero loss |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 42 | +0.557539 | -0.157285 | +37.303 | 0.000488 | -150.473 |
| 2 | 37 | +0.570785 | -0.204697 | +35.500 | 0.000538 | -151.159 |
| 3 | 10 | +0.598709 | -0.233381 | +216.815 | 0.000655 | +40.798 |
| 4 | 19 | +0.587867 | -0.196684 | +109.422 | 0.000568 | -76.697 |
| 5 | 26 | +0.620627 | -0.345590 | +302.596 | 0.000753 | +152.023 |

The fold-rate range is `0.063088 s/hour`, well inside the `0.1835323183`
limit, and no fold selects the negative basin. Aggregate omitted-track loss is
`333.964`, versus `519.472` at zero, an improvement of `185.508`. Prediction is
mixed at track level: three omitted tracks improve and two worsen. The frozen
gate is aggregate, so 68739 passes, but the result does not support a claim of
uniform per-track improvement. Its prospective full-TRAIN iteration 23 rate is
`+0.593621 s/hour`.

## What worked, failed, and was learned

The numerical machinery worked cleanly. Deterministic global profiling,
half-step coverage, exact replay, and interior checks passed for every fold in
under one minute. The audit also resolves iteration 23's main concern: 68739's
positive basin survives all five leave-one-track-out perturbations, while the
negative basin loses by substantial TRAIN objective margins.

The universal prospective model rule failed. Fifteen eligible sources do not
improve aggregate omitted-track prediction over zero, despite numerically sound
fits. Eight of those sources also have fold-dependent signs; NORAD 69551 has
mixed signs and a `0.186331 s/hour` range, just beyond the frozen limit. These
are identifiability and predictive-support failures, not optimizer failures.

Cross-fitting distinguishes stable fit geometry from uniform prediction.
NORAD 68739 is stable in rate and basin and improves in aggregate, yet two of
its five omitted tracks worsen. The evidence supports the predeclared aggregate
claim only. Sparse one-track rates from iteration 23 are not identifiable under
this policy and correctly collapse to zero.

## Precise next step

Do not launch a geographic basin and do not deploy the all-eligible rate model.
The next admissible iteration is a separately sealed, fixed-coordinate
source-admission evaluation: predeclare the 65 cross-fit passers from this
artifact as rate-enabled, set all other 186 sources to zero, freeze their
iteration 23 full-TRAIN diagnostic rates, and then score the already-existing
randomized HELD rows once without refitting. A geographic search remains a
no-go regardless of that evaluation; it would require a later prospective
plan and its own gates.

## Reproduction and sealed artifacts

`plan.json` and `audit.json` have adjacent SHA-256 seals. The machine-readable
artifact records all 251 support decisions, all 486 profiles and exact replay
checks, every omitted-track score, the prospective zero policy, explicit
68739/57248/58683 audits, source bindings, and the 58.3-second runtime.

```bash
.venv/bin/pytest -q \
  reports/2026_09_25_ds1_iteration24_crossfit_rate/test_run.py

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python \
  reports/2026_09_25_ds1_iteration24_crossfit_rate/run.py \
  --output reports/2026_09_25_ds1_iteration24_crossfit_rate/audit.json
```
