# Exact x86 integer SIMD feasibility result

This bounded prototype is scientifically exact but did not pass its preregistered
performance gate. It is therefore not promoted and no development or control
dataset replay was opened for this variant.

The candidate keeps the stable FP32 FFTW detector profile and changes four integer
ingress loops: natural dual-receiver lag-4 rank folding, selected-window packing,
coarse power/differential folding, and nuisance lag sums. Runtime dispatch uses
CPUID for SSSE3/SSE4.1. Forced selection is thread-local; the CPUID state is a C11
atomic. Every signed CI16 product is formed in 32 bits and sign-extended to 64 bits
before complex addition or subtraction. FP reductions, FFTs, support, frame starts,
tie rules, nuisance decisions, and confirmation are unchanged.

On P-core 0, the frozen component gate timed two complete sequential receiver
calls per repetition, with one warmup and 11 counterbalanced scalar/SIMD
repetitions. Caller thread CPU medians were:

| Rate | Exact scalar | SIMD | CPU speedup | Wall speedup |
|---|---:|---:|---:|---:|
| 2.5 Msps | 1.666 ms | 1.564 ms | 1.0653x | 1.0651x |
| 5 Msps | 4.454 ms | 4.176 ms | 1.0665x | 1.0664x |

Both rates missed the frozen 1.10x incremental gate. The measured improvement is
about 6.5% for this complete server call. It cannot support a 10x claim. Because
the gate failed, the design required stopping before the 256 receiver development
visits, 24 old constructed-control receiver visits, and 40 adversarial-control
receiver visits. No result ratio was multiplied by an earlier optimization ratio.

The correctness suite compares forced scalar, forced SIMD, and the frozen FP32
FFTW library at both rates and both receiver lanes. It covers random CI16, extrema,
zero energy, an active strong-tone nuisance fit, terminal vector remainders,
invalid-output preservation, concurrent first dispatch, input immutability, and
PROT_NONE guard pages for packing and the full RX1 rank path. All 20 tests pass.
The build receipt also records the effective preprocessor dependency graph, proving
that the local SIMD headers were compiled, and records no global ISA flag. Binary
disassembly contains the expected `pmulld`, signed `pmovsxdq`, and 64-bit
`paddq`/`psubq` sequence.

Frozen evidence:

- `design.json`: `1e1e7e8c38452b01c86935e7f56edd671326eb3bb5195e7d7145bf4492fc7794`
- `libserver_simd.so`: `1364b352d661df932716781dbf5b022bde738a76dceb73141b64fe35d43371ad`
- `libserver_simd.so.build.json`: `666d4df0f64583734a9d22a9e8d4194d6f7a47260da75f930feea3d8f5538af7`
- `component_results.json`: `4f1abd221b530cb7953a9a0cee9f09f98a9e9f3250cdb137f348ae87aa99ea61`
- `server_simd.c`: `fd635209b1b3e341935869ff20ed4e7ad0f3adf29a0ecb68f5f09f462dd612ce`
- `ci16_fold.h`: `56f0dc6f2a7200211595abf44b40bfddbc506ae7643ba76893b10f059bb32f6f`
- `ci16_lag.h`: `3a6687e485ef1ee46b91853cd526bba7796b07333b77a41e2dc22f54d6582b80`

The result applies to this x86 server harness. It says nothing about physical ARM
performance.
