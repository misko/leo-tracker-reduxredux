# Reusing the center of the fractional GLRT grid

The grouped detector reduced median fifth-center fractional-refinement CPU from **9.02 to 7.09 ms** on 96 held saved-IQ windows. The complete fifth-center call fell from **30.95 to 28.78 ms** median wall time and from **37.20 to 35.20 ms** at p95. All **1,536 ordered candidates per mode** matched the frozen typed detector field for field after removing clocks, including all **243 stock and 255 fifth-center gated candidates**. [Timing chart](stage.png) · [PDF](stage.pdf) · [Per-call times](stage.csv)

## Exact integer bracketing

The detector already scores the integer epoch at the candidate's selected CFO before fractional refinement. Fractional refinement visits that same epoch in the middle of its five-point bracket. In the qualified geometry both calls use the same 16-frame budget, available frames, template rotation, exact/control templates and early 64-symbol region. The new path brings the two existing center scores into the bracket and computes the four outer starts in two AVX2 pairs. Each start retains the scalar order of its complex sums and its own frame spectra, normalization, FFTs, bin ties and grid scores. The parabolic timing calculation and terminal 16-tap Lanczos resampling still use their original arithmetic.

The accelerated branch requires 10 MS/s wide mode, AVX2, common frame support and a grid contained within one epoch period. It uses the original scalar path at circular boundaries, at unequal terminal-frame support and on other architectures. The work audit removes 1,383 stock and 1,390 fifth-center integer hypothesis evaluations across the distinct genuine windows. In fifth mode that avoids 41,178 per-frame 128-point FFTs and 5,560 final spectral transforms. The four remaining hypotheses keep their full FFTs. The grouped path uses about 16.5 KiB of automatic arrays and no added persistent receiver workspace. [Native source and build receipt](detector-build.json) · [Work counts](summary.json)

## Matched saved-IQ results

The fixed panel uses DS26-0197 lower and DS29-0316 upper, the first 24 windows in each capture's segments 2 and 7. These chronological blocks are distinct from the previous typed-detector benchmark's segments 0 and 4. Both roles ran three warmed, counterbalanced repetitions on CPU20 for DS26 and CPU21 for DS29. Clocks start with loaded CI16. The decoded boundary includes conversion of typed output to Python fields. The typed-call clock includes the ctypes invocation and ends at the native output structure. Archive reading and diagnostic JSON are outside these clocks.

| Median / p95 in ms over 288 calls per role and mode | Typed stock | Grouped stock | Typed fifth | Grouped fifth |
| --- | ---: | ---: | ---: | ---: |
| Fractional stage CPU | 8.89 / 10.35 | 6.88 / 8.09 | 9.02 / 10.47 | 7.09 / 8.26 |
| Native typed call CPU | 24.30 / 28.50 | 22.27 / 25.83 | 30.12 / 34.32 | 28.12 / 32.21 |
| Call through decoded fields CPU | 24.50 / 28.74 | 22.47 / 26.04 | 30.32 / 34.56 | 28.35 / 32.45 |
| Call through decoded fields wall | 25.24 / 32.81 | 23.52 / 30.71 | 30.95 / 37.20 | 28.78 / 35.20 |
| Decoded wall at or below 20 ms | 12 / 288 | 36 / 288 | 0 / 288 | 0 / 288 |

The paired median wall gain was 1.93 ms in stock and 2.03 ms in fifth mode. Fifth wall p50/p95 moved 30.86/35.66 to 29.22/34.17 ms on DS26, and 30.95/39.26 to 28.56/35.93 ms on DS29. Both signed pilots at ±688.125 kHz survived on both receivers. The two seeded-noise windows and two zero-IQ windows yielded no gated candidates. All six controls reproduced stock when hints were absent. Peak Python worker RSS ranged 200,844–200,972 KiB for the typed control and 200,612–201,048 KiB for the grouped detector. These are x86 host timings and worker memory, ending at RF measurements. This study fits no positions. [Paired distributions](summary.json) · [Numerical receipts](measurements.json.gz)

## Offline release and complete recording interface

The capsule contains both existing C ports, the exact published shared libraries, the original native scout sidecar, the source closure, both edge template banks and a synthetic signed upper-edge canary. It uses x86-64 Linux glibc and system `libfftw3.so.3`. Fresh extraction verified every packaged file hash and reproduced the matched C canary in stock, fifth and absent modes. [Capsule](fractional-detector-linux-x86_64.tar.gz) · [Extraction verification](capsule-verification.json)

```sh
mkdir replay
tar -xzf fractional-detector-linux-x86_64.tar.gz -C replay
cd replay
sha256sum -c SHA256SUMS
timeout 10s ./fractional-detector fifth upper-strong.ci16 upper-exact.c16 \
  upper-control.c16 upper-filters.c8 upper-energy.f64 > receipt.json
```

Use `stock` or `absent` for the other modes. The file format is exactly 200,000 little-endian signed 16-bit `[rx0 I, rx0 Q, rx1 I, rx1 Q]` sample times at 10 MS/s. Native callers may use `source/native_hotpath.h` or the existing `leo_native_glrt_analyze_center_union_v1` entry. The latter was independently tested against the released center-union library using the actual Python FFTW scout and full direct adapter. Each edge used eight genuine held windows plus signed, seeded-noise and zero controls. Complete public rows, full ordered scout results and values, hint support, every gate and absent-hint outputs matched. That direct proof is a bounded input to the separate complete-recording receiver qualification. [Direct feature gate](whole-feature-gate.json) · [Lower proof](direct-lower.json) · [Upper proof](direct-upper.json) · [Result lock](result-lock.json)
