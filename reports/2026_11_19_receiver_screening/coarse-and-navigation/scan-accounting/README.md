# Normal original receiver acquisition accounting

The normal receiver removes the signed-index validity prepass and collects each raw shard in one decoding and hashing pass. Across three full waveform outputs, median paired collector CPU savings ranged from **97.75 to 134.62 ms per recording**. Both collectors returned identical complete public payloads and native inputs. All three fresh compact fits exactly reproduced the previous coordinates and RF diagnostics in both calibration arms. [Collector chart](timing.pdf) · [Input and source plan](plan.json)

The existing scan determines capture validity during actual acquisition. The collector checks each terminal count against authenticated visit statuses and hashes the same shard bytes it consumes, including final fragments from interrupted workers. The normal entry point dropped 51 lines, its raw worker stayed at the same line count, and shared collection and verification gained 20 lines, for a net reduction of **31 lines**. The measured baseline and candidate source files and qualification harness are preserved with the plan. [Source snapshots](sources/) · [Protocol](PROTOCOL.md)

## Collection and original detector boundary

Each waveform ran in eight fresh CPU13 processes, four pairs alternating previous-first and candidate-first. The measurement starts inside the process at the normal collector call and ends after it returns. The read-only inputs were the same previously authenticated raw shards in both versions. Canonical equality covered raw worker exits and resources, complete chunk receipts, delivery clocks, every physical probe and candidate, and the flags for passing and rejected candidates. The same common assembler produced byte-identical native documents from both collectors. The scientific fields also matched the previous fresh native document for each recording. [24 measured collector receipts](receipts/collect.json) · [Full assembly audit](audit.json)

| Recording | Valid / scheduled visits | Physical probes | Candidates | Gate passes | Gate-positive probes |
|---|---:|---:|---:|---:|---:|
| DS26-0237 | 6,766 / 6,768 | 13,532 | 60,306 | 10,243 | 3,740 |
| DS29-0082 | 4,868 / 6,772 | 9,736 | 42,162 | 4,582 | 1,868 |
| DS29-0519 | 6,727 / 6,771 | 13,454 | 62,048 | 14,464 | 4,637 |

Every recording kept 106 authenticated chunks. Both collectors and the previous native outputs had the same physical exclusions, gate masks and candidate ordering. [Native and candidate parity](receipts/assembly.json)

| Recording | Previous / candidate median collector CPU (ms) | Paired median CPU saved (ms) | Paired median wall saved (ms) | Removed signed-index CPU (s) |
|---|---:|---:|---:|---:|
| DS26-0237 | 496.28 / 368.55 | 133.98 | 134.19 | 1.478 |
| DS29-0082 | 386.73 / 299.75 | 97.75 | 97.77 | 1.844 |
| DS29-0519 | 493.56 / 357.23 | 134.62 | 150.91 | 1.829 |

The removed prepass costs are CPU12 measurements under each installed producer. They sum the old per-worker index walks serially and reproduced the authenticated raw validity counts. The first index-only harness imported a reporting package absent from the capture runtime. The standalone signed-index runner completed under the installed runtime, and the initial logs are preserved. The prepass CPU and collector time sit outside the detector clock. The archived detector consumed about 2,478, 1,893 and 3,134 CPU seconds on the three recordings, respectively. [Per-pair timings](stage.csv) · [Index receipts](receipts/)

An independent normal raw smoke used the same 64 valid DS26-0237 visits in each checkout. Both emitted 147 folded grids, 128 physical probes and 569 candidates. Its visit payloads matched exactly after removing the two detector timing fields. The one-run launch wall times were 76.94 seconds before and 68.94 seconds after, while detector CPU was 41.45 and 47.74 seconds, respectively. [Normal raw smoke receipts](receipts/normal-smoke/)

## Compact position and calibration

One fresh compact fit per recording consumed the canonical native input shared by both collectors. Each fit preserved the matched causal catalogue and original 25 km offer. Both calibration arms shared observations, candidates, priors and search budget. The predictions were frozen before the survey scores were generated. [Prediction lock](prediction-lock.json) · [Score lock](score-lock.json) · [All four original v5 options](v5-controls.csv)

| Recording | Survey error, `c = 0` / fitted `c` (km) | Conditional RF RMS, zero / fitted (Hz) | Fresh compact wall (s) |
|---|---:|---:|---:|
| DS26-0237 | 0.3531 / 0.2619 | 80.670 / 80.608 | 73.22 |
| DS29-0082 | 0.5681 / 0.5158 | 97.003 / 96.684 | 38.37 |
| DS29-0519 | 0.2350 / 0.3059 | 76.458 / 76.524 | 76.85 |

The fresh and prior solutions agree in both arms for every recording. The fitted calibration lowered survey error on DS26-0237 and DS29-0082 and raised it on DS29-0519. The positions and frequency objectives are available per arm. [Per-arm scores](scores.csv) · [`c = 0` chart](charts/c0/modifications.pdf) · [Fitted `c` chart](charts/fitted_c/modifications.pdf)

## Reproduce

Use separate baseline and candidate checkouts corresponding to the archived source snapshots. The collectors require the saved waveform shard directories pinned in the plan. The timing and position commands accept an isolated report directory with a copy of this protocol. The compact jobs can use a free core through the `position-on` entry point. [Source snapshots](sources/) · [Qualification driver](../../../../tools/pipeline_eval/qualification/scan_accounting_trial.py)

```bash
.venv/bin/python -m tools.pipeline_eval.qualification.scan_accounting_trial freeze "$work" --baseline "$old" --candidate "$new" --cpu 13 --report "$out"
.venv/bin/python -m tools.pipeline_eval.qualification.scan_accounting_trial collect "$work" --report "$out"
.venv/bin/python -m tools.pipeline_eval.qualification.scan_accounting_trial assemble "$work" --report "$out"
for case in DS26-0237 DS29-0082 DS29-0519; do
  .venv/bin/python -m tools.pipeline_eval.qualification.scan_accounting_results position-on "$work" --case "$case" --cpu 13 --report "$out"
done
.venv/bin/python -m tools.pipeline_eval.qualification.scan_accounting_results publish "$work" --report "$out"
```
