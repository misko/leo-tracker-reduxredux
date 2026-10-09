# Curvature-aware qualification of the lost ordinary region

**The ordinary failed calibration prefit now qualifies under the unchanged 0.001 stationarity gate.** Full scaled projected KKT falls from 0.00153543861071 to 0.000845178642467, after one round and six exact objective/gradient evaluations. This does not yet establish a better final position; the prefit holds position fixed.

![Qualification, roundoff-sized score change and timing step](qualification.png)

| Quantity | Before | After |
|---|---:|---:|
| Exact objective | 40696.314622537 | 40696.3146225371 |
| Full KKT | 0.00153543861071 | 0.000845178642467 |
| Qualification gate | 0.001 | 0.001 |
| Horizontal prefit position | Fixed ordinary region | Identical |

The selected coordinate is 20, relative-timing basis coefficient 12, with a step of **-1.61119188484e-08 s** (-16.111919 ns). This is a zero-sum basis coefficient, not an independently measured satellite clock. It changes no position coordinate, candidate bank, RF prior or timing prior.

Central gradient probes at ±1e-5 estimate curvature 95298.3083617. The predicted scalar score benefit is 1.23694311463e-11, only 1.700 ULP. The measured score instead rises by 4.36557456851e-11, **6 ULP**, consistent with a change below useful score resolution. The globally frozen allowance is 128 initial-score ULP (9.31322574615e-10). It is a fixed total ceiling, not a per-step allowance or a relaxed KKT threshold.

## Gradient evidence and limits

The algorithm compares full independent KKT over all free coordinates, not only the stepped coordinate. The independently repeated final audit agrees at 0.000845178642467. Its largest remaining component is coordinate 19 (relative timing basis 11), with scaled raw/projected gradient -0.000845178642467. Full returned gradient vectors and every probe/trial remain in [result.json](result.json).

| Central scaled step | Objective finite-difference derivative |
|---:|---:|
| 0.0001 | -0.00222753442358 |
| 1e-05 | -0.000854561221786 |
| 1e-06 | -0.000905856722966 |

These checks cover the worst remaining coordinate, not every derivative. The 1e-5 derivative is close to the analytic gradient; larger-step nonlinearity and smaller-step objective cancellation limit the finite-difference comparison. Qualification is proven under the existing numerical gate, not as a global minimum or complete proof of every gradient implementation.

## Frozen provenance and publication sequence

All **668** frozen source/input hashes still match. The original 93 prefit receipt hashes and 94 numerical result are unchanged; their inherited executable closures also match. This includes the original failed trials, which are preserved rather than rewritten as successes.

Protocol and executable sources were committed locally at `db56090b2` before execution. The first remote push was rejected because concurrent web work advanced main. After execution, that web commit `3b0a8c409` was merged and the frozen preparation was pushed. **This is local pre-execution freezing, not remote prepublication.** The merge did not change the pinned scientific sources. [Protocol](protocol.json) and [verification](verification.json) record the source and receipt hashes.

A separately frozen calibration/association/final-fit continuation is needed to establish whether retaining this ordinary region improves the published 55.685 km fitted-c failure. No reference-guided seed or score selection, reserve access, new RF collection or production change occurred.
