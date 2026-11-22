# Conditional residual scans on the frozen DS30 panel

The conditional build preserved **4/4 fixes** and published all eight required figures for each. Total elapsed time fell **821.81 → 495.68 s (1.66× speedup)** and total CPU time fell **659.87 → 378.76 s (1.74×)**. Three recordings improved in both position fits. The regression on DS30-0155 increased the panel's median position error in both calibration arms. The candidate failed the prespecified speed and accuracy gates. The 16-recording stage and the reserved blind panel were left unopened for this candidate. [Complete verified stage score](measurements/ds30-conditional-stage-inventory.json)

| Frozen order | Elapsed s, deployed → candidate | CPU s, deployed → candidate | Fitted error km, deployed → candidate |
|---|---:|---:|---:|
| DS30-0374 | 129.73 → 92.05 | 127.05 → 71.80 | 1.935 → 1.867 |
| DS30-0008 | 291.87 → 151.25 | 211.01 → 123.42 | 1.512 → 1.410 |
| DS30-0155 | 148.20 → 125.89 | 144.70 → 80.96 | 1.157 → 1.426 |
| DS30-0001 | 252.01 → 126.48 | 177.11 → 102.58 | 0.470 → 0.464 |

The median paired candidate/baseline elapsed ratio was **0.614** and the summed ratio was **0.603**. Each must be at most **0.500**. The measured shortfall was **84.77 seconds elapsed** across four cases. On CPU alone it was 48.83 seconds. Each recording ran serially on one low-priority pinned core on Gauss, alternating arm order. The OS reported different amounts of disk reading between arms. [Third pair](measurements/DS30-0155-conditional.json) · [Fourth pair](measurements/DS30-0001-conditional.json)

| Error across four recordings | Fixed-zero deployed → candidate | Fitted deployed → candidate |
|---|---:|---:|
| Median | 1.306 → 1.431 km | 1.334 → 1.418 km |
| P90 | 1.791 → 1.691 km | 1.808 → 1.735 km |

![Matched elapsed and CPU distributions and cumulative horizontal error on every assigned DS30 recording](conditional-ds30-stage.png)

## First recording in the frozen order

The first longer recording, DS30-0374, took **92.05 seconds** from sealed I/Q to all eight published images with the conditional receiver, versus **129.73 seconds** for deployed ALGO08v2. Both fits moved slightly closer to the scoring reference. The candidate ran first and incurred 16,255,104 filesystem input blocks. The baseline reported zero. Single-core CPU time was **71.80 versus 127.05 seconds**. Even with the disk-read imbalance set aside, the candidate would need another **8.27 seconds of compute savings** to halve baseline CPU time on this case. [Paired recording receipt](measurements/DS30-0374-conditional.json)

## Where the lead case spent time

| DS30-0374 elapsed interval | Deployed | Conditional |
|---|---:|---:|
| Launch to sealed detections | 89.81 s | 58.78 s |
| Detections to terminal result and grid | 34.49 s | 30.60 s |
| Terminal result to complete publication and exit | 5.43 s | 2.67 s |

The candidate requested 6,791 full scans and 2,497 primary-only scans. All 9,288 native calls consumed 29.63 CPU seconds. There were 29 changes in the selected factor on a radio lane. Fourteen selected residuals disappeared, six gave way to a primary factor, and nine selected primary factors disappeared. Skipping a residual can change the later continuation decision about a primary measurement. No new selected factors appeared at previously empty opportunities. [Individual changed measurements](measurements/DS30-0374-selected-changes.json.gz) · [Chronological scan rule](receiver-residual-prefix-192.md)

Both solvers returned 81 tracks and 20 associated satellites. The deployed solver associated 2,905 of 4,157 selected observations. The candidate associated 2,900 of 4,134. Fixed-zero / fitted position errors changed from **1.855 / 1.935 km to 1.742 / 1.867 km**. The corresponding terminal RF RMS changed from **101.54 / 101.52 Hz to 101.23 / 101.21 Hz**. The publication's separate diagnostic residual statistic increased from 142.38 / 128.88 Hz to 155.61 / 135.68 Hz. These statistics use different residual definitions. The fitted endpoint moved 89 m and the rendered content of all eight required figures changed. Position accuracy comes from the eligible station reference. [Scoring authority](../../2026_11_21_ds30_full/reference-audit.json)

## Second recording in the frozen order

DS30-0008 had 6,765 admitted stereo visits. Baseline ran first. Elapsed time fell **291.87 → 151.25 s (1.93×)** and CPU **211.01 → 123.42 s (1.71×)**. The OS counted 16,039,640 filesystem input blocks for baseline and 3,895,888 for the candidate. Halving baseline CPU would require another **17.92 CPU seconds**. Of 13,530 lane requests, 1,990 used the primary-only scan. Both endpoints moved closer to the reference, from **1.639 / 1.512 km to 1.572 / 1.410 km**, despite a small increase in terminal RF RMS from 129.70 / 129.66 Hz to 129.89 / 129.82 Hz. Both runs published all eight images. The candidate retained 6,992 selected measurements, removed 24 and added five. [Paired recording receipt](measurements/DS30-0008-conditional.json)

## Receiver changes on the regression case

DS30-0155 had 24 changed selections. Seventeen deployed primary factors and five residual factors disappeared. One primary and one residual appeared on previously empty opportunities. The published position degraded in both calibration fits. [DS30-0155 factor changes](measurements/DS30-0155-selected-changes.json.gz) · [DS30-0008 changes](measurements/DS30-0008-selected-changes.json.gz) · [DS30-0001 changes](measurements/DS30-0001-selected-changes.json.gz)

## Reproduction

Use the one-pair DS30 runner with the conditional build specification `65b664d49a5e91baf1fb593c19808f4cf32921d0c17ffe6145d61189570089c6`. Each case checks the independently assigned raw authority, region, per-case orbit archive and pins. Generate a changed-measurement table with `python -m reports.ALGO08.single-core-2x.selected_changes WORKSPACE/CASE/pair.json`. Plot verified timings and all-recording position-error curves with `python -m reports.ALGO08.single-core-2x.plot_ds30_stage STAGE.json OUTPUT.png`. Containing offers at a single physical station measure performance at that station. [Nested stage runner](ds30-stage.md) · [Missing-region evidence](receiver-residual-prefix-192.md#complete-physical-and-simulated-publications)
