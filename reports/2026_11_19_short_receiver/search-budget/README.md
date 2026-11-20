# How many starting assignments does v5 need?

All six recordings returned positions under all three policies. Refining only the first ranked assignment preserved the fitted median at 0.832 km and changed the 95th percentile from 1.395 to 1.385 km. It gave no consistent whole-worker speedup. Starting from a single unranked center seed made the worker 1.12× faster by paired median. Its DS26 P95 rose from 1.162 to 2.006 km. [Fitted charts](../../2026_11_19_position_atlas/short-receiver/fitted_c/modifications.pdf) · [Zero-calibration charts](../../2026_11_19_position_atlas/short-receiver/c0/modifications.pdf)

Each run started with the full recorded GLRT detections, the same causal orbital catalogue and the same supplied 25 km tile. Stock generated four calibration starts and four corner proposals, removed duplicates, and refined up to three ranked proposals. The first-ranked policy kept that search and refined just its first proposal. The single-seed policy retained the zero-calibration center start, ran the ordinary two discovery updates and refined the resulting proposal. All three used the zero-calibration branch gate for both final calibration fits and ran the same downstream v5 cavity solver. [Protocol](PROTOCOL.md) · [Implementation](../../../tools/pipeline_eval/variants/v5_search_budget.py)

| Six recordings | Median error in km, zero / fitted | P95 error in km, zero / fitted | Fitted errors within 10% of no-repair v5 or better | Median initial stage | Median full worker | Median paired worker speedup |
|---|---:|---:|---:|---:|---:|---:|
| Compact v5, up to three ranked starts | 0.818 / 0.832 | 1.309 / 1.395 | 6/6 | 25.8 s | 117.9 s | 1.00× |
| First ranked assignment | 0.818 / 0.832 | 1.301 / 1.385 | 6/6 | 20.6 s | 126.9 s | 0.93× |
| One center seed | 0.900 / 0.878 | 1.913 / 1.897 | 5/6 | 7.8 s | 111.8 s | 1.12× |

The two datasets contribute three recordings each. Runs used one pinned x86 core per recording with rotated method order on a shared host. Median paired speedup is computed from each recording's own stock and candidate times. On DS26-0122 one center seed moved the fitted position error from 0.747 to 2.136 km while lowering initial-stage time from 66.1 to 10.3 seconds. Median conditional frequency RMS on all six was 78.44 / 78.41 Hz for stock and the first-ranked policy, and 79.66 / 79.63 Hz for one seed. Both complete reference and candidate position distributions for each dataset are in the CSVs. [Per-recording decisions and time](per-recording.csv) · [Distributions by dataset and calibration](distributions.csv) · [Worker and input hashes](receipt.json)

## Original assignment checkpoints on 135 recordings

The authenticated original archives retain the fitted position of each competing initial assignment before conservative recovery. The first-ranked proposal won v5's zero-calibration branch selection on 97 of 127 DS26 recordings and seven of eight DS29 recordings. The other 31 selected a later-ranked proposal. Each row below describes those *initial* positions, with both calibration fits run on the same observations. [First-ranked positions](initial-checkpoints/v5_initial_rank1.jsonl.gz) · [Selected positions](initial-checkpoints/v5_initial_best3.jsonl.gz) · [Per-recording errors and RF residuals](initial-checkpoints/per-recording.csv)

| Initial checkpoint | DS26 median / P95 km | DS29 median / P95 km | DS26 / DS29 median RF RMS in Hz |
|---|---:|---:|---:|
| First-ranked, zero calibration | 1.417 / 4.412 | 1.745 / 3.199 | 164.59 / 172.76 |
| Best of three, zero calibration | 1.293 / 4.531 | 0.973 / 3.199 | 164.04 / 162.42 |
| First-ranked, fitted calibration | 1.416 / 4.442 | 1.737 / 3.292 | 164.59 / 172.77 |
| Best of three, fitted calibration | 1.297 / 4.542 | 0.968 / 3.292 | 164.06 / 162.44 |

The broad final-position experiment reran all 31 original branch disagreements through the downstream solver and included eight agreement controls. All 39 produced a fix. Fitted median / P95 improved from 0.917 / 4.568 km for no-repair v5 to 0.869 / 3.549 km for first-ranked. On individual recordings, 34 of 39 errors were within 10% of v5 or better in each calibration arm. Four worsened by more than 100 m. The remaining 96 had no fresh first-ranked final fit. This roster deliberately concentrates the cases in which assignment selection could matter. [39 matched recordings](../../2026_11_19_position_atlas/short-receiver/fitted_c/v5_first_ranked_broad-replayed.png) · [Full roster and measurement coverage](../../2026_11_19_position_atlas/short-receiver/fitted_c/v5_first_ranked_broad.png) · [Broad replay evidence](broad/README.md)

## Rebuild the figures and measurements

The figures read the saved predictions and require no IQ archive.

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel short-receiver --variant v5_first_ranked --out /tmp/first-ranked-charts
```

On the corpus host, use an empty local output directory for a new six-recording run. Each invocation runs its assigned two recordings and all three policies.

```sh
OUT=/tmp/v5-initial-budget
for cpu in 16 22 23; do
  .venv/bin/python -m tools.pipeline_eval.qualification.search_budget replay --cpu "$cpu" --out "$OUT" &
done
wait
.venv/bin/python -m tools.pipeline_eval.qualification.search_budget score --runs "$OUT" --report "$OUT/report"
```
