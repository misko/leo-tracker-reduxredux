# DS1 iteration 22: randomized-time predictive scorer prototype

## Scope

This iteration prototypes the scorer only. It does not run or authorize a new
geographic basin. The smoke replay uses the two six-session DS1 TRAIN cases at
their original sealed `shared_time` coordinates and taus. Those coordinates
and taus were selected using randomized TRAIN rows before held evaluation.

The exact `Prepared` contract already has a `train` mask. The later
full-observation adapter used by iterations 12 through 20 deliberately replaces
that mask with all `True`, so it cannot support a predictive comparison. This
prototype instead loads the receipt-bound masks through the original DS1
`make_engine` API and passes that engine directly to the exact orbit `prepare`
API. Candidate identity is consequently selected from TRAIN rows only.
The small adapter adds the already-verified cache directory to each session;
the original DS1 engine retains its receipt/cache digests but omits that path,
which the causal exact-node builder needs to recover snapshot provenance.

## Frozen comparison

Both arms use the same coordinate, tau, TRAIN-selected identity, causal TLE,
observations, cap, and occupied-second weights. The zero-rate arm fixes every
per-NORAD phase rate to zero. The rate arm fits the historical regularized
per-NORAD scalar objective from iteration 12 using TRAIN rows only. The rates
are conditionally independent after profiling TRAIN CFO, avoiding the much
slower numerical-gradient joint optimizer. Each arm independently fits its per-track
constant CFO from TRAIN rows, then predicts HELD rows without refitting.

Unsupported TRAIN identities remain at the cap in both arms. Track losses are
weighted by occupied seconds within each recording and the six recording
scores receive equal weight. HELD rows cannot select any parameter or control
flow.

## Evidence boundary

The smoke result is a randomized within-track prediction check at two fixed
coordinates. It is not a geographic estimate, a basin result, a new-session
transfer test, or untouched validation. The historical randomized held rows
have already been inspected elsewhere in DS1, so this remains regression
evidence even though the implementation preserves the fit/evaluation boundary.

## Smoke result

The two fixed-point replays complete with 4,785 TRAIN / 3,500 HELD observations
in group `20260921_00` and 5,692 TRAIN / 3,994 HELD observations in group
`20260921_16`. All 774 eligible tracks receive a TRAIN-selected identity; no
unsupported track is silently removed.

| Group | Zero-rate TRAIN | Rate TRAIN | Zero-rate HELD | Rate HELD | HELD delta |
|---|---:|---:|---:|---:|---:|
| `20260921_00` | 0.130075 | 0.044743 | 0.154682 | 0.059842 | -0.094840 |
| `20260921_16` | 0.136759 | 0.075101 | 0.143913 | 0.079438 | -0.064475 |

The TRAIN-fitted rate arm improves HELD loss in all twelve individual sessions.
Both zero-rate exact gates have zero maximum interpolation error. The fitted-rate
gates pass at `4.28e-5` and `7.65e-5 Hz` maximum error.

This is positive evidence that per-NORAD rate structure predicts randomized
HELD times rather than merely reducing full-observation residuals. It does not
qualify the current `+/-0.25 s/hour` rate model: one fitted source in group `00`
and three in group `16` reach the effective numerical boundary. A widened,
predeclared TRAIN-only scalar fit must be audited before any basin uses this arm.

The full basin remains blocked until a widened-rate smoke reproduces the held
comparison, all rate optimizers converge away from their guards, and a separate
prospective search plan freezes how TRAIN loss selects the shared coordinate
without consulting HELD loss.

## Reproduction

```bash
.venv/bin/pytest -q \
  reports/2026_09_25_ds1_iteration22_randomized_time_predictive/test_run.py

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python \
  reports/2026_09_25_ds1_iteration22_randomized_time_predictive/run.py \
  --output \
  reports/2026_09_25_ds1_iteration22_randomized_time_predictive/smoke.json
```
