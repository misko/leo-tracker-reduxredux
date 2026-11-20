# Position error for each receiver modification

Open the illustrated gallery for a separate cumulative distribution and recording-level dot plot for each change. The first ten charts cover the full-pipeline experiments on 127 DS26 and eight DS29 recordings. The remaining charts cover the follow-up modules, stopping points and earlier eight-scan prototypes. Both roof datasets were recorded at one installation. [Fitted-calibration gallery](figures/fitted_c/README.md) · [Zero-calibration gallery](figures/c0/README.md) · [Index, counts and percentiles](figures/README.md)

Each page uses the same recording IDs for its prototype and its four original v5 controls. The upper curve gives the fraction of all scheduled recordings that returned a fix within the distance on the horizontal axis. A withheld fix stays in the denominator. In the lower panel, each point is one estimate and each diamond is the median of that row. Regional receivers also show the best available estimate when they withheld a fix, where they recorded it. [Fitted PDF](figures/fitted_c/modifications.pdf) · [Zero-calibration PDF](figures/c0/modifications.pdf) · [Fitted source rows](figures/fitted_c/modifications.csv) · [Zero-calibration source rows](figures/c0/modifications.csv)

To view just the ten full-pipeline directions, open the original ten-page books. The batched GLRT, screened GLRT, streamed-IQ and bounded-IQ receiver charts use 80 scheduled windows per recording. All four withheld every roof fix at that budget. Their zero curves and empty dot rows are measured outcomes. [Ten directions, fitted calibration](../2026_11_18_pipeline_eval/figures/fitted_c/modifications.pdf) · [Ten directions, zero calibration](../2026_11_18_pipeline_eval/figures/c0/modifications.pdf)

## Does the receiver need all eight channels?

On the preselected six recordings, keeping alternate RF channels saved detector calls and degraded position accuracy. On DS29-0082, full v5 produced a 0.517 km error. Keeping odd channels gave 1.253 km and keeping even channels gave 15.324 km. The experiment kept both antennas, every visit to each selected channel and the original recording clock. Both schedules repeated tracking, satellite assignment and the paired v5 cavity fits. [Odd-channel chart](figures/fitted_c/glrt_odd_channels.png) · [Even-channel chart](figures/fitted_c/glrt_even_channels.png) · [Protocol](PROTOCOL.md)

| Receiver on the six timing recordings | Median error in km, zero / fitted | P95 error in km, zero / fitted | Within 5 km, fitted | Median conditional Doppler RMS in Hz, zero / fitted |
|---|---:|---:|---:|---:|
| Full numerical v5 | 0.818 / 0.832 | 1.309 / 1.395 | 6/6 | 78.443 / 78.409 |
| Full-channel v5 through the cavity fit | 0.818 / 0.832 | 1.309 / 1.395 | 6/6 | 78.443 / 78.409 |
| Odd channels through the cavity fit | 1.138 / 1.222 | 1.689 / 1.740 | 6/6 | 76.348 / 76.346 |
| Even channels through the cavity fit | 2.970 / 2.941 | 12.778 / 12.785 | 4/6 | 70.033 / 70.035 |
| All channels with compact orbital projection | 0.818 / 0.832 | 1.309 / 1.395 | 6/6 | 78.443 / 78.409 |

Each calibration pair used the same retained observations, candidate search, region, other priors and budget. Conditional RMS describes the frequencies retained by that particular run. The even-channel trial has the smallest RMS and the largest geographic errors. Each schedule returned coordinates in both arms on all six recordings. [Recording-level geographic and frequency errors](paired-errors.csv) · [Distributions by dataset and calibration](paired-distributions.csv)

The channel trials ran once each on the same CPU for a given recording. The six recordings covered all six possible orders. Compared with full-channel cavity v5 in that batch, median paired speedup was 2.14× for odd channels and 1.73× for even channels. Two full-file hashes identify the scheduling wrapper because a separate waveform-dispatch helper was added during the batch. DS29-0082 exercised both versions. A repeat with the final wrapper reproduced the same observations, track counts, coordinates and RMS for both schedules and both calibration arms. [Timing and input identities](paired-runtime.csv) · [Channel trial receipts](channel-pairs.jsonl.gz) · [Final-wrapper repeat](channel-repeat.jsonl.gz)

