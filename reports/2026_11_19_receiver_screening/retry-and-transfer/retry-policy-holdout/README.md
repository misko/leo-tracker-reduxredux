# Causal retry policies on an independent upper-edge recording

On DS26-0162, the frozen 0.8-second policy used **27.7% fewer retries** and retained **470 of 530 rescues (88.7%)**. At the same number of retries on every receiver and RF, the hash control retained 403 rescues and located the roof **251 m closer at `c = 0` and 288 m closer with fitted `c`**. The two-second policy saved more attempts and retained 391 rescues. [Prospective retry comparison](stage.pdf) · [Geographic scores](scores.csv)

DS26-0162 is the prospective recording for the predeclared 0.8-second policy. After two consecutive evaluated misses at the same receiver and actual RF, it waits 0.8 seconds from the latest evaluated miss. A success resets the streak. Skipped opportunities leave state unchanged. The other policies are full conditional retry, primary-only, the existing two-second pause after one failed retry, and a hash control with the same attempt count as the 0.8-second policy at every physical receiver and RF. [Protocol](PROTOCOL.md) · [Frozen implementations](policy-lock.json)

## Signed waveform and counterfactual

DS26-0162 has 6,772 scheduled visits and 59 original invalid visits. The replay streamed and authenticated the 106 compressed chunks. It recomputed both 12-anchor primaries on all 3,153 valid visits with any final positive, including visits in which a rescue made the original final result dual positive. A double-negative final result identifies a visit where both receivers used their primary outputs. The original factors supply those 3,560 paired primary results. Eight fresh waveform witnesses span all four final gate patterns. A separately measured 20-visit assay cross-checks the new primary stream and the retained double-negative factors. [Waveform inputs](source-lock.json) · [Fresh witness outputs](receipts/smoke.json) · [Complete factor and timing audit](resources.json)

The solver assembly preserves the original capture support and clocks and substitutes the failed receiver's actual 22-anchor candidate records on chosen opportunities. An unsuccessful retry still replaces the complete failed-lane candidate list and counts against the budget. [Decisions and factor assembly](receipts/schedule.json) · [Authenticated worker receipts](prediction-lock.json)

| Policy | Attempts | Unsuccessful attempts | Rescues | Gated receiver-probes |
| --- | ---: | ---: | ---: | ---: |
| Full conditional | 1,319 | 789 | 530 | 5,517 |
| Primary only | 0 | 0 | 0 | 4,987 |
| Two seconds after one failure | 757 | 366 | 391 | 5,378 |
| 0.8 seconds after two failures | 953 | 483 | 470 | 5,457 |
| Physical-key hash control | 953 | 550 | 403 | 5,390 |

The original detector retried receiver 0 on 627 visits and receiver 1 on 692. The conservative policy and its matched control each used 498 and 455 retries on those receivers. The streamed primary replay took **425.1 s wall** and **1,049.2 worker CPU seconds** on four capped workers. Complete primary detector work on the 3,153 selected visits took **1,025.8 CPU seconds**, including 374.9 seconds in the prepared coarse grids. Median selected-visit CPU was 311 ms. The compact services timed the assembled factors separately. [Host resources and witness counts](resources.json)

## Geographic and frequency results

All five compact services ran fresh on complete native factors and returned both calibration arms under the 512 MiB cap. Both timers were within 10% of all four original v5 reference roles in both arms. Primary-only exceeded all four reference errors by more than 10%. The matched hash draw returned the smallest errors at both calibration settings even though the two-failure policy retained 67 more rescues at the same attempt counts. [All four v5 roles](v5-controls.csv) · [Zero-calibration chart](charts/c0/modifications.pdf) · [Fitted-calibration chart](charts/fitted_c/modifications.pdf)

| Policy | Geographic error `c = 0` / fitted `c` (km) | Conditional RF RMS zero / fitted (Hz) | Compact wall / CPU (s) |
| --- | ---: | ---: | ---: |
| Full conditional | 0.402 / 0.417 | 47.47 / 47.46 | 100.81 / 86.23 |
| Primary only | 0.559 / 0.579 | 47.41 / 47.38 | 80.63 / 70.24 |
| Two seconds after one failure | 0.425 / 0.405 | 46.53 / 46.46 | 88.17 / 76.17 |
| 0.8 seconds after two failures | 0.428 / 0.435 | 46.74 / 46.73 | 100.21 / 83.78 |
| Physical-key hash control | 0.177 / 0.147 | 46.18 / 46.13 | 72.87 / 70.60 |

Fitted `c` changed the 0.8-second policy's conditional RF RMS by −0.009 Hz and its geographic error by +7 m. Its frequency objective moved from 37,540.97 to 37,524.24. Both calibration arms used the same factors, causal catalogue, original offer, priors, and search budgets. [Paired scores and objectives](scores.csv) · [Compact service receipts](prediction-lock.json)

## Retrospective detector counts

The two earlier recordings provide support comparisons on independently completed primary and conditional streams. The sibling study reports their retrospective compact positions separately. [Retrospective counts](retrospective-counts.csv) · [Retrospective position scores](../retry-policy-retrospective/scores.csv)

| Recording | Full opportunities / rescues | Two-second attempts / rescues | 0.8-second attempts / rescues | Same-count hash rescues |
| --- | ---: | ---: | ---: | ---: |
| DS26-0237 | 1,592 / 448 | 840 / 315 | 1,063 / 392 | 303 |
| DS29-0082 | 1,010 / 228 | 530 / 164 | 650 / 193 | 147 |

## Reproduce the holdout

The resolved scratch workspace is `/srv/bulk/leo-dev/retry-policy-holdout-20261119-B`. Use the same installed producer and compact release pinned in the source lock. The waveform module freezes source bindings and supports the `preflight` and `run` commands over an explicit scratch path. The results module uses `freeze-policy`, `prepare`, `position`, and `publish` in that order around the waveform replay. The report stores the compressed worker output, independently checked witnesses, complete factor streams, schedule, worker requests and terminal receipts. [Waveform command](../../../../tools/pipeline_eval/qualification/retry_policy_holdout.py) · [Results command](../../../../tools/pipeline_eval/qualification/retry_policy_holdout_results.py) · [Component tests](../../../../tests/pipeline_eval/test_retry_policy_holdout.py)
