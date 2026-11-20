# Retry and transfer gallery

[Browse the benchmark](benchmark/index.html) · [Download the offline ZIP](benchmark/modification-charts.zip) · [Verify exported files](benchmark/pack-lock.json)

The pack contains **19 position comparisons** with both calibration views and **15 stage charts**. It includes 53 standalone PNGs, the PDF books, the measured and plotted values, and their hashes.

| Study | Position comparisons | Stage charts | Measurement boundary |
| --- | ---: | ---: | --- |
| [Batched waveform](batched-waveform/README.md) | 1 | 1 | Full screened lower-edge waveform through the batched detector and compact position |
| [Bearing transfer](bearing-transfer/README.md) | 4 | 1 | Containing and near-missing offers at eight measured StarLoc sites, with anonymous and author-ID fits |
| [Cadence waveform](cadence-waveform/README.md) | 0 | 1 | Original retries and online timers on four chronological saved-I/Q spans |
| [Cascade audit](cascade-audit/README.md) | 2 | 1 | Held fast and original compact endpoints, with a retrospective escalation ceiling and ranked budgets |
| [Fine CFO batching](fine-batch/README.md) | 0 | 1 | Paired complete detector timings and output agreement on 16 saved stereo visits |
| [First-gate panel](first-gate-panel/README.md) | 1 | 1 | Archived rank prefixes on 135 roof recordings and the matched compact position panel |
| [First-gate raw replay](first-gate-raw/README.md) | 0 | 1 | Full detector timings and exact rank-prefix projection on 16 saved stereo visits |
| [Multi-session position](multi-session/README.md) | 3 | 1 | Held spatial support across six recorded roof sessions and positions at two separate simulated sites |
| [Peer retry anchors](peer-retry/README.md) | 0 | 1 | Complementary eight-anchor retries on 40 outcome-blind visits and 20 known-rescue controls |
| [Portable fine CFO](portable-fine/README.md) | 0 | 1 | Host detector timings and numerical agreement for ARM builds under emulation |
| [Retry cadence](retry-cadence/README.md) | 3 | 1 | Retry opportunities and compact positions for miss and hit timers and the oracle control |
| [Retry evidence](retry-evidence/README.md) | 1 | 1 | Frozen primary-pilot rule and matched time-spread control through compact position |
| [Retry policy holdout](retry-policy-holdout/README.md) | 2 | 1 | Complete prospective DS26-0162 recording and the receiver-and-RF-matched hash control |
| [Retry policy retrospective](retry-policy-retrospective/README.md) | 1 | 0 | Fixed 0.8 s rule and matched hash control on two earlier recordings |
| [Retry anchor reuse](retry-reuse/README.md) | 0 | 1 | Two shared-anchor cache entries tested through the detector on six saved stereo visits |
| [Upper primary](upper-primary/README.md) | 1 | 1 | Recomputed DS29-0082 retry visits and complete primary-only factors through compact position |

The roof charts include all four original v5 options for the scheduled recordings. Transfer charts use their sealed offers and documented controls. The tables keep withheld, timed-out, failed, unavailable, and unmeasured outcomes in their scheduled denominators. Saved forced estimates appear as diagnostics. StarLoc phase and Doppler differences remove the fixed single-RF calibration term, leaving the fitted arm unavailable. The multi-session model’s within-frequency differences make its two calibration views coincide. [Calibration views](benchmark/charts/index.html) · [Position and frequency summaries](benchmark/summary.csv) · [Per-recording scores](benchmark/position-rf.csv) · [Plotted position values](benchmark/positions.csv)

The stage pages label their own sample, measurement boundary, and controls. The stage index links the plotted values and the source inventory records each receipt. [Stage figures and measurements](benchmark/stage-charts/README.md) · [Descriptor and receipt inventory](benchmark/study-evidence.json)

## Rebuild the benchmark

```sh
study=reports/2026_11_19_receiver_screening/retry-and-transfer
work=$(mktemp -d)
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark \
  --study "$study" --pack --out "$work/benchmark"
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check \
  "$work/benchmark/charts" --expected-charts 19
```
