# Missing Model C estimates: bounded continuation controls

Four matched continuations recover strictly converged CH1–8 estimates for DS22-047 and DS22-059. This is availability progress, not attainment of the localization target. DS22 distances use the configured, unconfirmed reference. All fits use fitted c.

| Case | Historical CH1–8 | Historical CH1–4 km | Historical CH5–8 km | Original-chart continuation km | Diagonal-chart continuation km |
|---|---|---:|---:|---:|---:|
| DS22-047 | unavailable | 3.216082 | 4.600712 | 2.634421 | 2.976395 |
| DS22-059 | unavailable | 312.824461 | 307.991885 | 311.996473 | 312.559486 |

Both training-objective selectors choose the original-chart continuation. Neither selected estimate is below 1 km. DS22-047 now beats the historical halves; DS22-059 remains a catastrophic localization failure shared with both halves. Historical halves did not receive these extra continuations, so this is not a matched-budget channel comparison. No pilot result replaces the full-cohort curves.

| Case / chart | Training objective | Independent stationarity | Actual objective calls | Fit seconds |
|---|---:|---:|---:|---:|
| 047 original | 43723.440938 | 0.000838776 | 409 | 22.1135 |
| 047 diagonal | 46135.626361 | 0.000469062 | 155 | 9.1393 |
| 059 original | 46990.555149 | 0.000230911 | 404 | 18.6673 |
| 059 diagonal | 47034.868228 | 0.000259531 | 188 | 9.1943 |

Scaling reduces measured fit time by 2.42× and 2.03×, respectively, but leads to worse training objectives. It must not be used to discard the original-chart solution. Lower cost alone is not a localization improvement.

## Controlled design and provenance

The first two eligible labels among ordinary missing-C cases were selected without reference distances. For each case, the minimum saved training-objective endpoint among six completed, nonstationary original fits supplied one initializer. No rejected endpoint was treated as an accepted incumbent. The native observations, candidate bank, physical likelihood, priors, fitted c, and original local disk were preserved. Both arms started from the same complete state. Geographic scales stayed at one; only qualified non-geographic diagonal scales changed. Each arm used one optimizer invocation, a 60-second bound including a five-second independent-audit reserve, and 600 iterations, with an external process timeout. There was no restart or new RF collection.

Qualification used 482 objectives and 482 additional explicit orbit predictions, zero fits; all finite-difference probes were feasible with no visibility changes. The four continuations used 1,156 objectives including eight independent-audit objectives, plus four separately recorded source-replay objectives. All four passed strict independent stationarity. Both case pairs were sealed before reference evaluation, which performed zero objectives and zero fits. Evaluation checks both seals and source hashes before reading the reference.

Authoritative bulk receipts:

- `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-missing-c-diagonal-qualification-v1`
- `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-missing-c-precondition-control-v1`
- `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-missing-c-control-evaluation-v1/report.json`

These results distinguish numerical availability from geographic validity. Next modeling work should preserve the original chart as an eligible competitor and investigate the shared distant association basin in 059; merely making the existing objective converge cannot resolve that failure. A full-cohort improvement still requires the same frozen candidate policy across all eligible recordings, with missing estimates retained in the denominator.
