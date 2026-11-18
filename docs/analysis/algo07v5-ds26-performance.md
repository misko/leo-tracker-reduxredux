# algo07v5 performance on DS26

Use fast v5 without experimental repair as the standard configuration. It had
the most successful runs (285 of 318) and the lowest mean wall time. All
position errors and mean worker times below use the same 127 recordings
that succeeded in every configuration on both repeats.

| Configuration | Mean error c=0 / fitted-c | Mean wall across repeats | Overhead |
| --- | ---: | ---: | ---: |
| No repair | 1,252 / 1,232 m | 445 s | — |
| Selective gap | 1,248 / 1,228 m | 456 s | +2.5% |
| One omitted track | 1,240 / 1,222 m | 511 s | +14.9% |
| Two omitted tracks | 1,228 / 1,211 m | 533 s | +19.8% |

Two-track recovery reduced mean error by 24 m with c=0 and 20 m with fitted-c.
It timed out 22 times versus three for no repair. All four configurations had
the same P95 position error on the matched recordings (3,084 m and 3,126 m).
The two repeats agreed on the reported error statistics. Mean wall time changed
by −1.8%, +0.5%, +0.4% and −1.9%, respectively.

Coverage: 1272/1272 outcomes; 159 frozen cases; 127 cases complete in every role and repetition.

four-or-fewer fixed CPU lanes; shared-host contention; sequential configurations and repeats within each recording lane; wall times are descriptive, not isolated latency qualification.

Position errors and selected-fit frequency metrics are separate. Both c=0 and fitted-c use matched frozen input, candidate policies and search budgets; frequency fit alone does not establish location accuracy. CV uses population standard deviation over the two repeats. Shared-host contention remains uncontrolled.

| Configuration | Statuses |
| --- | --- |
| baseline | {"complete": 285, "failed": 28, "missing": 2, "timed_out": 3} |
| selective-gap | {"complete": 283, "failed": 31, "missing": 2, "timed_out": 2} |
| omitted-track-one | {"complete": 279, "failed": 29, "missing": 2, "timed_out": 8} |
| omitted-tracks | {"complete": 265, "failed": 29, "missing": 2, "timed_out": 22} |

Same successful cohort, separately for each repeat:

| Role / repeat | Cases | Arm | Mean error m | Median m | p90 m | p95 m | p99 m | Max m | Mean wall s | Median wall s | p95 wall s | Mean CPU s |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline / r0 | 127 | c0 | 1252.045 | 987.606 | 2334.292 | 3083.809 | 6076.396 | 7268.906 | 448.996 | 423.505 | 728.861 | 404.678 |
| baseline / r0 | 127 | fitted_c | 1231.812 | 999.365 | 2179.852 | 3125.739 | 6095.192 | 6857.982 | 448.996 | 423.505 | 728.861 | 404.678 |
| baseline / r1 | 127 | c0 | 1252.045 | 987.606 | 2334.292 | 3083.809 | 6076.396 | 7268.906 | 441.034 | 400.342 | 726.389 | 396.227 |
| baseline / r1 | 127 | fitted_c | 1231.812 | 999.365 | 2179.852 | 3125.739 | 6095.192 | 6857.982 | 441.034 | 400.342 | 726.389 | 396.227 |
| selective-gap / r0 | 127 | c0 | 1248.249 | 983.008 | 2334.292 | 3083.809 | 6076.396 | 7268.906 | 454.980 | 426.859 | 747.871 | 412.144 |
| selective-gap / r0 | 127 | fitted_c | 1227.875 | 988.214 | 2179.852 | 3125.739 | 6095.192 | 6857.982 | 454.980 | 426.859 | 747.871 | 412.144 |
| selective-gap / r1 | 127 | c0 | 1248.249 | 983.008 | 2334.292 | 3083.809 | 6076.396 | 7268.906 | 457.096 | 416.104 | 742.259 | 409.578 |
| selective-gap / r1 | 127 | fitted_c | 1227.875 | 988.214 | 2179.852 | 3125.739 | 6095.192 | 6857.982 | 457.096 | 416.104 | 742.259 | 409.578 |
| omitted-track-one / r0 | 127 | c0 | 1240.226 | 983.008 | 2334.292 | 3083.809 | 6076.396 | 7268.906 | 510.339 | 472.225 | 844.563 | 465.244 |
| omitted-track-one / r0 | 127 | fitted_c | 1221.824 | 998.669 | 2190.256 | 3125.739 | 6095.192 | 6857.982 | 510.339 | 472.225 | 844.563 | 465.244 |
| omitted-track-one / r1 | 127 | c0 | 1240.226 | 983.008 | 2334.292 | 3083.809 | 6076.396 | 7268.906 | 512.444 | 475.147 | 861.753 | 471.385 |
| omitted-track-one / r1 | 127 | fitted_c | 1221.824 | 998.669 | 2190.256 | 3125.739 | 6095.192 | 6857.982 | 512.444 | 475.147 | 861.753 | 471.385 |
| omitted-tracks / r0 | 127 | c0 | 1227.934 | 980.247 | 2278.349 | 3083.809 | 6076.396 | 7268.906 | 538.213 | 505.266 | 915.702 | 491.485 |
| omitted-tracks / r0 | 127 | fitted_c | 1211.365 | 988.214 | 2190.256 | 3125.739 | 6095.192 | 6857.982 | 538.213 | 505.266 | 915.702 | 491.485 |
| omitted-tracks / r1 | 127 | c0 | 1227.934 | 980.247 | 2278.349 | 3083.809 | 6076.396 | 7268.906 | 527.975 | 500.886 | 911.184 | 495.564 |
| omitted-tracks / r1 | 127 | fitted_c | 1211.365 | 988.214 | 2190.256 | 3125.739 | 6095.192 | 6857.982 | 527.975 | 500.886 | 911.184 | 495.564 |

Repeat 1 / repeat 0, same successful cohort:

| Configuration | Timing | Median ratio | p95 ratio | Median delta s | Median CV |
| --- | --- | ---: | ---: | ---: | ---: |
| baseline | wall_seconds | 0.975 | 1.246 | -9.196 | 0.037 |
| baseline | cpu_seconds | 0.980 | 1.134 | -8.933 | 0.030 |
| selective-gap | wall_seconds | 0.999 | 1.268 | -0.429 | 0.040 |
| selective-gap | cpu_seconds | 1.004 | 1.153 | 1.420 | 0.028 |
| omitted-track-one | wall_seconds | 1.002 | 1.307 | 1.162 | 0.037 |
| omitted-track-one | cpu_seconds | 1.004 | 1.202 | 1.656 | 0.029 |
| omitted-tracks | wall_seconds | 0.996 | 1.232 | -1.390 | 0.034 |
| omitted-tracks | cpu_seconds | 1.008 | 1.220 | 3.866 | 0.024 |

Full mean/median/p90/p95/p99/max distributions for errors, frequency scores, residuals, wall and CPU seconds, all successful cases, common cases, and every per-case repeat delta/ratio/CV are in repeat-comparison.json. Paired baseline changes and matched-observation frequency residuals are in comparison.json.
