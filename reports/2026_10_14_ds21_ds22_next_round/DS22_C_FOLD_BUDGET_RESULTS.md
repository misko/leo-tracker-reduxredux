# C075 fresh matched budgets recover the distant training winner

Both the 20-second and 40-second selectors choose the same strictly accepted propensity state, with configured-station distance **77.664744 km**, objective 38355.694526 and NLL 38159.858137. The earlier accepted 21.331360 km propensity state remains eligible but loses 6014.775732 objective units. Recovering stationarity therefore restores a distant training-selected solution; the closer available estimate cannot be promoted by its configured distance.

The controlled 20-versus-40-second comparison shows **no time-budget benefit**: each source returns identical parameters, objectives and evaluation counts under both budgets, with solver success before 20 seconds. The previous same-source calls had hit their deadline; the fresh runs completed more work. Current CPU/wall measurements do not establish why the earlier runs were slower, and no claim of historical CPU contention is made.

| Accepted original fold source | Budget s | Accepted | Objective | KKT | Evaluations | CPU s | Invocation wall s |
|---|---:|---|---:|---:|---:|---:|---:|
| Fold 0 all geography | 20 | Yes | 38355.694526 | 0.000758968 | 355 | 16.276 | 16.277 |
| Fold 0 all geography | 40 | Yes | 38355.694526 | 0.000758968 | 355 | 16.398 | 16.413 |
| Fold 1 all geography | 20 | No | 38808.389091 | 0.003995748 | 268 | 17.168 | 17.168 |
| Fold 1 all geography | 40 | No | 38808.389091 | 0.003995748 | 268 | 17.251 | 17.252 |

All four have solver_success true. Fold 1 remains rejected under the unchanged independent KKT threshold 0.001. Increasing its deadline does not resolve early solver termination. No further retry is implicit in this result; a numerical stopping diagnostic would be distinct work.

The original raw C comparison is full 77.586921 km, CH1–4 23.428397 km and CH5–8 51.146438 km. Those historical halves use a different raw likelihood and share full-channel discovery/initialization; they are not this propensity model's matched halves. All distances use the **configured, unconfirmed station** and are not verified accuracy. No held observations or locked cases were used.

## Why this control was run

A separate frozen four-objective audit replayed the two earlier failed all-origin releases. Fold 0's projected timing/group/propensity gradients were 0.0278079 / 0.0218523 / 9.53e-5; fold 1's were 0.00731696 / 0.00456485 / 7.48e-5. Both had seven active propensity bounds, but propensity residuals were already below the strict threshold. Fold 1 also had one active physical constraint. Timing and group calibration were the principal remaining convergence directions.

The new experiment restarted from **both accepted original fixed-fold profiles**, never a failed full-data endpoint or a reference-selected state. Each source received fresh 20- and 40-second fits with the same original disk, model and 600-iteration limit. The same accepted propensity incumbent was eligible in both budget selectors. Three qualification objectives replayed both source states and the incumbent, with exact initializer preservation, in 30.691 seconds. Three driver tests, one evaluator barrier test and Ruff passed. Four audit tests also passed.

This adds four fits to the prior 23-call fold experiment. Two are accepted and two rejected; all outcomes are preserved. The original cohort and earlier failed experiment remain unchanged. No model promotion or accuracy target is claimed.

## Frozen evidence

- Gradient audit source `cd8b83d6b`, four objectives, zero fits: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c-fold-gradient-v1`.
- Budget driver source `54b7f2e41`; evaluator `338a96122`.
- Scientific namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c-fold-budget-v1/DS22-075`.
- Protocol SHA256: `691641fccbfd04223dd0945131af4edd0d69cded18ccac63308f36b47836cec9`.
- Terminal SHA256: `97f18a9376bfb2a3ae15e9237d2d369191459df91581e1a3a2672fd57b239fe9`.
- Global seal SHA256: `273029113adcfa11e780853239064ab0be255def4069ebe3452fd084bd7d71fc`.
- Post-seal comparison: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c-fold-budget-comparison-v1/report.json`.

The evaluator recursively validated all four call receipts before reading the configured reference.
