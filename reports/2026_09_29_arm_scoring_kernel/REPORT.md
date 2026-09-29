# Faster FP64 final GLRT scoring from CI16

## Motivation

The single-core real-time objective requires cheap final scoring as well as
cheap discovery. The preceding oracle-coordinate budget experiment consumed
118.651 ms per dual-RX dwell for input preparation plus positive-only scoring,
even with free perfect candidate locations. The target remains 72 ms.

## Problem

The final scorer's hot loop uses C complex multiplication with compiler
exceptional-value handling. It also materializes FP64 IQ before scoring,
despite reading only the supported pilot regions. These costs can be reduced
without dropping symbols, frames, exact/control templates or residual bins.

This is a **scoring experiment with original baseline coordinates supplied**.
It is not a new detector, tracking policy, discovery-recovery result, or
real-time pipeline. Existing exhaustive acquisition remains far over budget.

## Solution

1. Enable the existing bounded magnitude helper: sqrt(re*re+im*im) for finite
   normal squared magnitudes, with cabs fallback otherwise.
2. Expand the two FP64 complex correlation updates into explicit real and
   imaginary products, preserving their component accumulation order.
3. Read interleaved CI16 at each supported integer sample directly, converting
   only the samples consumed by the final scorer. Avoid materializing the
   complete FP64 dwell. The conversion cost is inside scoring time.

Global `-fcx-limited-range` was tested diagnostically, but is **not enabled in
the selected local-arithmetic variant**. No fast-math flag, FP32 final score,
reduced frame/symbol count, new gate, or reduced residual FFT is used.

`explicit_dot.inc` supplies the two correlation updates. `run.py` overlays
the frozen source in each independent build. `probe.c` is a serial diagnostic
with a current-window CI16 pointer. This private interface supports only zero
fractional offset, is not thread-safe and is not production-integrated. The
selected v2 explicitly rejects all nonzero/nonfinite offsets before accessing
IQ; fractional scoring is outside its qualification. Arbitrary overflowing/nonfinite inputs are also
outside the CI16/template scope of this experiment.

## Method

PLUTO+ 192.168.1.15 CPU0, four metadata-selected 2.5 MS/s DS7 dual-RX dwells,
three repeats per variant. A dwell is 120 ms, 22 overlapping receiver-windows,
176 candidate entries. Four unique dwells contain 88 windows, 704 entries and
119 original positives. Coordinates are supplied by the original baseline.

All eight candidates are scored in every window. Positive-only CPU is a
retrospective sum of those individually timed calls whose original margin
was >=0.025; no usable algorithm knows this subset for free. File I/O,
allocation and template/FFT setup are outside timing. There is no RF capture
or concurrent RAM producer. Repeats do not enlarge the independent cohort.

## ARM results

Mean CPU milliseconds per 120 ms dual-RX dwell:

| Variant | Preparation | All 176 scores | Original-positive scores only | Preparation + positive-only |
|---|---:|---:|---:|---:|
| Previous shared-FP64-dwell reference | 36.781 | 484.336 | 81.870 | 118.651 |
| Bounded magnitude | 36.743 | 446.494 | 75.172 | 111.915 |
| Bounded magnitude + global limited-complex flag (diagnostic) | 36.983 | 273.284 | 45.825 | 82.808 |
| Bounded magnitude + local explicit FP64 dot | 36.677 | 283.230 | 47.377 | 84.054 |
| **Local dot + bounded magnitude + direct CI16 v2** | **0.093** | **273.929** | **46.574** | **46.667** |

Compared with the shared-FP64 reference, the selected variant reduces the
scoring stage by 43.4% (1.77x). Preparation plus all scores falls from 521.117
to 274.022 ms (1.90x). The oracle-positive-only diagnostic falls 60.7% to
46.667 ms (2.54x), leaving about 25.3 ms of the 72 ms budget before discovery,
negative proposals and fallback. This is evidence that final scoring need not
alone preclude the goal, not proof that a complete detector fits.

Scoring all candidates still exceeds 72 ms by 3.80x even with discovery free.
No whole-search speedup is inferred from these isolated-stage measurements.

## Numerical qualification

Every timed ARM variant preserved all 704 candidate score/coordinate checks
and all 119 positive decisions on its four dwells, across all three repeats.
The selected variant then passed host replay at all original coordinates in
the full existing 704-dwell DS7 subset:

| Rate | Windows evaluated | Candidate entries | Original positive entries with matching scores/gates |
|---|---:|---:|---:|
| 2.5 MS/s | 3,344 | 26,752 | 4,573/4,573 |
| 5 MS/s | 4,752 | 38,016 | 5,466/5,466 |
| 7.5 MS/s | 4,048 | 32,384 | 5,186/5,186 |
| 10 MS/s | 3,344 | 26,752 | 4,356/4,356 |
| Total | 15,488 | 123,904 | 19,581/19,581 |

Maximum exact/control score difference is 6.773e-15; maximum tracking CFO
difference is 2.853e-9 Hz. Bounds are 2e-9 score and 2e-6 Hz, with identical
positive gates and original epochs. These are **oracle-coordinate numerical
equivalence counts**, not detections discovered by the new method.

Twenty-four host controls additionally compare the frozen scorer with the new
one: four rates, both edges, zero/full-scale/random CI16, 176 evaluations each.
They exercise epochs at zero/midpoint/last cell and CFOs including +/-400 kHz.
All 4,224 comparisons meet score/CFO tolerances and preserve gate decisions.
Host checks establish all-rate numerical behavior; ARM timing is 2.5 MS/s only.

## Reproduction and evidence

`run.py` imports the sealed scoring-budget runner; it requires that runner's
saved inputs, baseline, toolchain and already staged device files. Use a fresh
output directory. The selected command is:

```sh
.venv/bin/python reports/2026_09_29_arm_scoring_kernel/run.py new-arm-run --shared --magnitude --explicit-dot --raw-ci16
```

`explicit-ci16-v2/` archives the source expansion, ARM binary, build receipt,
seeds, raw results and summary. Earlier variant directories retain the other
experiments. `host704-v4/` retains all 704 raw outputs and its build receipt;
`qualify.py` implements the checks. `controls-v3/` and `controls.py` retain the
synthetic comparisons against a separately compiled frozen reference.
`test_zero_offset.c` and `offset-test.json` check rejection of unsupported
offsets before any input access. V1 and its successful host704-v3/controls-v2
checks are retained; v2 adds the explicit unsupported-offset rejection.

Host qualification attempts v1/v2 and control attempt v1 stopped at compilation
because newer host glibc redefines `_POSIX_C_SOURCE` under `_GNU_SOURCE`.
The successful host builds retain this warning in `compiler.stderr` and remove
only `-Werror`; the numerical source and FP flags are unchanged. ARM builds
retain `-Werror`. Failed compile attempts contain no scientific results.

The real-time reduced-profile result and exhaustive high-recovery result
remain distinct; see the [performance index](../../docs/research/arm-glrt-performance.md).
No production code, published contracts or scientific fixtures were changed.
