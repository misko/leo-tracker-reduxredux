# F(4,3) coarse-dot feasibility microkernel

This bounded experiment tests the arithmetic kernel needed to compute four
adjacent coarse epochs from each three-tap template chunk. It uses the rational
Cook-Toom/Winograd F(4,3) transforms. The six-sample input transform is shared
by all 12 CFO lanes, the six transformed complex template coefficients are
prepared once, and ARM executes the six pointwise complex products four CFOs
at a time with explicit NEON.

For one three-tap chunk and 12 CFOs, the direct kernel performs 144 complex
multiplications (4 outputs x 3 taps x 12 CFOs). F(4,3) performs 72 (6 transform
points x 12 CFOs), plus one shared complex input transform and CFO-local output
adds/scales. Template transforms are outside the hot loop. This changes FP32
addition order and is an approximation; it cannot be described as exact even
though the transform is algebraically equivalent over real arithmetic.

The oracle covers four nominal rate labels, 8,000 pseudorandom cases,
coherent input, CI16-normalized small values, zero, and the six-sample boundary
needed for the fourth output. Worst observed absolute component error is
`2.86102295e-06` with the required `-fno-fast-math` build. Host and sanitizer
tests pass, and the Cortex-A9 artifact cross-builds with warnings as errors.
Disassembly confirms packed `q`-register loads and arithmetic in `cw_four`.

The host optimized microbenchmark is neutral and noisy (about 0.98--1.03x the
direct kernel across rebuilds), so this is not integrated into the full search
yet. Host behavior does not establish Cortex-A9 benefit because the ARM path is
explicitly NEON while the host path is scalar. A bounded physical run of the
standalone ARM unit can decide whether integration is justified. Integration
must also handle the scalar fifth cell and template lengths not divisible by
three, while preserving each frame's accumulation order and support rules.

Build with:

```sh
python3 reports/2026_09_29_arm_wave7_coarse_winograd/build.py
```

The ARM test binary SHA-256 is
`5b9254ff11115669c9a6785c29d5cd7256645aca300ce435c8c61e137217595e`.

## Fair V2 comparator

The V1 physical result (`direct_ms=1244.749`, `winograd_ms=909.350`) is
confounded: V1's direct comparator is scalar C while Winograd is explicit
NEON. It does not establish a 27% algorithmic gain over the real coarse kernel,
which is already explicit NEON.

V2 is isolated under `implementation-v2`, `tests-v2`, and `builds-v2`. It uses
the same explicit four-CFO NEON packing for both direct and Winograd kernels and
pins the ARM process to CPU0. Its ARM SHA-256 is
`7dce7accf886cc4a657ab1c837d3456ff4b1f15f5ae2d832fe20f90adb2213ac`.
No full-search integration should proceed until this fair comparator shows a
material physical ARM improvement.
