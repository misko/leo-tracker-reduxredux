# Measured GLRT search results

Generated from `summary.json`. CPU and wall times are mean per-visit medians across two repeats. Science counts each visit once. Recovery is relative to the original detector, not physical truth.

## Priority: 2.5 MS/s

| Method | CPU ms/dwell | Wall ms/dwell | CPU speedup | Confirmations recovered | Positive hypotheses recovered |
|---|---:|---:|---:|---:|---:|
| Original | 1243.5 | 1250.3 | 1.00× | 32/32 (100.0%) | 761/761 (100.0%) |
| Exact optimized | 1179.3 | 1182.5 | 1.05× | 32/32 (100.0%) | 761/761 (100.0%) |
| 11 windows × 6 candidates | 1039.7 | 1045.1 | 1.20× | 32/32 (100.0%) | 726/761 (95.4%) |
| 11 windows × 4 candidates | 949.9 | 963.3 | 1.31× | 32/32 (100.0%) | 658/761 (86.5%) |
| 6 windows × 8 candidates | 634.0 | 679.1 | 1.96× | 32/32 (100.0%) | 425/761 (55.8%) |
| 4 windows × 8 candidates | 424.2 | 426.1 | 2.93× | 30/32 (93.8%) | 269/761 (35.3%) |
| 3 windows × 8 candidates | 318.4 | 322.3 | 3.91× | 26/32 (81.2%) | 205/761 (26.9%) |
| 6 windows × 2 candidates | 452.1 | 452.4 | 2.75× | 32/32 (100.0%) | 260/761 (34.2%) |
| 4 windows × 2 candidates | 295.3 | 297.7 | 4.21× | 29/32 (90.6%) | 174/761 (22.9%) |
| Progressive 4-window start | 441.0 | 445.1 | 2.82× | 32/32 (100.0%) | 275/761 (36.1%) |

## All supported sample rates

Cells show CPU milliseconds per dwell / matched-confirmation recovery. Higher-rate results each contain only four visits.

| Method | 2.5 MS/s | 5 MS/s | 7.5 MS/s | 10 MS/s |
|---|---:|---:|---:|---:|
| Original | 1243.5 / 32/32 (100.0%) | 3536.7 / 4/4 (100.0%) | 6669.2 / 2/2 (100.0%) | 11681.5 / 4/4 (100.0%) |
| Exact optimized | 1179.3 / 32/32 (100.0%) | 3367.9 / 4/4 (100.0%) | 6539.7 / 2/2 (100.0%) | 11811.8 / 4/4 (100.0%) |
| 11 windows × 6 candidates | 1039.7 / 32/32 (100.0%) | 3180.0 / 4/4 (100.0%) | 6396.9 / 2/2 (100.0%) | 11163.5 / 4/4 (100.0%) |
| 11 windows × 4 candidates | 949.9 / 32/32 (100.0%) | 2949.3 / 4/4 (100.0%) | 6279.3 / 2/2 (100.0%) | 10875.1 / 4/4 (100.0%) |
| 6 windows × 8 candidates | 634.0 / 32/32 (100.0%) | 1798.6 / 4/4 (100.0%) | 3917.4 / 2/2 (100.0%) | 6367.8 / 4/4 (100.0%) |
| 4 windows × 8 candidates | 424.2 / 30/32 (93.8%) | 1266.7 / 4/4 (100.0%) | 2532.6 / 2/2 (100.0%) | 4066.5 / 4/4 (100.0%) |
| 3 windows × 8 candidates | 318.4 / 26/32 (81.2%) | 913.7 / 4/4 (100.0%) | 1858.4 / 2/2 (100.0%) | 3012.5 / 4/4 (100.0%) |
| 6 windows × 2 candidates | 452.1 / 32/32 (100.0%) | 1566.1 / 4/4 (100.0%) | 3085.6 / 2/2 (100.0%) | 5638.0 / 4/4 (100.0%) |
| 4 windows × 2 candidates | 295.3 / 29/32 (90.6%) | 1041.6 / 4/4 (100.0%) | 2277.0 / 2/2 (100.0%) | 3892.1 / 4/4 (100.0%) |
| Progressive 4-window start | 441.0 / 32/32 (100.0%) | 2332.4 / 4/4 (100.0%) | 5821.4 / 2/2 (100.0%) | 7912.0 / 4/4 (100.0%) |

## Fastest tested methods passing each development gate

This is selection on an exposed development cohort, not an independently validated deployment choice.

| Rate MS/s | Required confirmation recovery | Fastest passing method | CPU ms | CPU speedup |
|---:|---:|---|---:|---:|
| 2.5 | 90% | 4 windows × 2 candidates | 295.3 | 4.21× |
| 2.5 | 80% | 4 windows × 2 candidates | 295.3 | 4.21× |
| 5 | 90% | 3 windows × 8 candidates | 913.7 | 3.87× |
| 5 | 80% | 3 windows × 8 candidates | 913.7 | 3.87× |
| 7.5 | 90% | 3 windows × 8 candidates | 1858.4 | 3.59× |
| 7.5 | 80% | 3 windows × 8 candidates | 1858.4 | 3.59× |
| 10 | 90% | 3 windows × 8 candidates | 3012.5 | 3.88× |
| 10 | 80% | 3 windows × 8 candidates | 3012.5 | 3.88× |

## Mixed-rate cohort

The average weights the actual 16/4/4/4 visit mix, not a deployment rate distribution.

| Method | CPU ms | Wall ms | CPU speedup | Confirmations recovered | Hypotheses recovered | Exact full outputs |
|---|---:|---:|---:|---:|---:|---:|
| Original | 3837.4 | 3848.7 | 1.00× | 42/42 (100.0%) | 1154/1154 (100.0%) | 28/28 |
| Exact optimized | 3776.7 | 3801.4 | 1.02× | 42/42 (100.0%) | 1154/1154 (100.0%) | 28/28 |
| 11 windows × 6 candidates | 3557.0 | 3616.9 | 1.08× | 42/42 (100.0%) | 1107/1154 (95.9%) | 0/28 |
| 11 windows × 4 candidates | 3414.7 | 3434.6 | 1.12× | 42/42 (100.0%) | 1000/1154 (86.7%) | 0/28 |
| 6 windows × 8 candidates | 2088.5 | 2121.6 | 1.84× | 42/42 (100.0%) | 638/1154 (55.3%) | 0/28 |
| 4 windows × 8 candidates | 1366.1 | 1388.8 | 2.81× | 40/42 (95.2%) | 412/1154 (35.7%) | 0/28 |
| 3 windows × 8 candidates | 1008.3 | 1012.3 | 3.81× | 36/42 (85.7%) | 313/1154 (27.1%) | 0/28 |
| 6 windows × 2 candidates | 1728.3 | 1740.0 | 2.22× | 42/42 (100.0%) | 379/1154 (32.8%) | 0/28 |
| 4 windows × 2 candidates | 1198.8 | 1200.6 | 3.20× | 39/42 (92.9%) | 253/1154 (21.9%) | 0/28 |
| Progressive 4-window start | 2547.1 | 2566.6 | 1.51× | 42/42 (100.0%) | 422/1154 (36.6%) | 2/28 |

This receipt is explicitly composite; consult its predecessor hashes and restart provenance. In the reported experiment, only the final 10 MS/s timing repeat spans a process restart; all repeat-zero science and both lower-rate repeats precede it.
