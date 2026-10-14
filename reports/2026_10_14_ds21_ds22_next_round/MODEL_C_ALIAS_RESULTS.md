# C029 receiver ambiguity: substantial local improvement, unchanged selected position

The matched ambiguity-refinement experiment completed all four fits, all independently stationary, in 58.78 s. Both selectors retain the original union incumbent at **83.390154 km**. The discrete shift reveals a better nearby likelihood basin, but does not fix the final training-score ranking or meet the accuracy target.

## Training-only fixed-state screen

All twelve sealed C029 endpoints, including rejected ones, were evaluated at five declared receiver-offset shifts: unchanged and ±one OFDM ambiguity interval for each receiver separately. Position, satellite timing, other calibration coefficients, nuisance values, observations and candidate bank stayed fixed. Sixty objective evaluations completed in 15.38 s with exact baseline replay and unchanged prior penalties; zero fits or reference reads occurred.

Only broader-discovery start 1 (global ordinal 1) and original-discovery start 4 (ordinal 10) improved. Both preferred receiver 1 plus 227272.727 Hz. Fixed-state objective improvements were 278.875344 and 13.298660 respectively. Both endpoints were included by this training-only rule, without filtering on acceptance or reference error.

## Four matched refinements

Each detected endpoint supplied one unchanged and one shifted starting state. All four used the unchanged native objective, fitted c, original per-start 25 km disk, and original 20 s / 600-iteration solver budget. The source incumbent remained eligible in both arms. These are new paired refinement experiments with explicit extra computation, not silent retries of the original failed jobs.

| Source ordinal | Refinement | Accepted | Objective | NLL | Error km |
|---|---|---|---:|---:|---:|
| 1 | Unshifted | yes | 38357.757934 | 38116.291616 | 5.202842 |
| 1 | Shifted | yes | 33200.718561 | 32973.971821 | 3.691118 |
| 10 | Unshifted | yes | 39821.394359 | 39254.578643 | 223.810614 |
| 10 | Shifted | yes | 39273.576981 | 38727.776716 | 222.442323 |
| Shared source incumbent | Unchanged | yes | **33034.867925** | **32763.644261** | **83.390154** |

The improved ordinal-1 state loses to the incumbent by 165.850636 objective units. Its NLL is 210.327560 worse, partially offset by a 44.476924 lower prior penalty. Thus the discrete ambiguity choice caused a substantial local optimization/likelihood difference, but neither prior-only ranking nor the one-step integer choice alone explains the remaining error. Selecting the 3.69 km state using its reference distance would be an oracle choice and is not the reported algorithm result. The single-coordinate neighborhood is not an exhaustive ambiguity search.

All accuracy values were joined only after all four outcomes and training selectors were sealed. No held observations, locked cases, new RF collection or reference-derived initializers were used.

## Evidence

- Screen source `1548ac773`; output `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-alias-neighborhood-029-v1`; result SHA256 `2ed61575273b40096d4aa6b6bc3366ed53f039d6319f37ec40ad72156b7d3aa3`.
- Paired source `366905362`, evaluator `b9c5a695c`; output `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-alias-paired-029-v1`.
- Four-call terminal SHA256 `a6109542f48269e781eac4bdfe0fd50e24c6f4109a202100011ef776f1739c5f`; seal SHA256 `b54e1554cba7e2b6dc0ef2ce579320992e6f4d0f7c1de27438e9130d196fc3a7`.
- Actual-native neighborhood closure test passed; paired-call state/budget/incumbent/no-retry and reference-gate tests passed; Ruff passed.
