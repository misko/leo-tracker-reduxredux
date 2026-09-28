# Coarse-search experiments: measured decisions

The qualified 2.5 MS/s GLRT implementation is unchanged. This investigation
rejected a slower exact kernel, quantified the limited opportunity for exact
cross-window caching, and found a promising FFT-bank kernel for higher rates.
It does not establish a new full-pipeline speedup or meet the real-time goal.

## Exact four-epoch kernel: reject

SOL implemented the alternative NEON lane layout and verified its arithmetic.
It keeps all hypotheses, with four neighboring epochs and one CFO per vector.
Host full/partial/zero coarse grids match at every supported rate. ARM pure
kernel tests and all 32 candidate objects in four repeated saved-IQ probes
match the preceding CZT implementation; coarse grids are bit-identical.

Its ARM mean is **1,746.50 ms/window**, compared with **1,559.84 ms/window** for
the qualified CZT build: **11.97% slower**. No larger cohort was run for this
rejected implementation. Sources, receipts, and evidence are sealed in
`../2026_09_28_arm_epoch_lane/`.

## Exact overlap reuse: limited by normalization

Root measured all 704 saved dwells and Terra reviewed the reuse boundary.
Only 33.78%, 34.05%, 33.97%, and 34.01% of adjacent window pairs have equal
normalization scales at 2.5, 5, 7.5, and 10 MS/s respectively. None of the
receiver/dwell sequences shares one scale across all eleven windows.

Reusing raw correlation magnitudes requires that scale match; per-window
prefix subtraction, inverse normalization, support, and addition order must
remain local. Combining roughly half-window overlap with this scale gate
allows only about 15–16% raw-dot reuse before cache overhead. This is a
screening estimate, not measured CPU savings. A power-of-two normalization
could permit broader reuse but changes the current FP32 rounding and needs
separate qualification. See the sealed `scale_reuse.json` and `REUSE_REVIEW.md`.

## Shared-input FFT bank: higher-rate candidate

The standalone bank computes all 132 public symbol/CFO filters using
overlap-save convolution. Input FFTs are shared, kernel spectra cached, and
V5 uses explicit NEON complex multiplication. ARM CPU0 measurements use
process CPU time, three repetitions and their median, on identical centered
synthetic inputs. The benchmark evaluates 8,192 correlation positions per
filter and accumulates into the same epoch-major layout.

| Corresponding rate | Taps | Best FFT size | Direct CPU ms | V5 FFT CPU ms | Kernel speedup |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2.5 MS/s | 11 | 64 | 127.332 | 154.262 | **0.8254×: slower** |
| 5 MS/s | 22 | 128 | 229.951 | 165.635 | **1.3883×** |
| 7.5 MS/s | 33 | 128 | 332.957 | 174.019 | **1.9133×** |
| 10 MS/s | 44 | 256 | 435.303 | 187.101 | **2.3266×** |

These are raw correlation-bank timings, **not full GLRT speedups**. They omit
per-window normalization, frame/epoch folding, support counting, candidate
selection, direct repair, and the remaining GLRT stages. Prepacking, FFTW
planning, and kernel-spectrum construction are also excluded. The direct
baseline retains twelve NEON lanes while FFT evaluates eleven public CFOs;
ratios therefore include avoiding the unused lane's work.

V4, using compiler-generated complex multiplication, was slower than V5.
V6, using FFTW_MEASURE instead of FFTW_ESTIMATE, also lost: its best FFT times
were 287.004, 309.868, 324.073, and 338.576 ms for the four tap lengths.
Planning time is reported separately and does not explain that execution-time
loss. Retain V5; do not promote V6 or apply FFT to 2.5 MS/s on this evidence.

All ARM configurations pass zero/impulse and synthetic-grid comparisons.
The V5 random accumulated-magnitude comparisons have maximum relative errors
below 5.6e-7 and normalized RMS errors below 1.3e-7. These are not normalized
GLRT-score bounds. Host ASAN/UBSAN tests pass, but host runs do not execute the
ARM-specific NEON branches.

Root's separate four-window DS7 prototype validates convolution indexing and
candidate coverage: with NumPy double FFTs over FP32 operands, all eight
selected coarse peaks match in each window. Maximum grid error is 1.286e-7.
An engineering guard selected eight high cells plus neighbors, 24/36,663
cells per window. This is not an ARM float-FFT/full-GLRT equivalence test or
a proof of a universal error bound.

## Next acceptance gate

Integrate V5 only as an experimental coarse proposal for 5/7.5/10 MS/s,
retaining the current direct path at 2.5 MS/s. Recompute proposed winning
epochs and neighbors with the qualified direct kernel; validate the guard and
fallback with real data. Measure complete windows and dwells, exact candidate
identity, positive-window recovery, and individual-hit recovery before claiming
an improvement. Preserve original support and frame-rounding semantics.

For 2.5 MS/s, larger gains still require reducing repeated work or a different
search strategy; this investigation has not improved its qualified runtime.
The current best full-dwell result remains **34.332 CPU seconds per 120 ms
dual-RX dwell**, with the previously reported 119/119 ARM hits and 19,581/19,581
host-cohort hits. Simultaneous capture and 40% headroom remain unproven.

See `benchmark_summary.json`, raw `arm-microbench-v*/result.json`,
`MICROBENCH_REVIEW.md`, `FFT_BANK_DESIGN.md`, and archived build snapshots.
