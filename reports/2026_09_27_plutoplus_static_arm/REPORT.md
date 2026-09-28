# PLUTO+ single-core GLRT experiment

Latest: [40% headroom optimization](optimize/GOAL40.md) achieves 42.7–44.1%
CPU0 headroom during recorded-cadence capture contention, with all four
sample rates passing saved-file scientific qualification.

Follow-up: [simultaneous adaptive capture and GLRT benchmark](concurrent/REPORT.md)
measures capture contention, IRQ placement, actual-arrival pacing and SD writing.
The later [exact ARM optimization experiment](optimize/REPORT.md) reduces the
2.5-MS/s saved-IQ mean further to 93.40 ms with exact scientific parity.

Compiled and evaluated saved real IQ on 192.168.1.15, using CPU0 of its
Cortex-A9. Natural-stride input plus FP32 FFTW reduces CPU time by 13.5% at
2.5 MS/s. All four requested native rates execute and pass the comparison
gates. The initial 1.3x speedup objective was not met.

## Measured comparison

Mean CPU milliseconds per 120-ms dual-RX visit; RX0 and RX1 execute serially.
Each visit contributes the median of five calls following a warmup.
A is packed input/FP64 FFTW; B packed/FP32; C natural-stride/FP64;
D natural-stride/FP32. Scientific flags are identical across variants.

| Native MS/s | Real visits | A ms | B ms | C ms | D ms | A/D speedup | CPU reduction |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2.5 | 32 | 124.89 | 119.72 | 113.72 | 108.06 | 1.156x | 13.5% |
| 5 | 32 | 228.34 | 225.24 | 206.14 | 202.10 | 1.130x | 11.5% |
| 7.5 | 8 | 352.88 | 345.64 | 320.50 | 310.34 | 1.137x | 12.1% |
| 10 | 8 | 443.17 | 435.54 | 397.77 | 389.86 | 1.137x | 12.0% |

At 2.5 MS/s, ingress alone gives 1.098x and FP32 FFTW alone gives 1.043x.
Their combined gain is measured directly, not inferred by multiplication.
D's 160 measured 2.5-MS/s pair calls all finished under 120 ms: wall p95
113.07 ms, maximum 117.36 ms. Higher-rate pair calls exceeded 120 ms.

These measurements cover conversion, packing and native detection on resident
IQ. File I/O, transfer, FFT planning, startup and JSON serialization are
excluded. The profile ranks six windows and confirms one per receiver; this
is not a complete deployed scanner benchmark or a live real-time guarantee.

## Scientific evidence and review

D retained all baseline positive receivers: 21/21 at 2.5 MS/s, 17/17 at
5 MS/s and 2/2 at 7.5 MS/s, with no added positives. The eight 10-MS/s
real visits had no baseline positives, so real-data sensitivity at that rate
is unestablished. Rank, window, candidate, fractional status, physical
association and explicit decision-equality comparisons pass.

All 24 constructed controls across four rates passed: 192/192 receiver truth
checks across A/B/C/D. Host ASan/UBSan passed all 96 method/control executions;
eleven component tests pass. High-rate support required three scratch-capacity
fixes in isolated research source snapshots. Production sources and golden
fixtures are unchanged.

SOL reviewed the ARM implementation and identified a missing explicit
decision-equality predicate in the inherited assessor. It is now covered by
regression tests. Receipt-only audits confirm no decision flips in either run.
Terra independently checked raw timings, deterministic repetitions, cohort
completion and the final 10-MS/s result.

## Run provenance

The first bounded run completed 103/104 cases before its 850-second deadline.
It completed all controls and the entire 2.5/5/7.5-MS/s real cohorts. Its partial
10-MS/s cohort is excluded from this table. A separate 180-second run completed
all eight 10-MS/s real visits in 114.8 seconds with the same binaries and input
hashes; its controls are the already completed first-run controls. Original
completion records and evaluator/runner copies are preserved.

- [First run and controls](target_run_01/REPORT.md)
- [Complete 10-MS/s run](target_run_02_10m/REPORT.md)
- [Build and repeat instructions](RUNBOOK.md)
- [Runnable example at every rate](EXAMPLES.md)
- [Experimental protocol](PROTOCOL.md)

The authorized SD format is complete: ext2 mounted at /mnt/glrtbench,
approximately 238 GiB. Inputs and executables remain in
/mnt/glrtbench/leo-static-glrt.4jwvdm; the second run is in
/mnt/glrtbench/leo-static-glrt.9wnALf. No RF acquisition or radio control was
performed. The executables pin and verify CPU0 and use one FFTW thread.

## Next experiment

Prioritize the measured remaining work at 2.5 MS/s: ranking (37.92 ms),
coarse acquisition (20.77 ms), fine work (18.31 ms) and fractional work
(17.17 ms), per dual-RX visit in D. These diagnostic timers can overlap and
must not be summed. Optimize ranking/acquisition next, then evaluate causal
tracking with fresh confirmation to avoid repeated acquisition. Keep the
same four-rate controls and real-data comparison gates. Larger speedup claims
require another measurement; changing FFT precision alone is insufficient.
