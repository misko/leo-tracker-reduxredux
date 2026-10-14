# Prespecified common-clock prior sensitivity: DS22-001

Doubling only the common receiver-clock prior standard deviation did not repair the combined fit in this bounded experiment. Eight of nine fits passed the unchanged stationary acceptance rule. The original full-view winning seed timed out under the changed prior, so changes in the selected full endpoint also reflect convergence attrition.

| View | Original-prior distance (km) | Doubled-clock-SD distance (km) | Sensitivity training winner |
| --- | ---: | ---: | --- |
| CH1–8 | 5.582157 | 6.801640 | low-anchor |
| CH1–4 | 4.381020 | 4.667284 | low-anchor |
| CH5–8 | 2.779966 | 2.660111 | B-profile-release |

Distances use the configured station reference, whose DS22 continuity remains unconfirmed. This is a conditional shared-discovery channel ablation with full-training-derived starts, not independent half discovery. Combined remains worse than both halves; no accuracy target or model promotion follows.

Only the common receiver-clock precision was multiplied by 0.25. Relative satellite timing, common timing and group calibration priors were unchanged. All three original seeds, their per-seed 25 km disks, channel masks and budgets were retained. Each fit received 20 seconds and at most 600 actual objective evaluations. Selection used each view's training objective among stationary outcomes. Objectives under different prior strengths were not used to select a hyperparameter.

The all-view B-profile-release start ended at 20.0927 seconds with KKT residual 23.6659 and 252 objective evaluations. Its lower raw objective was rejected and retained without retry. Both alternative all-view starts and all six half-view starts were accepted. An outer logging statement encountered a missing stationarity field only after the all-view seal; the two still-unattempted views then ran normally. No numerical call was repeated.

An 18-evaluation zero-fit qualification reproduced the original-scale saved objectives and verified that only the prescribed clock penalty and gradient changed. Component tests cover the exact original-scale oracle and unchanged likelihood/posteriors, physical gradients and group precision. A separate two-evaluation postseal diagnostic reproduced both selected full objectives and decomposed their scores:

| Selected full endpoint | Low NLL (1811 windows) | High NLL (1418 windows) | Low signal mass | High signal mass |
| --- | ---: | ---: | ---: | ---: |
| Original prior | 22248.954156 | 17472.138968 | 1227.964275 | 965.490239 |
| Doubled clock SD | 22053.642893 | 18527.980303 | 1248.803117 | 789.482229 |

| Prior contribution | Original selected endpoint | Sensitivity selected endpoint |
| --- | ---: | ---: |
| Common satellite timing | 0.212632 | 0.014503 |
| Relative satellite timing | 288.769091 | 248.032202 |
| Common receiver clock | 94.850188 | 20.815520 |
| Group contrast | 0.398174 | 0.398924 |

The changed selected endpoint improves low-band likelihood but loses substantial high-band likelihood and assigned signal mass. These are descriptive differences between accepted states, not proof that weakening the prior causes worse geography: the prior definition changed and one promising starting basin did not converge. No reference or held data entered qualification, fitting, selection or decomposition. No normalization bug is inferred.

Sources: `1d013d1c8` numerical component/pilot, `5ee57994c` evaluator, `7dfb8d3a3` decomposition. Evidence is under `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-native-prior-{pilot,comparison,scores}-v1`. The earlier disk-full incident affected only an uncommitted, unfrozen driver; it was restored and tested before any sensitivity protocol or scientific call existed.
