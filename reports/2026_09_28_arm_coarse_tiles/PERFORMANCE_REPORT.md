# Coarse acquisition: compiler scheduling and NEON tile experiments

The selected change retains the existing coarse algorithm and disables GCC
automatic array prefetching only for the functions in `coarse_fp32.h`.
FP64 FFTW remains the FFT backend. No windows, candidates, symbols, frames,
or frequency hypotheses are removed. No new approximate arithmetic is added.

## Matched 2.5 MS/s ARM measurements

All runs use CPU0 on PLUTO+ 192.168.1.15 with saved IQ. No RF collection or
simultaneous capture was started. Four matched probe-zero receiver-windows,
three repetitions per probe:

| Method | CPU milliseconds / window | Relative to previous FFTW build |
|---|---:|---:|
| Previous FFTW build | 1,997.96 | 1.00x |
| Disable automatic prefetch globally | 1,700.80 | 1.17x |
| **Disable automatic prefetch only in coarse kernel** | **1,681.06** | **1.19x** |
| Four-epoch, four-CFO NEON tile | 2,953.03 | 0.68x |
| Same tile, automatic prefetch disabled | 2,971.95 | 0.67x |
| Four-epoch, two-CFO tile, prefetch disabled | 2,260.68 | 0.88x |

Every measured variant produces identical canonical candidate objects and
bit-identical coarse grids on these probes. The source-level vectorization
experiments are rejected for speed. The two-CFO version fixes the four-CFO
version's severe register spilling but is still slower than the original
kernel. Disabling loop peeling in addition to prefetch produces the exact
same untiled binary, so that duplicate binary was not timed separately.

## Full-dwell ARM verification

Four metadata-selected saved 120 ms dual-receiver dwells at 2.5 MS/s,
identical to the preceding FFTW benchmark. Each processes 11 overlapping
20 ms windows per receiver, at 10 ms stride.

| Measurement | Previous FFTW | Selected compiler change |
|---|---:|---:|
| CPU seconds per dwell | 43.973 | **37.037** |
| Windows executed | 88 | **88** |
| Original individual hits recovered | 119/119 | **119/119** |
| Original positive windows recovered | 49/49 | **49/49** |

All **704 candidate objects** in the ARM cohort are identical to the previous
FFTW run, including epoch, CFO, acquisition scores, and final GLRT scores.
The selected change saves **15.8%** of CPU time on these full dwells. CPU
stage totals show the saving in coarse acquisition: 26.740 to 19.780 seconds
per dwell; the remaining stages stay approximately unchanged.

The experiment does not establish real-time operation. Compute alone still
uses about **309 times** a continuous single-core budget. A 40% headroom
budget allows 0.072 CPU seconds per 120 ms dwell, leaving about a **514x**
gap before capture costs. Workspace setup and file transport are outside the
kernel CPU measurements.

## Why the compiler change helps

The generated baseline coarse function contains an unrolled tap loop with
many vector spills. With automatic prefetch disabled, the function shrinks
from 3,112 to 1,404 bytes. Static assembly lines accessing the stack decrease
from 171 to 33; these are code-inspection counts, not dynamic performance
counters. `COMPILER_INSPECTION.json` and saved assembly retain the evidence.
Limiting the option to coarse functions avoids small regressions in other
stages seen with the global flag.

The supported rates remain 2.5/5/7.5/10 MS/s. The global compiler variant was
also measured on 16 all-rate ARM probes: all 128 candidate objects and every
coarse-grid byte match the previous FFTW backend. Its mean full-window
speedups are 1.17x, 1.26x, 1.31x, and 1.31x respectively.

The selected function-scoped variant also completed all 16 ARM probes with
bit-identical grids and identical candidate objects. Four probes per rate,
one repetition per probe:

| Rate (MS/s) | Previous FFTW seconds/window | Selected seconds/window | Speedup |
|---|---:|---:|---:|
| 2.5 | 1.996 | 1.688 | 1.18x |
| 5 | 5.928 | 4.663 | 1.27x |
| 7.5 | 11.754 | 8.902 | 1.32x |
| 10 | 19.122 | 14.477 | 1.32x |

The small timing difference between the single-repetition and three-repetition
2.5 MS/s measurements is retained in the receipts. No statistical confidence
interval is claimed.

## Larger DS7 quality qualification

A separately compiled host version of the selected change completed **704
dwells across all 88 recordings**, eight metadata-selected dwells per
recording. This is **0.361% of DS7's 194,934 dwells**, not full DS7.

| Rate (MS/s) | 20 ms windows run | Original positive windows recovered | Original individual hits recovered |
|---|---:|---:|---:|
| 2.5 | 3,344 | 1,682/1,682 | 4,573/4,573 |
| 5 | 4,752 | 1,874/1,874 | 5,466/5,466 |
| 7.5 | 4,048 | 1,933/1,933 | 5,186/5,186 |
| 10 | 3,344 | 1,518/1,518 | 4,356/4,356 |
| **Total** | **15,488** | **7,007/7,007** | **19,581/19,581** |

All **123,904 candidate objects** are identical to the previous qualified
host FFTW implementation. There are no missing windows or added positives.
Against the frozen original, the same negative-candidate coarse-basin
discrepancy remains at ordinal306/RX0/probe3; the compiler change introduces
no new difference. Host qualification establishes corpus equivalence;
runtime improvements above are measured separately on ARM.

For the original comparison, positive means margin >=0.025. Hit recovery
uses maximum one-to-one matching in the same dwell/receiver/window within
2 samples and 8 kHz tracking CFO; strict ordered scientific checks use exact
integer epochs, 2e-6 Hz CFO tolerance and 2e-9 score tolerance. Direct
comparison to the preceding FFTW build is stronger: complete candidate
objects are identical, including numerical values and signed-zero encoding.

## Validation and reproduction

The tile experiments include host full-grid parity over all four rates with
full, partial-tail, and zero inputs. Their ARM NEON unit tests compare against
the original NEON reduction and pass exact equality. An ARM-only bug in the
initial test reference was fixed before target qualification; `*-a` four-CFO
builds are superseded by `*-b`. No tolerance was relaxed to pass these tests.

The frozen all-FP64 oracle runner still exits nonzero because the retained
FP32 coarse stage differs from that original grid/score. Those raw failure
receipts are preserved. The paired comparison against the already qualified
FP32-coarse/FP64-FFTW build is performed by `compare_probes.py` and requires
identical candidate objects and coarse-grid bytes.

```sh
.venv/bin/python reports/2026_09_28_arm_coarse_tiles/compiler_build.py \
  --variant coarse-only --output /var/tmp/leo-coarse-scoped-new
.venv/bin/python reports/2026_09_28_arm_full_optimization/arm_cohort.py \
  --binary /var/tmp/leo-coarse-scoped-new/cohort \
  --unit /var/tmp/leo-coarse-scoped-new/test_screen \
  --output /var/tmp/leo-coarse-scoped-new/cohort-four
```

Target tests require the authorized PLUTO+ and existing saved-IQ fixtures.
Build receipts retain commands, compiler identity, and source/binary hashes.
All changes remain research tooling; the production analysis pipeline is not
changed by this experiment.
