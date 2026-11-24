# Second-screen attrition did not predict DS30 error excess

Higher charted second-screen attrition was associated with **smaller** candidate-minus-installed position error on the 24 shared fixes outside the two motivating controls. Kendall tau-b was **−0.232 at fixed `c = 0`** and **−0.217 at fitted `c`**. The two prospective captures gave one discordant comparison in each arm. The released screen measurements supply no evidence for the proposed high-attrition retry signal across this sample. [Frozen protocol](ds30-second-screen-attrition-protocol.md) · [First-30 prediction](measurements/ds30-second-screen-first30-prediction.json.gz) · [First-30 score](measurements/ds30-second-screen-first30-scored.json.gz)

Subtracting the second screen’s retained conditional support from its exact entering support reproduces **400/2,209 (18.11%)** for DS30-0220 and **71/1,990 (3.57%)** for DS30-0086. Those two accepted-repair controls motivated the test and are excluded from all results below. Outside them, the exact counts are present for **25/28** assigned captures. The three unavailable signals are joint withholds before the screen, DS30-0107, DS30-0102 and DS30-0314. Installed also had one solver failure, DS30-0397, so 24 recordings enter each shared-fix rank.

| Candidate route | Shared fixes | Excess tau-b, fixed / fitted | Concordant vs discordant, fixed | Concordant vs discordant, fitted |
| --- | ---: | ---: | ---: | ---: |
| All with exact screen counts | 24 | −0.232 / −0.217 | 106 vs 170 | 108 vs 168 |
| Accepted repaired result | 9 | +0.167 / +0.278 | 21 vs 15 | 23 vs 13 |
| Completed without repair | 13 | −0.359 / −0.385 | 25 vs 53 | 24 vs 54 |
| Already fell back after screening | 2 | −1.000 / −1.000 | 0 vs 1 | 0 vs 1 |

There were no tied comparisons. Over the 24 shared fixes, tau-b against absolute error was **−0.275 / −0.290** for installed and **−0.391 / −0.377** for the candidate. The accepted-repair subset points in the hypothesized direction. It is a subset defined by what happened after the screen, and its association did not extend to the other routes or the whole cohort. The candidate uses a different receiver packet, so these associations cannot attribute the position difference to either receiver or solver.

## Cost of the frozen 10% retry

Five of 28 cases would trigger. Four already had smaller candidate error in both arms. Replaying installed on the fifth, DS30-0124, restores a fix within 2 km in both arms. The full counterfactual charges **599.876 s wall / 529.449 s CPU** of installed runs on top of the original candidate clocks. This includes a new installed full replay on DS30-0147 after its candidate had already paid **59.334 s wall / 59.094 s CPU** for fallback inference. The installed DS30-0397 failure contributes **90.017 s wall / 77.353 s CPU** through exit only. All other measured runs include common publication verification.

| Strategy | Sum wall | Sum CPU | Fixes per arm | Within 1 km, fixed / fitted | Within 2 km, fixed / fitted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Installed | 2,578.877 s | 2,269.374 s | 24/28 | 14 / 17 | 24 / 24 |
| Candidate | 1,581.427 s | 1,468.556 s | 25/28 | 12 / 13 | 21 / 21 |
| Candidate plus indicated installed replay | 2,181.304 s | 1,998.004 s | 25/28 | 12 / 13 | 22 / 22 |

The retry sum ratios to installed are **0.846 wall / 0.880 CPU**, and the median paired ratios are **0.602 / 0.634**. The apparent time advantage over installed comes with lower counts within both distance thresholds. Partial acquisition or a truly early screen would be a different, unmeasured workflow.

## Reserved next two

Both builds fixed both arms on both captures and each candidate completed without repair. At **250/2,762 (9.05%)**, DS30-0067 was the higher-attrition case and improved by **0.789 / 0.721 km**. DS30-0413 dropped **130/3,029 (4.29%)** and worsened by **0.144 / 0.075 km**. Neither crossed 10%. Their candidate clocks sum to **123.000 s wall / 112.883 s CPU**, versus **221.317 / 193.632 s** installed. One comparison per arm supplies no stable rank or threshold estimate. [Prospective prediction](measurements/ds30-second-screen-next2-prediction.json.gz) · [Prospective score](measurements/ds30-second-screen-next2-scored.json.gz)

Frozen protocol commit `4a0430249`. The first-30 export seal is `84fc1193f55485f66a20b703fc52540fb8c94301937769759e4ed07a75b3af92`. The prospective seal `541588f35a91598ab5340660efd833df707523c5cab0fcebbb117f78a615dc4e` binds combined export `47cee10d70ad04b3e1dffa26754e8d54baeaa1602c91e8a0552fd1e4a694eb9a`. Both candidate-only prediction files were sealed before scoring. The readout joined only saved original pair, publication and witness metadata. Eight tests passed, with no IQ, orbit reads or solver launches. [Readout](ds30_second_screen_attrition.py) · [Tests](../../../tests/pipeline_eval/test_ds30_second_screen_attrition.py)