## Computing the same orbital quantities with fewer arrays

The original code prepares satellite position, velocity and derivative grids at every observation time before trying a receiver position. The compact module retains the original orbit knots and the interpolation indices, weights and rotations for the three phase offsets. One C loop interpolates those states and projects Doppler, elevation and Doppler's phase derivative onto the proposed receiver position. The worker feeds these arrays to the existing satellite assignment and v5 cavity fits. It uses all eight channels and receives the same single 25 km roof tile as original v5. Its position errors measure accuracy given that region. [Python worker](../../tools/pipeline_eval/variants/orbit_projector.py) · [C projection](../../tools/pipeline_eval/variants/orbit_projector.c)

The compact worker returned both positions on **135/135 recordings** on its first attempt. The six paired runs, the stress run and the other 128 confirmation runs cover the original roster exactly once. All 270 coordinates matched the stored cavity coordinates exactly. Compared with the final no-repair v5 positions, twelve DS26 coordinates moved by more than a metre in each arm. Three gave smaller errors and nine gave larger errors. All eight DS29 coordinates matched full v5 in both arms. [Fitted position chart](figures/fitted_c/orbit_projector.png) · [Zero-calibration chart](figures/c0/orbit_projector.png) · [Per-recording comparisons](roof-comparison.csv) · [Authenticated predictions](projector-roof.jsonl.gz)

The compact worker and original no-repair v5 had the same fix count, count within 5 km, median, P95 and worst error on both datasets, with either calibration setting. The final column describes the compact worker's frequency residuals. The comparison CSV distinguishes conditional RMS from the frequency metric in the original v5 reports. [All four v5 options and their distributions](roof-distributions.csv) · [Evidence hashes](projector-roof-receipt.json)

| Dataset and calibration | Fixes | Within 5 km | Median error (km) | P95 (km) | Worst (km) | Median conditional RMS (Hz) |
|---|---:|---:|---:|---:|---:|---:|
| DS26, zero | 127/127 | 125 | 0.988 | 3.084 | 7.269 | 70.751 |
| DS26, fitted | 127/127 | 125 | 0.999 | 3.126 | 6.858 | 70.722 |
| DS29, zero | 8/8 | 8 | 0.753 | 1.210 | 1.320 | 77.221 |
| DS29, fitted | 8/8 | 8 | 0.742 | 1.312 | 1.458 | 77.276 |

The first supervisor exited after all workers had saved their individual receipts. A second invocation authenticated the full roster and published the results from those receipts. Independent offline rescoring reproduced the two comparison CSVs byte for byte.

On DS26-0036 the prepared arrays fell from **400,482,816 to 24,604,512 bytes**, a 16.28× reduction for 1,524 satellites and 2,053 observation times. Output arrays and peak process memory are outside that count. The grid comparison evaluated three receiver positions and repeated the center. The largest absolute Doppler difference was 1.45 × 10⁻⁸ Hz or less. Across the six timed recordings, comparing the original layout's 128 bytes per satellite-time cell at the largest shape with the compact worker's maximum retained bytes gives ratios of 8.96× to 23.30×. [Development grid measurements](grid-development.json) · [Sizes per recording](paired-runtime.csv)

Across the six pairs, the median host time from stored detector output to both positions fell from **278.51 s for full numerical v5 to 114.74 s** for the compact cavity worker. That is a 2.43× ratio of medians. The median of the six paired speedups was **2.34×**, with a range of 1.58× to 2.72×. These times combine the earlier cavity cutoff and the compact orbital calculation. Each pair used one CPU, on a shared host, with order alternated across recordings. Each side ran once per recording. [Paired worker receipts](projector-pairs.jsonl.gz) · [Timing rows](paired-runtime.csv)

