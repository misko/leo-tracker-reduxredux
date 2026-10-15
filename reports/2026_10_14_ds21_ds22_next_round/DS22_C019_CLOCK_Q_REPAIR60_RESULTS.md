# C019 native propensity: numerical availability repaired, geography still poor

The separate 60-second numerical control repaired both rejected fixed clock/propensity profiles without changing the strict KKT threshold, objective, constraints, or priors. Each required one positive-definite affine-tangent Newton step. Both original SLSQP repeats remained rejected.

| Fixed profile | Before KKT | After KKT | Actual evaluations | Numerical seconds | Minimum tangent Hessian eigenvalue |
|---|---:|---:|---:|---:|---:|
| Original ordinal 0 | 0.002337809 | 8.39e-9 | 305 | 21.876 | 0.201111 |
| Coarse ordinal 12 | 0.007060624 | 5.06e-9 | 309 | 22.541 | 0.093921 |

The full Hessian certificates were positive with no regularization. Objective decreases were only 6.09e-9 and 3.42e-9, so the repair principally established strict numerical availability. The actual work took slightly more than20 seconds: the earlier 20-second Hessian timeouts did not indicate negative curvature or absence of a local correction.

After all four fixed outcomes completed, both accepted complete states received their prescribed free-position continuations. Original0 was accepted at objective39638.957821, NLL39144.906684, KKT0.000191930 in30.37 seconds/390 evaluations. Coarse12 remained rejected at KKT0.003079313, despite solver success, after46.74 seconds/641 evaluations. Free calls use600 **iterations**, unlike the fixed controls'600 **actual-objective** cap; their independent final audits occur afterward. The rejected coarse release is retained and ineligible.

Only after the global seal, the training-selected original0 result was compared with the configured, unconfirmed station reference:

| Model/state | Configured-reference distance km |
|---|---:|
| Historical expanded-bank clock conditional winner | 143.256619 |
| Accepted clock/propensity release | 142.622404 |

This is not a useful localization repair. Training NLL and objective improve substantially, while the selected position stays in the distant original basin. There are no matched clock/propensity half-position fits, no held/locked evidence, and no verified accuracy claim or promotion. Zero propensity was a feasible objective bound only, not a stationary propensity incumbent; the accepted result is below that bound.

The first60-second wrapper exposed an integration defect: the reused immutable numerical core rejected seconds>20 before any objective evaluation in its two Newton units. Those guard-failure receipts remain preserved in `ds22-c019-clock-q-repair60-v1`. The separate v2 core changes only that admission guard; root independently verified AST equivalence after the single20→60 replacement. Eight component/integration tests passed, including an unmocked reproduction of the old zero-call failure and a real new PD step. The two completed SLSQP repeat outcomes were reused exactly; only the never-evaluated Newton calls were recovered. No evaluated failed call was silently retried.

Authority: source/protocol `7dcdae323`; post-seal evaluator `17c184e97`; namespaces `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c019-clock-q-repair60-v2` and adjacent `ds22-c019-clock-q-repair60-v2-comparison`. The matched60-second inventory contains six numerical calls (two reused repeats, two recovered Newton calls, two releases), plus the separately preserved zero-objective guard failures. The preceding20-second control contributed four additional attempts. Actual v2 qualification used four objectives/zero fits in47.01 seconds; all native replay fields matched prior qualification exactly.
