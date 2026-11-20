# Two orbital phase fits on the compact v5 path

Each satellite can arrive slightly ahead of or behind its prediction from the causal orbital elements. V5 alternates between estimating the receiver position and evaluating the orbit again at an updated satellite time. This experiment reduces early fits from five to two, keeps all three candidate assignments in the initial search and retains the final signed correction and cavity checks. Both calibration arms use the same data, catalogue, region and budgets. [Protocol](PROTOCOL.md)

Six same-core pairs produced all six positions. The median stock-to-candidate time ratio was 1.27× for wall time and 1.24× for CPU time. Five of the six replays ran faster. Four of six fitted errors exceeded 110% of original v5. One timing supervisor ended before recording the elapsed time and CPU for DS26-0122. Repeating that candidate on the same core reproduced both coordinates, both RF residuals and all numerical decision counters exactly. Its repeated wall and CPU times were 214.02 and 212.98 seconds. [Per-recording measurements](per-recording.csv) · [Timing distributions](summary.json) · [Retained first attempt](interrupted-attempt.json)

| Dataset and calibration | Fixes, both | Median error, stock → two fits (km) | P95 error, stock → two fits (km) | Within 10% of no-repair v5 or better |
| --- | ---: | ---: | ---: | ---: |
| DS26, zero | 3/3 | 0.751 → 0.969 | 1.226 → 1.560 | 0/3 |
| DS26, fitted | 3/3 | 0.747 → 0.974 | 1.162 → 1.484 | 0/3 |
| DS29, zero | 3/3 | 0.885 → 1.109 | 1.276 → 1.299 | 2/3 |
| DS29, fitted | 3/3 | 0.917 → 1.042 | 1.404 → 1.416 | 2/3 |

The 21 separate confirmation recordings also exceeded the median-error tolerance. Their fitted median rose from 0.758 to 0.956 km. [Independent confirmation](../phase-confirmation/README.md)

## What changed during the initial fit

The archived original v5 numerical history exposes its position, c=0 objective and largest orbital-time update after each of the five fits for every candidate assignment. Selecting the smallest c=0 objective after the second fit selected the same assignment as the fifth fit on **135/135 recordings**. The fitted-calibration position for that assignment still moved a median **55 metres** and a P95 **671 metres** from fit two to fit five. The maximum movement was **2.12 km**. With zero calibration the median and P95 were **60 and 667 metres**. The archived fitted-calibration maximum satellite-time adjustment at fit two had a median of **0.644 s** across recordings. These are changes in the initial local east/north position and time estimates. The downstream results use geographic error against the receiver's reference location. [Per-recording initial fits](initial-phase-history.csv) · [Distributions and archive digest](initial-phase-history.json)

## Reproduction

The paired workers require the frozen native detector documents, causal orbit catalogues and v5 numerical source on the archive host. Pick two available CPUs. The first program alternates stock and candidate order. Seal the six completed pairs before running the geographic scorer. The separate archive audit reads the original numerical states and uses each archive's request and content digests.

```sh
runs=/srv/bulk/leo-dev/receiver-convergence-20261119/phase-budget
.venv/bin/python -m tools.pipeline_eval.qualification.phase_budget replay --lane 0 --cpu 22 --runs "$runs" &
.venv/bin/python -m tools.pipeline_eval.qualification.phase_budget replay --lane 1 --cpu 23 --runs "$runs" &
wait
.venv/bin/python -m tools.pipeline_eval.qualification.phase_budget seal --runs "$runs"
.venv/bin/python -m tools.pipeline_eval.qualification.phase_budget score
.venv/bin/python -m tools.pipeline_eval.qualification.phase_history_audit --jobs 2
```

The plotting command reads the published predictions and their digests. [Six timing pairs and 21 independently selected recordings](../../2026_11_19_position_atlas/convergence/index.html)
