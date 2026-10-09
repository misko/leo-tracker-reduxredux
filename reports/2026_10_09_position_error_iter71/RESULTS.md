# Iteration71 results: ordinary clock proposals and continuation

**Partial: 25/63 feasible sources complete;
one further source unavailable.**
Only completed source pipelines enter the three-way comparison. All64 planned
slots remain in coverage. There are362 fit receipts so far,
including64 independent-convergence failures.
The longest recorded fit is39.866seconds;
0 reach the90-second allowance.
64 failed fits reported optimizer success
but did not pass the independent convergence gate; they remain ineligible.

![Matched source results](comparison.png)

## Score-selected winners on the matched completed-source set

| Arm | Search stage | Source | Objective | Position error km | Frequency RMS Hz |
|---|---|---:|---:|---:|---:|
| fitted-c | direct | 6 | 30690.009457 | 224.195728 | 117.399 |
| fitted-c | proposals | 12 | 30442.065661 | 253.582751 | 117.795 |
| fitted-c | continuation | 12 | 30435.285919 | 249.066896 | 117.532 |
| zero-c | direct | 6 | 30662.260999 | 221.415046 | 114.216 |
| zero-c | proposals | 12 | 30449.956852 | 249.004609 | 118.539 |
| zero-c | continuation | 12 | 30449.956852 | 249.004609 | 118.539 |

Reference error is evaluated after winner selection. These are alternative
hypotheses for one consumed recording, not independent dataset samples.
Lower objective or RMS does not establish better position accuracy. The direct
controls are new90-second unchanged-start runs; historical20-second iteration55 differences
are separately retained in summary.json, not silently ignored or substituted.
Currently50 controls are compared, with
0 convergence-flag changes and maximum
absolute objective difference0.
This is a numerical reproducibility audit, not an accuracy selection rule.

## Paired source changes relative to the new direct controls

| Arm | Stage | Improved / regressed / tied | Gained / lost convergence | Both unqualified |
|---|---|---:|---:|---:|
| fitted-c | proposals | 6 / 6 / 11 | 2 / 0 | 0 |
| fitted-c | continuation | 7 / 7 / 9 | 2 / 0 | 0 |
| zero-c | proposals | 3 / 7 / 7 | 8 / 0 | 0 |
| zero-c | continuation | 4 / 9 / 4 | 8 / 0 | 0 |

Position comparisons require both alternatives qualified, with1m tie tolerance.
Convergence gains are not counted as accuracy gains. Earlier eligible candidates
remain available, so a later score improvement can still worsen reference error.
Every fit uses90s/600; proposals and continuation add compute and recenter local
disks. Both arms share starts and stage budgets. No convergence gate is relaxed.

## Source coverage

| Source index | Region | Status |
|---:|---:|---|
| 0 | 0 | complete |
| 1 | 0 | complete |
| 6 | 1 | complete |
| 7 | 1 | complete |
| 12 | 3 | complete |
| 13 | 3 | complete |
| 18 | 4 | complete |
| 19 | 4 | complete |
| 24 | 5 | complete |
| 25 | 5 | complete |
| 30 | 6 | complete |
| 31 | 6 | complete |
| 36 | 7 | complete |
| 37 | 7 | complete |
| 42 | 8 | complete |
| 48 | 9 | complete |
| 49 | 9 | complete |
| 54 | 10 | complete |
| 55 | 10 | complete |
| 60 | 11 | complete |
| 61 | 11 | complete |
| 66 | 12 | complete |
| 67 | 12 | complete |
| 72 | 13 | complete |
| 73 | 13 | pending |
| 78 | 14 | complete |
| 79 | 14 | pending |
| 84 | 15 | pending |
| 85 | 15 | pending |
| 90 | 16 | pending |
| 91 | 16 | pending |
| 96 | 17 | pending |
| 97 | 17 | pending |
| 102 | 19 | pending |
| 103 | 19 | pending |
| 108 | 21 | pending |
| 109 | 21 | pending |
| 114 | 22 | pending |
| 115 | 22 | pending |
| 120 | 23 | pending |
| 121 | 23 | pending |
| 126 | 24 | pending |
| 127 | 24 | pending |
| 132 | 25 | pending |
| 133 | 25 | pending |
| 138 | 26 | pending |
| 139 | 26 | pending |
| 144 | 27 | pending |
| 148 | 27 | pending |
| 150 | 28 | pending |
| 151 | 28 | pending |
| 156 | 29 | pending |
| 157 | 29 | pending |
| 162 | 30 | pending |
| 163 | 30 | pending |
| 168 | 31 | pending |
| 169 | 31 | pending |
| 174 | 32 | pending |
| 175 | 32 | pending |
| 180 | 33 | pending |
| 181 | 33 | pending |
| 186 | 34 | pending |
| 187 | 34 | pending |
| zero-timing | 8 | unavailable: no feasible source arm |

The frozen [experiment policy](README.md) explains the32-region inventory,
three parent calibration failures, common bank, ordinary clock frame, two source
types, priors and tie rules. This consumed single-recording experiment does not
replace any full-cohort result or prove independent generalization. Full148 means
remain1.360148km fitted-c /1.738896km zero-c. Uniform DS16/17/18 assessment and
independent validation remain necessary. Production and RF collection unchanged.
