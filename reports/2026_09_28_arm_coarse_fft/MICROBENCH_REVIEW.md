# Coarse FFT microbenchmark fairness review

## Result

`coarse_fft_bench.c` is a bounded raw-correlation throughput microbenchmark
after the fairness corrections. It is not a coarse-grid, full-window, or
dwell-speed result. The corrected source cross-compiles for Cortex-A9; its
host synthetic, zero, and impulse checks pass. The retained ARM v4 receipt is
reviewed below, but this review did not run a new ARM job.

The comparison is deliberately a combined candidate:

```
qualified 12-lane direct loop  versus  132 exposed-filter FFT bank
```

The direct side retains the qualified kernel's three four-lane NEON groups.
The FFT side avoids the twelfth CFO lane because full search reads 11 coarse
CFOs. Any reported speedup includes omitting that unexposed lane as well as
FFT-bank work, and cannot be called a pure FFT algorithm factor.

## Corrections verified

The direct reference uses prepacked separate real and imaginary tap-major
twelve-CFO arrays. Its ARM path uses the qualified three-vector complex
multiply grouping and the same two-Newton-step NEON reciprocal-square-root
magnitude. It does not gather complex templates or call `hypotf` in the
measured ARM path.

Both sides fold into an epoch-major 12-float accumulator. For every synthetic
position, symbol contributions are added in increasing symbol order. The
twelfth synthetic accumulator lane is zero padding: direct vector work remains
present while the 11-exposed-filter output comparison stays explicit.

The fixture is centered deterministic complex FP32 data. Input/template
prepacking, FFTW planning, and kernel-spectrum construction are outside the
timed regions and are explicitly reported as excluded. Each path uses
`CLOCK_PROCESS_CPUTIME_ID`; the ARM binary pins itself to CPU0. Three runs use
their median. The source cross-compiles as ARM EABI with Cortex-A9/NEON flags.

Host validation is a smoke test, not performance evidence. It completed each
tap/FFT combination with finite errors below the configured bounds, plus zero
and impulse checks. Host FFTW and cache behaviour cannot be extrapolated to
the target.

## Scoped ARM v4 observation

`arm-microbench-v4/result.json` records a successful CPU0 ARM run of this
synthetic benchmark, with its binary and build-receipt hashes. The best FFT
length was 128 for 11 and 22 taps, and 256 for 33 and 44 taps. The 11-tap
case was slower (`172.589 ms` FFT versus `127.448 ms` direct, `0.7384x`).
The larger synthetic filters were faster: `1.2353x` at 22 taps, `1.6954x` at
33 taps, and `2.1066x` at 44 taps. The reported normalized errors were about
`4.3e-7` to `5.5e-7`, with zero and impulse checks passing.

Those figures support continuing the bounded investigation for longer filters
and rule out the small 11-tap bank as a standalone speed win. They remain
raw-correlation measurements for the combined 12-lane-direct/132-filter-FFT
candidate. They do not predict full coarse-grid or GLRT speed.

## Outside the benchmark

The benchmark has 8,192 contiguous raw positions, but no actual 16-frame
schedule, FP64 prefix subtraction, inverse normalization, support counting,
NMS, or top-eight repair. It therefore cannot establish a coarse-grid gain.
A block-outer full pipeline can also alter FP32 accumulation order across
frames and symbols.

Future full-pipeline work must either cache forward block spectra and process
symbols/blocks in an order preserving each epoch's direct addition sequence,
or treat the FFT grid only as a proposal and repair selected epochs plus
neighbours with `coarse_fp32_cell` before NMS. The latter remains subject to
the guard and fallback rules in `FFT_BANK_DESIGN.md`.

## Required next measurement

Use the ARM CPU0 binary with a retained build receipt, then measure actual
20-ms windows at all four rates including direct prefix/normalization and the
selected repair guard. Report direct and FFT-plus-repair coarse CPU separately,
repair/fallback counts, and complete 11-window/two-receiver dwell CPU. Do not
claim a performance gain before those results exist.