To isolate the projector's contribution, both workers stopped at the same cavity fit on the two original smoke recordings. Five alternating pairs per recording produced exactly the same coordinates, conditional RMS, track counts and observation counts in both workers. The projector was faster in every pair. Median paired speedup was **1.158× on DS26-0036** (range 1.070–1.306×) and **1.203× on DS29-0082** (range 1.132–1.236×). Worker wall time includes process startup and projector compilation. [All ten paired timings](cavity-projection-timing.csv) · [Twenty worker receipts](cavity-repeats.jsonl.gz)

On the separately chosen stress recording DS26-0066, the new module reproduced the original cavity checkpoint in both calibration arms. Its fitted error was 2.370 km against 1.218 km for full v5. With zero calibration it was 2.389 km against 1.244 km. The original post-cavity steps account for this difference. [Fitted stress chart](DS26-0066-fitted_c.png) · [Zero-calibration stress chart](DS26-0066-c0.png) · [Stress recording](stress.jsonl.gz) · [Original v5 stopping-point study](../2026_11_19_receiver_simplification/README.md)

The DS29-0082 execution trace counted 299 distinct Python functions in the full localization analysis, application and benchmark variant directories, 189 through the cavity cutoff and 195 with the compact module. Across the whole measured Python source these counts were 1,544, 1,404 and 1,410. The compact path adds a 55-line C kernel. The counts describe the code exercised on this recording. [Compact worker trace](DS29-projector-footprint.json.gz) · [Full v5 trace](../2026_11_19_receiver_simplification/footprint/v5_lean.json.gz) · [Cavity worker trace](../2026_11_19_receiver_simplification/footprint/v5_core.json.gz)

## Independent locations and embedded execution

Five regional position receivers ran the complete geographic transfer benchmark. All five withheld on every one of the 62 queries in which the correct region was absent. All five also withheld on all eleven StarLoc captures with the correct region present. The chart for each receiver shows the measured grid control, the reported fixes and the forced estimates separately for each source, including the forty simulated acquisitions and eight roof recordings. [Five geographic transfer charts](transfer-figures/README.md)

The transfer audit compared the two orbital calculations on 26,542,592 satellite-time cells across 118 nonempty queries. Half the queries offered the correct region. Half omitted it. Each query evaluated both zero phase and a per-satellite phase shift on the actual offered region centers. The largest discrepancies were 2.23 × 10⁻⁸ Hz in Doppler, 4.08 × 10⁻¹⁰ degrees in elevation and 1.44 × 10⁻⁹ Hz/s in the phase derivative. [All transfer queries, offered regions and discrepancies](transfer-grid.json.gz)

The audit included eight DS29 recordings, eleven StarLoc field captures at eight nearby site groups, and forty simulated acquisitions. Three Altrincham acquisitions had empty tracks in both offer conditions. StarLoc supplied processed single-frequency tracks. These comparisons test orbital arithmetic at the new locations. A measured end-to-end position distribution at a second installation remains open for the compact v5 worker. [Geographic data and prior receiver results](../2026_11_19_shared_receiver/README.md)

Cross-compilation for the Pluto Cortex-A9 and execution under QEMU reproduced the reference on eighteen synthetic satellite-time cells. The largest Doppler discrepancy was 7.28 × 10⁻¹¹ Hz. This verifies kernel execution with host-prepared inputs. Whole-receiver latency on the physical embedded system remains unmeasured. [ARM compiler flags and errors](arm-kernel.json)

## Detector time on recorded IQ

Each row below covers 16 decoded waveform windows, including invalid captures. The harness rotated six configurations over the same windows from segments 3 and 10. A skipped channel bypassed the detector call using the acquisition metadata. The full-channel detector produced 256 candidates on DS26-0036 and 176 on DS29-0082. On every called window, all candidate and receiver fields agreed with the full-channel original. All 54 captured native probe rows and the invalid-capture decisions matched the archive. [DS26 waveform receipt](DS26-0036-iq.json.gz) · [DS29 waveform receipt](DS29-0082-iq.json.gz)

