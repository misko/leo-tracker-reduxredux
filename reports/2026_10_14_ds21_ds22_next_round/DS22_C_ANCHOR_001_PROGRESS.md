# First sealed C independent-anchor diagnostic

DS22-001 completed its prescribed training-only anchor/profile/release slice.
DS22-003 remains pending its independent half models. No new reference join
has occurred; both case seals are required before paired position reporting.

The genuine original full-C model and both independent half-model seals passed
qualification in41.819seconds, zero optimizer calls. The original full winner's
objective replayed. Its timing-boundary initializer margin changed physical
coordinates by at most1.0533e-9; all non-geographic parameters and nuisance
coefficients were identical across the three anchor initializations.

| Anchor/stage | Training objective | Stationarity statistic | Seconds | Accepted |
| --- | ---: | ---: | ---: | --- |
| Original all / profile | 41863.551059 | 0.000109818 | 0.863 | yes |
| Original all / release | 41863.551059 | 0.000109817 | 0.748 | yes |
| Independent low / profile | 42149.804513 | 1198.827934 | 20.059 | no |
| Independent high / profile | 43855.017537 | 294.249491 | 20.041 | no |

Four calls occurred; the two releases after failed profiles were skipped by
the prespecified rule. The only accepted released state reproduces the
original full-C solution. The two alternative profiles exhausted their20second
fit budgets, so their higher objective values are not evidence that their
geographic basins cannot improve the model. No time-budget extension, restart,
acceptance relaxation or incumbent substitution occurred.

Implementation d27809098 passed seven owned tests and Ruff, including small
timing-margin handling and rejection of mismatched/nonstationary independent
anchor sources. Exact sources, qualified vectors, launch/outcome/termination
receipts and the aggregate seal are under
`local/ds22-c-independent-anchor-v1/DS22-001/`. The next step is the unchanged
prespecified003 control, followed by the paired assessment.
