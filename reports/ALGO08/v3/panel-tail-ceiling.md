# How much can faster withdrawals and publication save on the enrolled DS30 panels?

The first four and first sixteen DS30 recordings contain **zero v3 withdrawals**. Across the historical 55 there is one, DS30-0227, which took **1.309 s out of 5,638.25 s**. Its bootstrap is important to users waiting for a short recording. Substantial progress on the panel timing gates has to come from recordings that produce positions. No recordings were reprocessed for this calculation. [Original recording decisions and elapsed clocks](first-55/recordings.csv) · [Frozen rosters](development/stages.json)

The calculation gives the candidate the entire terminal-to-exit interval for free on every completed fix, and grants an instantaneous result on every v3 withdrawal. It charges prior solver failures in full. The median column gives the median of individual candidate/v3 ratios, and the summed column divides total candidate elapsed by total v3 elapsed. Both must be at most 0.500. These are optimistic allowances for work at these boundaries. Receiver startup, the numerical grid, and any other work upstream of the terminal keep their costs.

| Enrolled panel | Complete / withheld / solver failed | Original elapsed s | Complete fixes, terminal to exit s | Original elapsed with both shortcuts granted for free, median / summed |
|---|---:|---:|---:|---:|
| First 4 | 4 / 0 / 0 | 403.36 | 11.93 | 0.969 / 0.970 |
| First 16 | 15 / 0 / 1 | 1,715.13 | 47.11 | 0.973 / 0.973 |
| Historical 55 | 52 / 1 / 2 | 5,638.25 | 150.61 | 0.973 / 0.973 |

## If acquisition sustained the measured two-member rates

Keep the frozen model's **26.105 s** dense numerical solve, scale each instrumented recording's numerical cost using its original solve clock, and charge **2.063 s** shared overhead per completed run. Apply the two independently measured compressed acquisition rates separately across each roster. The faster prefix still misses both gates on the first four even if the post-terminal work is free. The slower prefix misses both by more. This comparison gives a reason to prioritize the dense solver and sustained verified acquisition over further publication tuning once the current renderer is timed. [Two-member physical measurements](physical-short-prefetch.md) · [Model and scope](regional-dense-pair.md)

| Enrolled panel | Assumed sustained MB/s | Original tails, median / summed | Free post-terminal work and withdrawals, median / summed |
|---|---:|---:|---:|
| First 4 | 224.74 | 0.598 / 0.566 | 0.565 / 0.536 |
| First 4 | 248.29 | 0.564 / 0.531 | 0.532 / 0.502 |
| First 16 | 224.74 | 0.558 / 0.559 | 0.528 / 0.531 |
| First 16 | 248.29 | 0.522 / 0.528 | 0.491 / 0.501 |

The calculation preserves the original matched-process denominators and v3 outcomes for every recording. A future candidate can change its outcome distribution and the work it induces in the graph and solver. Only an actual paired run can establish the resulting fix rate, position accuracy and elapsed ratios. The raw six-member throughput trial stopped before reading or staging because the shared bulk volume was busy. [Six-member resource census](long-physical-prefetch-admission.md)

Reproduce from the checkout root with `PYTHONPATH=.:src python reports/ALGO08/v3/panel_tail_ceiling.py`. The program checks the published source hashes, the full 55 stage splits and the roster mapping before evaluating the counterfactual. [Calculation](panel_tail_ceiling.py) · [Component tests](../../../tests/pipeline_eval/test_panel_tail_ceiling.py)
