# Single-core ARM saved-IQ result on 192.168.1.15

Completed 103/104 physical cases in 850.0 seconds. Complete: **False**. Scientific case failures: **0**.

Independent explicit decision-equality audit: **309/309** comparisons pass.

Incomplete real-data strata excluded from rate tables: [{"rate_hz": 10000000, "completed": 7, "planned": 8}].

These are measurements on the physical Cortex-A9, pinned to CPU0, with RX0 and RX1 processed sequentially. Input is stored IQ at its native rate. No RF, radio controls, firmware or production services were used or changed. The target SD card was formatted with user authorization and mounted at /mnt/glrtbench.

A = packed input/FP64 FFTW; B = packed/FP32; C = natural-stride/FP64; D = natural-stride/FP32. All share the same scientific flags and six-window, one-confirmation-per-receiver profile. This is not the eleven-probe full scanner or a deployed production-service benchmark.

## Real-data CPU result

All times below are mean CPU milliseconds per complete dual-receiver visit. Each case contributes its median of five measured calls after one warmup. Speedups are ratios of paired summed medians, not multiplied stage gains.

| MS/s | Visits | A FP64 packed | B FP32 packed | C FP64 strided | D FP32 strided | D speedup |
|---:|---:|---:|---:|---:|---:|---:|
| 2.5 | 32 | 124.89 | 119.72 | 113.72 | 108.06 | 1.156x |
| 5 | 32 | 228.34 | 225.24 | 206.14 | 202.10 | 1.130x |
| 7.5 | 8 | 352.88 | 345.64 | 320.50 | 310.34 | 1.137x |

At the primary 2.5-MS/s rate, FP32 alone gives 1.043x, strided ingress alone 1.098x, and the combination 1.156x (13.47% less CPU). No promotion is claimed: the 1.30x performance requirement or complete-run scientific gate is not met. No 10x claim is supported.

Incremental FP32 gain after natural-stride ingress (C CPU / D CPU): 2.5 MS/s: 1.052x; 5 MS/s: 1.020x; 7.5 MS/s: 1.033x.

The explicitly equal-visit 2.5/5-MS/s aggregate (32 visits each) gives A/B 1.024x, A/C 1.104x, A/D 1.139x and C/D 1.031x. The primary result remains 2.5 MS/s; no unequal four-rate aggregate is used.

## Scientific comparison

| MS/s | Baseline positive receivers | D retained | D lost | D added | D identity failures |
|---:|---:|---:|---:|---:|---:|
| 2.5 | 21 | 21 | 0 | 0 | 0 |
| 5 | 17 | 17 | 0 | 0 | 0 |
| 7.5 | 2 | 2 | 0 | 0 | 0 |

Controls completed: 24/24; required truth checks passed: 192/192. Checks include pilot identity and window, noise/tone rejection, deterministic repetition, rank/window/candidate agreement and 2-us circular timing / 8-kHz physical-CFO association. The raw per-case assessments retain score drift and all B/C/D comparisons.

The real cohort is exposed development data without independent physical truth. A zero-positive rate has no real sensitivity denominator. Small constructed sets do not establish rare false-alarm rates or broad multisignal sensitivity.

A separate receipt-only check of every serialized non-timing field across repetitions passed 412/412 method/case records. See full-determinism-audit.json; this is additional reporting, not a retuned gate.

SOL review found that the inherited identity predicate did not itself reject a margin-threshold decision flip. Run 01 preserved its original evaluator; run 02 used the explicit decision gate. This report also independently checks explicit activity equality from every raw method/case result (decision-equality-audit.json). Any failure blocks scientific promotion even if the original case-level identity predicate passed. No threshold was changed.

## Observed wall time

These values use all five timed repetitions, not only case medians. p95 is the nearest-rank empirical percentile. Maxima and percentiles are descriptive only. Single-RX wall values are the sum of packing_wall_ms and detector_wall_ms, not a separately timed whole-RX service boundary. wall-tails.json contains A/B/C/D pair and separate RX0/RX1 p95/max and >100/>120-ms counts for each complete real cohort.

| MS/s | D pair p95 ms | D pair max ms | D single-RX max ms | Pair calls >120 ms |
|---:|---:|---:|---:|---:|
| 2.5 | 113.07 | 117.36 | 60.38 | 0/160 |
| 5 | 211.54 | 214.49 | 109.59 | 160/160 |
| 7.5 | 312.59 | 313.18 | 169.05 | 40/40 |

## Next optimization target

Primary-rate D stage CPU, per dual-RX visit:

| Stage | Mean ms |
|---|---:|
| rank | 37.92 |
| coarse | 20.77 |
| fine | 18.31 |
| fractional | 17.17 |
| conversion | 4.03 |
| nuisance | 4.52 |

Stage timers are diagnostic and potentially inclusive; do not sum them into a new total. The next experiment should target the measured rank/acquisition and fractional-sampling work, or causal fresh confirmation that avoids acquisition. Swapping FFT precision alone does not remove these costs.

## Reproduction and limits

See ../RUNBOOK.md, ../PROTOCOL.md and the immutable build-snapshot.tar.gz. Host ASan/UBSan passed 24 controls through four variants; eleven component tests passed including the post-review threshold-crossing regressions. High-rate admission required three scratch-capacity fixes, tested before ARM execution. Those changes are isolated research snapshots, not production edits.

Timed service includes packing/conversion and the complete native detector on resident IQ. File transfer/read, FFT planning, initialization and JSON serialization are outside that boundary. Setup timers and whole-session elapsed time are retained separately. No per-case transfer timer, fault count or complete RSS trace was collected. One external process-status sample confirms Threads=1, CPU0 and an 18,616-KiB RSS/HWM; it is not a peak-memory bound across all cases. CPU frequency was not exposed through the target's cpufreq sysfs path. There was no clock-policy change.

Persistent target directory: `/mnt/glrtbench/leo-static-glrt.4jwvdm`. Raw target receipts are also copied here. Input and executable hashes were checked on the target, inputs before and after each case, and binaries before and after the run. run-lock.json binds evaluator and build hashes; completion.json records truncation/failure status.
