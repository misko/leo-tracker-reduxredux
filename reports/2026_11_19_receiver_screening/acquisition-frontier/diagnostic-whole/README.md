# Full-IQ differential scout on two development recordings

The qualified native FFTW scout reduced error on both development recordings, with improvements of **87–290 m** across the two calibration arms. DS29-0082 still had **2.296 km zero-calibration error and 2.055 km fitted-calibration error** against original v5 at 0.567 and 0.517 km. On the two independent held recordings, stock wide had lower error in both arms. Use the independent held and development panels alongside the pooled view. All four recordings came from one roof. [Zero-calibration charts](charts/c0/modifications.pdf) · [Fitted-calibration charts](charts/fitted_c/modifications.pdf) · [Pooled scores](pooled-scores.csv)

## Matched position results

Each cell gives `c = 0` / fitted `c` in kilometers. All eight candidate calibration arms and all eight stock calibration arms published. Original v5 no-repair appears in the table. The charts and score ledger also include all three other original capture-era policies. [Diagnostic prediction seal](prediction-lock.json) · [Cross-study identity audit](pooled-source-authority.json) · [All four original v5 options](pooled-scores.csv)

| Cohort and recording | Original v5 no-repair | Stock wide | FFTW scout + hinted wide |
| --- | ---: | ---: | ---: |
| Development DS26-0237 | 0.362 / 0.271 | 0.382 / 0.323 | 0.295 / 0.221 |
| Development DS29-0082 | 0.567 / 0.517 | 2.489 / 2.346 | 2.296 / 2.055 |
| Manifest-selected DS26-0168 | 1.515 / 1.551 | 0.805 / 0.796 | 1.724 / 1.722 |
| Manifest-selected DS29-0604 | 0.982 / 1.041 | 0.735 / 0.734 | 0.760 / 0.775 |

The pool matched exact FFTW and hinted GLRT binaries, the complete scientific source closure, and compact phase-release bytes. Each control uses the same stock 21-bin binary and decoder source. Within each recording, complete raw authority, native clock and exclusions, noncandidate probe metadata, original offered tile and catalogue match. The two development recordings contributed selected windows to earlier scout testing. Each new diagnostic ran the scout on every valid window, using current-window IQ and the same native wide search and compact solver. [Diagnostic protocol](PROTOCOL.md) · [Held selection](../whole-replay/selection.json) · [Pooling protocol](POOLED.md) · [Full native FFTW qualification](../differential-runtime/prediction-lock.json)

| Group | Median stock error, zero / fitted (km) | Median scout error, zero / fitted (km) | Within 5% of v5, stock → scout, zero / fitted | Within 10%, stock → scout, zero / fitted |
| --- | ---: | ---: | ---: | ---: |
| Two development recordings | 1.435 / 1.334 | 1.295 / 1.138 | 0 → 1 / 0 → 1 | 1 → 1 / 0 → 1 |
| Two manifest-selected held | 0.770 / 0.765 | 1.242 / 1.248 | 2 → 1 / 2 → 1 | 2 → 1 / 2 → 1 |
| All four | 0.770 / 0.765 | 1.242 / 1.248 | 2 → 2 / 2 → 2 | 3 → 2 / 2 → 2 |

## Physical acquisition changes

A positive visit contains a passing GLRT candidate on at least one receiver. A retained stock gate has an identical emitted passing candidate payload after removing its ordinal rank. DS26-0237 preserved its two invalid visits and DS29-0082 preserved its 1,904 invalid visits. Measured detector calls covered every valid visit and both receivers in both services. [Visit coverage](visit-coverage.json) · [Per-visit hashes, gate counts, and timing](visits.jsonl.gz) · [Per-probe audit](probe-audit.json)

| Recording | Valid dual visits | Positive visits, stock → scout | New / lost positive visits | New / lost positive receiver probes | Retained stock passing payloads |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0237 | 6,766 | 2,786 → 2,990 | 212 / 8 | 461 / 16 | 17,253 / 17,344 |
| DS29-0082 | 4,868 | 1,603 → 1,783 | 190 / 10 | 346 / 24 | 8,379 / 8,472 |

Within the same scout result, fitting `c` changed position error by −0.074 km on DS26 and −0.241 km on DS29. Conditional RF RMS changed by −0.073 and −0.304 Hz, and the conditional objectives changed by −1.377 and −1.293. Across detectors, DS26 conditional RMS fell by 0.672/0.634 Hz and DS29 conditional RMS rose by 4.682/4.552 Hz. The detectors select different observations, so these RF numbers describe their respective fits. [Calibration and conditional RF values](scores.csv)

## Detector and service measurements

The 20 ms count measures the complete dual-receiver detector call, including the scout where present. The scout consumed 41.27 and 29.47 CPU s across the two lanes on DS26 and DS29. Whole-service elapsed includes raw processing, handoff and phase-release positioning. The archive used separately measured load and another elapsed cap. The cgroup capped each new service at 512 MiB with zero swap and recorded a 512 MiB peak for both. [Timing by phase and call percentiles](deadlines.csv) · [Service receipts](resources.json) · [Measured timing plots](resources.pdf)

| Recording and branch | Wall calls ≤20 ms | Call wall P50 / P95 (ms) | Raw / position wall (s) | Pipeline wall / CPU (s) | Service cap |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0237 stock | 6,397 / 6,766 | 15.36 / 20.47 | 79.03 / 53.22 | 133.07 / 183.51 | 360 s |
| DS26-0237 scout | 1 / 6,766 | 32.46 / 64.24 | 154.46 / 95.52 | 250.95 / 353.37 | 450 s |
| DS29-0082 stock | 38 / 4,868 | 26.00 / 35.05 | 99.92 / 41.13 | 142.59 / 207.94 | 360 s |
| DS29-0082 scout | 0 / 4,868 | 32.21 / 42.11 | 111.27 / 42.39 | 154.43 / 237.72 | 450 s |

The acquired positive coverage improved on both development recordings. The measured independent holdout and full-call wall results favor retaining the stock wide default on this evidence. [Held FFTW reference and source artifacts](../whole-fftw/figures.json) · [Complete pooled distribution](pooled-summary.json)

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.diagnostic_whole_results score
.venv/bin/pytest -q tests/pipeline_eval/test_diagnostic_whole.py
```
