# C019 full coverage at 60 seconds: convergence improved, selected basin unchanged

The complete 44-call inventory is sealed: 40 new calls plus four exact inherited 60-second calls. **36/44 passed strict convergence.** The original-six and all-twenty-two selectors choose the same original start in both native models. Wider geographic coverage did not improve the selected configured-reference distance in this experiment.

| Model | Original-six accepted | All-twenty-two accepted | Selected start | Selected objective | Selected NLL | Configured distance km |
|---|---:|---:|---:|---:|---:|---:|
| Original native, no common clock | 5/6 | 16/22 | 0 | 42270.495787 | 41876.785059 | 142.976656 |
| Native common receiver clock | 4/6 | 20/22 | 0 | 41854.253146 | 41399.069633 | 143.256619 |

Both rows use the same fixed 67-candidate union and all original sixteen coarse centers, alongside six original endpoint controls. Objectives are compared only within a model. The original-six and expanded selectors are identical, so the expanded inventory's position delta is exactly zero within each model. This does not establish a global optimum or prove that no better basin exists.

Six rejected fits exhausted 60 seconds. Two reported solver success but failed the unchanged strict KKT rule: projected ordinal 2 at 0.00141705 and clock ordinal 2 at 0.00298663. Their objectives, 44359.047991 and 44073.750059, both lose their respective accepted selectors. Every rejected endpoint's returned objective is worse than its model's selected accepted objective; no low-objective rejected endpoint is being silently promoted or chosen by geographic error.

The six-worker forty-call wave finished in 744.527 seconds. All forty orchestration units completed without execution failures. The four inherited outcomes retain their original timing and source receipts. The earlier 20-second failures remain immutable. Comparison data were read only after the full44 seal.

The budget diagnostic and full search separate two problems. Twenty seconds was insufficient for this wider native bank. Sixty seconds provided many stationary solutions, including all sixteen coarse clock states, but did not move the training-selected position away from the distant original basin. Adding a common receiver clock likewise did not improve its configured-reference distance. Frequency fit, convergence and position accuracy must remain distinct conclusions.

Next diagnostic: evaluate the existing proper visibility-conditioned native density at **every accepted endpoint**, with exact legacy replay, normalization identity, physical/nuisance gradient and posterior closure, and current-domain KKT checks. This is a bounded zero-localization-fit test of whether support normalization changes the ordering across the wider geographic search. It must retain all accepted states rather than choose states by reference distance. The optional learned satellite-propensity model remains a separate subsequent experiment requiring fresh qualification on the expanded bank.

Driver `d58ba1078`, evaluator `61b669bb2`; four driver tests and one pre-seal reporting test passed, with Ruff clean. Scientific output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c019-full60-v1`. Sealed comparison: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c019-full60-comparison-v1`. DS22 station continuity remains unconfirmed: these are configured-reference distances, not verified position accuracy. No cohort-level result or histogram changed.
