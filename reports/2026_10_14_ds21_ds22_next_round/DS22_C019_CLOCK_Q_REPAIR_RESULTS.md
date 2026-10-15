# C019 clock/propensity numerical controls: still unavailable

All four prescribed fixed-geography numerical controls completed. None satisfied the unchanged strict KKT threshold of 0.001, so all four prospective free continuations were recorded as zero-call skips. No failed profile was accepted, retried, or substituted into a selector. This experiment adds four fit attempts, not a new position estimate.

| Original profile | Method | Actual objective calls | Numerical wall seconds | Result |
|---|---|---:|---:|---|
| Original ordinal 0 | Native SLSQP endpoint repeat | 13 | 1.001 | Solver success; KKT 0.002337810, rejected |
| Original ordinal 0 | Positive-definite tangent finish | 267 | 20.043 | Deadline during Hessian work; no returned endpoint |
| Coarse ordinal 12 | Native SLSQP endpoint repeat | 22 | 1.654 | Solver success; KKT 0.001041937, rejected |
| Coarse ordinal 12 | Positive-definite tangent finish | 272 | 20.034 | Deadline during Hessian work; no returned endpoint |

The two SLSQP repeats retained objectives 39651.35945252068 and 40785.63151601394. The coarse profile's KKT improved from 0.007060624 but remained above the threshold; its small remaining failure is not waived. The original profile's KKT was effectively unchanged. Better stopping behavior is distinct from a new accepted geographic result.

The native tangent dimensions were 151 and 153. Both Newton attempts exhausted their 20-second budgets before completing the full finite-difference Hessian and its positive-definiteness certificate. They therefore do **not** demonstrate an indefinite Hessian, a failed Newton step, or absence of an improving local direction. The measured work supports a numerical-cost limitation of this particular bounded implementation. The 600-call ceiling was not reached; no regularization or altered threshold was introduced.

Actual-data qualification used four objectives and zero fits in 45.53 seconds. It replayed the source objectives, gradients, posteriors, native metadata, fixed-domain geometry, and KKT exactly. The four-call wave finished in 72.95 seconds including preparation and authority checks. Each numerical call counted terminal replay inside its actual-call budget; the deadline guard can overrun by the final already-started objective evaluation. Sources and the original failed profiles remain immutable.

Authority: protocol/source commits `34f5c7353` and `3d0f921d1`; native helper, driver and tangent component tests: 18 passed, Ruff passed. Separate post-seal evaluator `c6c909807` has a reference-ordering test. Numerical namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c019-clock-q-repair-v1`. All four fixed outcomes and four skips were sealed before reporting. No held or locked observations were read.

Clock/propensity localization remains unavailable. The previous no-clock propensity result is a separate model and is unchanged. Zero propensity remains a feasible objective bound rather than a stationary propensity incumbent. There is no accuracy improvement or promotion from this experiment.