| Recording | Original all / odd / even channels (s) | Accelerated all / odd / even channels (s) |
|---|---:|---:|
| DS26-0036 | 42.99 / 22.57 / 20.49 | 20.50 / 10.56 / 9.84 |
| DS29-0082 | 30.88 / 13.87 / 17.39 | 14.76 / 6.52 / 8.02 |

Across the two clips, combining the accelerated pilot grid and a four-channel schedule reduced measured detector time by 3.85× to 4.74×. The position charts above show the cost of discarding those channels. The detector timer starts after decoding and stops before tracking. The numerical worker timings start from stored detector output. The two tables measure different portions of the receiver. [Detector timing, call counts and candidate comparisons](iq-timing.csv)

## Reproduce

From the repository root, use the following command to render the charts from the shipped results. It works without the waveform archive. Use `--variant glrt_even_channels` to render a single modification, or `--panel matched135` for the ten full-pipeline directions.

```sh
.venv/bin/python -m tools.pipeline_eval figures --out /tmp/receiver-charts
.venv/bin/python -m tools.pipeline_eval figures --panel transfer124 --out /tmp/receiver-transfer-charts
.venv/bin/python -m tools.pipeline_eval.qualification.duty_results --out /tmp/receiver-tables
.venv/bin/python -m tools.pipeline_eval.qualification.projector_roof --score-only
```

On the corpus host the following commands rerun the paired workers, the orbit comparison and the ARM check. Select six distinct available CPUs for the timing experiment. The waveform replay uses the capture-era producer bound to each recording and a release build of the accelerated pilot filter. [Waveform harness](../../tools/pipeline_eval/qualification/duty_iq.py) · [Producer bindings](../../tools/pipeline_eval/qualification/full_v5_check.py)

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.duty_trials --study channels --cpus 12 13 14 15 16 17 --out /tmp/receiver-channel-pairs
.venv/bin/python -m tools.pipeline_eval.qualification.duty_trials --study projector --cpus 12 13 14 15 16 17 --out /tmp/receiver-projector-pairs
.venv/bin/python -m tools.pipeline_eval.qualification.cavity_pairs --cpus 18 19 --out /tmp/receiver-cavity-pairs
.venv/bin/python -m tools.pipeline_eval.qualification.cavity_pairs --cpus 18 19 --out /tmp/receiver-cavity-pairs --report /tmp/receiver-cavity-results
.venv/bin/python -m tools.pipeline_eval.qualification.projector_roof --cpus 8 9 10 11 12 13 14 15 16 17 --work /tmp/receiver-roof-work --out /tmp/receiver-roof
.venv/bin/python -m tools.pipeline_eval.qualification.projector_audit --panel development --out /tmp/receiver-grid.json
.venv/bin/python -m tools.pipeline_eval.qualification.projector_audit --panel transfer124 --jobs 4 --out /tmp/receiver-transfer.json.gz
.venv/bin/python -m tools.pipeline_eval.qualification.projector_arm --out /tmp/receiver-arm.json
```

To repeat the recorded-IQ timings on the corpus host, compile the same pilot filter and launch each case with its original producer on one available CPU. The case verifies the producer identity before opening the waveform windows.

```sh
.venv/bin/python - <<'PY'
import os
import subprocess
import sys
from pathlib import Path

from tools.pipeline_eval.__main__ import ROOT, THREAD_ENV
from tools.pipeline_eval.qualification.full_v5_check import PRODUCERS
from tools.pipeline_eval.variants.anchor_receiver import compile_filter

library = Path("/tmp/receiver-anchor.so")
compile_filter(library)
cpu = str(min(os.sched_getaffinity(0)))
for case, producer in PRODUCERS.items():
    subprocess.run(
        ["taskset", "-c", cpu, sys.executable, "-m", "tools.pipeline_eval.qualification.duty_iq",
         "--case", case, "--library", str(library), "--out", f"/tmp/{case}-iq.json.gz"],
        env={**os.environ, **THREAD_ENV, "PYTHONPATH": f"{producer.root}:{ROOT}"},
        check=True,
    )
PY
```
