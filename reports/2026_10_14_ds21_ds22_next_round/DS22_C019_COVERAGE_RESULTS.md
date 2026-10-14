# C019 coverage pilot: complete, but no converged estimates

All 44 prescribed fits returned and sealed. None passed the unchanged strict convergence rule. Therefore neither original-six nor expanded-twenty-two selector has an estimate in either native model. No configured-reference comparison was made and no localization improvement or regression can be inferred from this experiment.

| Model | Attempted | Accepted | Objective evaluations per fit, min / median / max | KKT residual, min / median / max |
|---|---:|---:|---|---|
| Original native, projected clock initialization | 22 | 0 | 118 / 201 / 250 | 183.730 / 1430.149 / 8200.344 |
| Native common receiver clock | 22 | 0 | 154 / 202.5 / 252 | 202.272 / 930.236 / 2841.093 |

Every fit exhausted its 20-second limit; none reported solver success. Measured fitter durations were 20.07–20.21 seconds. Process CPU/wall ratios were 0.99971–0.99997, providing no evidence that core contention caused these deadlines. The six-worker wave completed all 22 paired units successfully in 369.945 seconds. Unit completion is distinct from scientific convergence.

The wider 67-satellite model is not numerically qualified for localization under this per-fit budget. This does not reject the coverage or clock hypotheses: the starting states passed physical transport and likelihood closure, but the optimizer did not reach stationary endpoints. It also does not establish that a longer budget will succeed.

The next bounded diagnostic should keep the bank, observations, model, initial states, priors and acceptance threshold unchanged and compare fresh 20-second and 60-second fits. A small training-only inventory can select the lowest returned objective within each model's original-start and coarse-start groups, then restart from those groups' original qualified initializers in both budget arms. Failed endpoints must remain ineligible as localization estimates. No geographic error should select starts or determine which outcomes are reported.

The scientific protocol and qualification are documented in `DS22_C019_COVERAGE_PROTOCOL.md`. Frozen output is `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c019-coverage-pilot-v1`; `seal.json` binds all 44 raw results, options, claims, audits and selectors. The completed DS21 cohort histogram remains unchanged.
