# Native probe availability cross

The experiment independently removes each wide-only positive and restores each capture-only positive. The four cells retain the same hardware-probe roster, including negatives. A jointly positive probe always keeps its complete wide candidate list and winner. A separately replayed stock capture-era input keeps its own jointly positive winners. Both detector exports are needed to define the treatments, so this is an oracle diagnostic.

| Recording | Joint positive | Wide-only positive | Capture-only positive | Joint negative | Exact joined probes |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS29-0082 | 1,634 | 429 | 234 | 7,439 | 9,736 |
| DS26-0237 | 3,417 | 591 | 323 | 9,201 | 13,532 |

Every joined receiver/visit/probe had identical noncandidate metadata, including the hardware counter, sample interval, channel, and actual RF. Capture and delivery clocks, closing sample counter and exclusions also matched. Both stored wide exports were byte-identical for each recording. The two fresh stock controls use the exact native archive bytes. [Prespecified protocol](PROTOCOL.md) · [Input roster and lane counts](join-audit.json) · [Locked receiver and native inputs](plan.json)

## Position and conditional RF

On DS29-0082, restoring capture-only positives improved both calibration arms. Removing wide-only positives by itself slightly increased both errors. When the two changes were applied together, the error fell by 0.678 km at `c = 0` and 0.462 km with fitted `c`. That closed 35% and 25% of the original gap to capture-era respectively. With the exact capture-era positive roster and unchanged shared wide winners, 1.243 and 1.368 km of error gap remained.

On DS26-0237, restoring capture-only positives alone produced the most accurate replay. Removing wide-only positives increased both errors whether or not the capture-only positives were restored. Removing wide-only positives on DS29-0082 helped only when the capture-only positives had also been restored. The interaction between the two changes therefore differs across the two recordings. [Paired contrasts](effects.csv)

Each paired value is `c = 0` / fitted `c`. All 10 services published both arms.

| Recording | Condition | Error (km) | Conditional RF RMS (Hz) | Positive probes | Prepared tracks |
| --- | --- | ---: | ---: | ---: | ---: |
| DS29-0082 | Stock wide | 2.489 / 2.346 | 84.42 / 84.25 | 2,063 | 71 |
| DS29-0082 | Remove | 2.512 / 2.379 | 80.43 / 80.34 | 1,634 | 56 |
| DS29-0082 | Restore | 2.177 / 2.028 | 80.09 / 80.00 | 2,297 | 75 |
| DS29-0082 | Both | 1.811 / 1.884 | 86.52 / 86.52 | 1,868 | 60 |
| DS29-0082 | Stock capture | 0.568 / 0.516 | 97.00 / 96.68 | 1,868 | 61 |
| DS26-0237 | Stock wide | 0.382 / 0.323 | 92.54 / 92.43 | 4,008 | 110 |
| DS26-0237 | Remove | 0.497 / 0.346 | 87.44 / 87.37 | 3,417 | 95 |
| DS26-0237 | Restore | 0.303 / 0.173 | 92.54 / 92.47 | 4,331 | 113 |
| DS26-0237 | Both | 0.430 / 0.339 | 89.07 / 88.99 | 3,740 | 104 |
| DS26-0237 | Stock capture | 0.353 / 0.262 | 80.67 / 80.61 | 3,740 | 103 |

The closest DS29-0082 estimate had the highest conditional RF RMS. The lowest RF RMS came from the restore-only cell, whose two position errors both exceeded 2 km. Conditional RF evaluates the measurements chosen by each fit. Every cell prepared three initial branches and reached publication without a cavity proposal. [Coordinates and errors](scores.csv) · [Graph support and frequency scores](graph-support.csv)

## Execution and evidence

All 10 services used the same installed phase-release package, original offer and causal TLE history. Each ran on CPU 6 or 7 with one numerical thread, the enforced 512 MiB cap, no swap and 210 s service limit. Post-GLRT CPU was 24.22–55.06 s per service, with worker wall time 24.35–55.80 s and maximum cgroup charge 443.1 MiB. All services completed and recorded zero OOM and swap events. These costs start at stored native factors. [Resource receipts](resources.csv) · [Prediction lock](prediction-lock.json)

The setup initially stopped on an inventory discrepancy before staging any fits. The historical whole-band package differs from the installed phase-release package in three recorded files. The completed replay used one consistent phase release across all cells and the capture control. Both fresh wide controls reproduced the historical wide coordinates and RF RMS exactly in both arms. The scorer also rechecked every staged treatment row. [Historical parity](archive-parity.csv) · [Independent treatment audit](treatment-audit.json) · [Score lock](score-lock.json)

- Remove-only figures. [`c = 0`](charts/c0/probe-support-remove.png) · [Fitted `c`](charts/fitted_c/probe-support-remove.png)
- Restore-only figures. [`c = 0`](charts/c0/probe-support-restore.png) · [Fitted `c`](charts/fitted_c/probe-support-restore.png)
- Combined-change figures. [`c = 0`](charts/c0/probe-support-both.png) · [Fitted `c`](charts/fitted_c/probe-support-both.png)
