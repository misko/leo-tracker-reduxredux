# Full-search ARM optimization with FFTW double precision

Replacing the built-in FP64 FFT backend with the device's single-threaded
FFTW double-precision backend reduces runtime without dropping windows,
frames, candidates, or frequency bins. The search and GLRT definitions remain
the same. FFTW uses `FFTW_ESTIMATE`; plan creation remains workspace setup.
This is numerical equivalence within documented tolerances, not bit identity.

The implementation is report-local. `fftw_build.py` snapshots the previously
qualified full-search sources and compiles their existing FFTW backend with
FP32 coarse acquisition and the conditioned-frequency guard unchanged.
`-fno-fast-math` remains enabled. ARM linkage is dynamic; execution receipts
record the actual device FFTW, libc, libm, and loader hashes. No RF capture was
started, and these measurements exclude simultaneous capture overhead.

## Large-cohort quality

The host qualification executes every scheduled window on 704 saved DS7
dwells spanning all 88 recordings (eight selected dwells per recording,
0.361% of 194,934 total dwells). This is not a full-DS7 evaluation.

| Rate (MS/s) | 20 ms receiver-windows executed | Positive windows recovered | Individual hits recovered |
|---|---:|---:|---:|
| 2.5 | 3,344 | 1,682/1,682 | 4,573/4,573 |
| 5 | 4,752 | 1,874/1,874 | 5,466/5,466 |
| 7.5 | 4,048 | 1,933/1,933 | 5,186/5,186 |
| 10 | 3,344 | 1,518/1,518 | 4,356/4,356 |
| **Total** | **15,488** | **7,007/7,007** | **19,581/19,581** |

No missing windows or added positive candidates. The original baseline
comparison retains the previously documented negative candidate discrepancy
at ordinal 306, RX0, probe3 (four ordered ranks differ). It originates in
FP32 coarse acquisition, which predates this FFT replacement. An independent
comparison against the qualified previous native implementation isolates the
effect of changing FFT backends.

Positive means margin >= 0.025. Individual recovery uses maximum one-to-one
matching within the same dwell/receiver/window, with <=2 sample epoch and
<=8 kHz tracking CFO differences. The stronger ordered scientific comparison
requires identical integer epoch, <=2e-6 Hz CFO error and <=2e-9 score error.

## ARM all-rate probe measurement

CPU0 on PLUTO+ 192.168.1.15, four saved probe-zero receiver-windows per rate,
one measured invocation per probe. All 16 probes retain eight candidates and
recover all 22 original positives. All comparable downstream scientific
fields meet the strict tolerance above. The raw all-FP64 oracle audit still
flags the known coarse-score/grid rounding from the retained FP32 coarse
implementation; its failure receipt is preserved, not relabeled as passing.
The original oracle does not emit the pre-interpolation fine-CFO field.

The 2.5 MS/s four-probe mean is about 1.996 seconds per receiver-window,
versus 2.741 seconds for the prior qualified optimized kernel. Fine FFT time
falls from roughly 904 ms to 174 ms. Final GLRT FFT time also falls, while
coarse acquisition remains about 1.21 seconds. This makes coarse acquisition
the main remaining runtime cost.

| Rate (MS/s) | Mean CPU seconds / 20 ms receiver-window | Coarse seconds | Fine FFT seconds |
|---|---:|---:|---:|
| 2.5 | 1.996 | 1.214 | 0.175 |
| 5 | 5.928 | 4.299 | 0.391 |
| 7.5 | 11.754 | 9.249 | 0.667 |
| 10 | 19.122 | 15.655 | 1.026 |

These are measured per-window costs, not real-time throughput claims. Each
120 ms dual-receiver dwell schedules 22 such overlapping windows.

A separate matched three-repeat 2.5 MS/s check gives **1,997.96 ms/window**,
confirming the single-invocation result. The corrected guarded FP32 screen
takes **2,121.53 ms/window** with the same four probes and three repeats,
so it is not selected. Its fine-stage verification costs more than the FFT
work it avoids on this target.

## Matched full-dwell ARM qualification

Four metadata-selected 2.5 MS/s dwells, identical to the previous qualified
ARM cohort: **88 windows**, **119/119 individual hits**, **49/49 positive
windows** recovered, no ordered scientific errors. Each run starts from a
saved 120 ms dual-receiver dwell and processes all eleven windows per receiver.

| Backend | CPU seconds / 120 ms dwell | Speed relative to prior backend |
|---|---:|---:|
| Prior built-in FP64 FFT | 60.314 | 1.00x |
| FFTW FP64 | **43.973** | **1.37x** |

This saves **27.1%** of CPU time on matched full dwells. The four-probe
comparison gives about **2.65x** relative to the first faithful native port,
which used the original insertion-sort path; that is a separate probe
comparison, not a measured original full-dwell timing.

At 43.973 seconds of CPU per 0.120 seconds of dual-RX input, compute alone is
about **366 times** a continuous single-core real-time budget. With 40%
headroom, the budget would be 0.072 CPU seconds per dwell, leaving about a
**611x** gap before capture costs. The goal is not achieved.

## Scope and next step

This is a full-search speed improvement, not a real-time result. Cold setup,
I/O, and capture costs must still be accounted for in an eventual streaming
integration. Preserve this implementation as the scientific comparator for
future coarse-search or overlap-reuse work. The separate guarded FP32 fine
screen in this folder is an experiment and has its own qualification record;
its results must not be conflated with this FP64 FFTW path.

## Reproduction

Build in a new output directory; existing output directories are intentionally
not overwritten:

```sh
.venv/bin/python reports/2026_09_28_arm_fine_fft/fftw_build.py \
  --arm --output /var/tmp/leo-full-fftw-arm-new
.venv/bin/python reports/2026_09_28_arm_full_optimization/arm_cohort.py \
  --binary /var/tmp/leo-full-fftw-arm-new/cohort \
  --unit /var/tmp/leo-full-fftw-arm-new/test_screen \
  --output /var/tmp/leo-full-fftw-arm-new/cohort-four
```

All-rate probe commands, including examples at 2.5/5/7.5/10 MS/s, are retained
in `fftw-results/arm/probes-allrates/results.jsonl`. The original probe runner
exits nonzero for the inherited FP32 coarse comparison; consult
`downstream-audit.json` for the explicitly separated downstream result.
Host cohort commands and inputs are preserved in the archived manifests and
build receipt. Target tests require access to the authorized PLUTO+ and the
existing saved-IQ fixtures; they do not access RF devices.
