# ARM compiler and compact fine-cache prototypes

This directory contains independently attributable ARM prototypes derived
from the immutable `arm_fine_precision` raw-v2 cohort. They retain the same CLI
and do not run target workloads.

| Variant | Change | ARM cohort bytes | Baseline-relative bytes |
|---|---|---:|---:|
| `strict-lto` | `-flto -fno-math-errno -fno-trapping-math`, with `-fno-fast-math` retained | 1,690,064 | -26,008 (-1.52%) |
| `fine-local` | explicit complex multiply, aligned FP32 FFT cache, FP64 magnitude/accumulation | 1,716,040 | -32 (-0.002%) |
| `combined` | both changes | 1,690,064 | -26,008 (-1.52%) |
| `limited-complex` | combined plus `-fcx-limited-range` | 1,676,876 | -39,196 (-2.28%) |
| `fine-local-v2` | fine-local with guaranteed 16-byte cache alignment | 1,716,080 | +8 (+0.0005%) |
| `combined-v2` | combined with guaranteed 16-byte cache alignment | 1,690,092 | -25,980 (-1.51%) |
| `limited-complex-v2` | limited-complex with guaranteed 16-byte cache alignment | 1,676,904 | -39,168 (-2.28%) |

The byte counts are measured build results, not performance claims. The target
evaluator must decide runtime value. LTO provides a concrete size reduction;
the local source change does not. There is no packed-cache variant because the
existing cache is already exactly two contiguous FP32 lanes per FFT cell (8
bytes), so further packing would either change precision or add unpacking work.

The v2 variants correct a target-specific contract failure found when the ARM
FFTW allocator returned an 8-byte-aligned cache pointer. Cached spectra now use
`posix_memalign(..., 16, ...)` and matching `free`; the component test continues
to require 16-byte alignment. The v1 receipts and binaries remain preserved as
failed-target-test evidence.

The source-local variant replaces `cabsf` with a bounded two-lane FP64
`sqrt(re*re + im*im)` and uses an FP64 reciprocal during score accumulation.
This slightly changes fine-stage rounding and is therefore a separate measured
variant. It does not alter `full_search.c` or `presence.c`, including final FP64
GLRT arithmetic. The compiler-only variants disable math `errno` and trapping
exception observability; they do not use global fast-math and make no bitwise
IEEE-equivalence claim.

`limited-complex` is deliberately more aggressive. GCC may omit range-reduction
and exceptional-value handling for complex division, multiplication, and
absolute value across the whole program. Its unit suite covers finite real
inputs at every supported sample rate, including partial frames; NaN, infinity,
overflow, signed-zero, and floating-point exception behavior are unsupported.
This flag therefore changes scientific semantics even though the final FP64
GLRT source files remain byte-identical. It is not a default replacement.

Each build directory is self-contained and has a `build-receipt.json` with the
exact compiler command, compiler output, binary hashes, and every C/header source
hash. Host and sanitizer tests were compiled from the copied variant source and
executed. ARM test binaries were cross-compiled with distinct names and were not
executed on the host. `build-manifest.json` indexes every receipt, while
`audit.json` verifies hashes, flags, distinct test identities, unit execution,
and unchanged final-GLRT sources.

Reproduction:

This publication tree is intentionally lean: compiled binaries and the repeated
expanded source copies beneath each build directory are omitted. Exact build
commands, original binary hashes, and source hashes remain in each
`build-receipt.json`. `publication-manifest.json` maps every variant to one of
the deduplicated `source-archives/*.tar.gz` snapshots and records both archive
and member hashes. `combined` shares the `fine-local` source snapshot, and
`combined-v2` shares `fine-local-v2`; their compiler flags remain distinct in
their receipts.

Verify the staged evidence and unpack a source snapshot with:

```sh
python3 verify_publication.py
tar -xzf source-archives/fine-local-v2.tar.gz
```

To reproduce binaries, unpack the archive named for the variant in
`publication-manifest.json`, then use the exact host, sanitizer, or ARM command
from the corresponding receipt, replacing its original build-directory prefix
with the extracted snapshot path and choosing a new output path. The original
full working tree can still regenerate and audit all artifacts with:

```sh
python3 reports/2026_09_29_arm_compile_pack/build_variants.py
python3 reports/2026_09_29_arm_compile_pack/audit.py
```
