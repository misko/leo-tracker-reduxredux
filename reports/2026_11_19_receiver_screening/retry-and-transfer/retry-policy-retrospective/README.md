# Retrospective position fits for the frozen two-failure retry policy

The 0.8 s retry timer retained **89 more original rescues on DS26-0237** and **46 more on DS29-0082** than the hash control at identical attempt counts by physical receiver and RF. Their positions were within 3 m of each other on DS26-0237. On DS29-0082, the timer reduced the geographic error against the hash by 120 m with `c = 0` and 274 m with fitted `c`. All four independent compact services published both calibration arms. [Counts](retry-counts.csv) · [Position charts](charts/README.md) · [Exact scores](scores.csv)

## Matched retry budgets

| Recording | Full conditional attempts / rescues | Matched attempts | Timer rescues | Hash rescues |
| --- | ---: | ---: | ---: | ---: |
| DS26-0237, lower edge | 1,592 / 448 | 1,063 | 392 | 303 |
| DS29-0082, upper edge | 1,010 / 228 | 650 | 193 | 147 |

The same policy source and hash rule were frozen for the independent DS26-0162 study. Each timer runs on the recorded monotonic clock and uses the most recent evaluated outcome for the physical receiver and RF key. The retrospective comparison uses existing complete primary and conditional candidate streams. Each input preserves the genuine retry candidate list on a selected visit, including visits that failed its gate. [Frozen selector](holdout-policy-lock.json) · [Physical choices and requests](selection-lock.json) · [Independent DS26-0162 study](../retry-policy-holdout/README.md)

## Position error in kilometres

| Recording | Calibration | Timer | Hash control | Full conditional |
| --- | --- | ---: | ---: | ---: |
| DS26-0237 | `c = 0` | 0.455 | 0.454 | 0.353 |
| DS26-0237 | Fitted `c` | 0.370 | 0.368 | 0.262 |
| DS29-0082 | `c = 0` | 0.421 | 0.542 | 0.568 |
| DS29-0082 | Fitted `c` | 0.599 | 0.872 | 0.516 |

Both services per recording used the original 25 km offer, causal TLE catalogue, compact release, priors and search budget. The full-conditional comparisons use the independently sealed compact positions on the signed archive. We checked exact probe equality between the saved conditional replay and that archive. Each chart also includes the four original v5 roles, with values that coincide on the lower recording. [Zero-calibration chart](charts/c0/modifications.pdf) · [Fitted-calibration chart](charts/fitted_c/modifications.pdf) · [All four v5 roles](v5-controls.csv)

## Conditional frequency fit

| Recording | Calibration | Timer RMS (Hz) | Hash RMS (Hz) | Full conditional RMS (Hz) |
| --- | --- | ---: | ---: | ---: |
| DS26-0237 | `c = 0` | 80.204 | 80.661 | 80.670 |
| DS26-0237 | Fitted `c` | 80.157 | 80.600 | 80.608 |
| DS29-0082 | `c = 0` | 78.671 | 78.732 | 97.003 |
| DS29-0082 | Fitted `c` | 78.517 | 78.483 | 96.684 |

Fitted `c` lowered conditional RMS for each fixed policy and recording. Geographic error increased for both reduced-retry policies on DS29-0082. Each row of the score table also records its frequency score. [Full numerical scores](scores.csv)

## Execution and reproduction

Four separate compact services ran on CPUs 16 and 18 with ext4 scratch, one core per service, a 210 s runtime cap, 512 MiB memory and zero swap. Runtime was 41.75–80.27 s wall. Each service evaluated both calibration arms. The two recordings belong to the older detector evidence base. The narrower detector schedule is a saved-factor comparison on authenticated delivery times. [Terminal rows and service clocks](positions.jsonl.gz) · [Prediction seal](prediction-lock.json)

Run `tools.pipeline_eval.qualification.retry_policy_pair stage /var/tmp/<new-work>` and `run /var/tmp/<new-work>` with a new report output directory. `tools.pipeline_eval.qualification.retry_policy_pair_results --out <output>` regenerates the figures and scores from the sealed terminals. [Protocol](PROTOCOL.md) · [Score seal](score-lock.json)
