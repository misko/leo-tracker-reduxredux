# Fine-input NEON audit

The fused path is compiled with `LEO_PRESENCE_COARSE_FP32` and fixed CI16
scale 32768. `coarse_fp32()` converts each input sample to raw/32768 and builds
the FP64 prefix from those normalized values. `fine_precision.h` scales the
selected template by 32768 and restores prefix energy by 32768 squared. Thus
the complex FFT input and denominator return to raw-CI16 units, subject to the
intentional FP32 input/template rounding. This is valid for the bounded CI16
range used by the runner; it does not establish behavior for arbitrary
floating samples or a build without the matching coarse-FP32 prefix.

Template lifecycle is internally sound: `scaled_template` is allocated with
the FFT workspace, cleared and rebuilt for each new epoch cache entry, then
freed with the cache. Per-frame spectra are separately aligned-allocated and
freed by the entry frame count. The allocation assumes `cache->size` covers
all `w->n` template indices, as it does for the current fine FFT setup; that
relationship is not asserted locally.

The host and sanitizer receipts execute inherited all-rate final-reuse,
fine-budget, and moment tests. `test_fine_precision` enters the
`LEO_PRESENCE_COARSE_FP32` branch, so it exercises the scalar mirrored
fine-input construction at all four rates. The physical ARM fused-unit receipt
also passed its inherited suite; in particular, `test_fine_budget_arm` exercised
the NEON fine-input path for the default frame budget and budgets 1/2/4/8 at all
four rates. This is physical-path coverage, not a dedicated raw prepared-buffer
equivalence test: no receipt compares scalar and NEON input cells under zero,
full-scale CI16, and prefix-boundary cases. The cache-size relationship is also
not asserted locally.

## Confirmed prepared-input tail overread

The optimized FP32 branch is unsafe at a terminal fine frame. Frame
availability accepts `start + symbol_start(w, 301) - 1 < sample_count`, which
is sufficient for the nonzero even-symbol template. It then unconditionally
loads `w->n` FP32 samples from `start` through `start + w->n - 1`; the
zero-template tail is still loaded. At the largest accepted start, the four
supported rates overread respectively 22, 45, 67, and 89 complex samples:

| Rate (Hz) | `w->n` | `symbol_start(301)` | overread complex samples |
| ---: | ---: | ---: | ---: |
| 2,500,000 | 3333 | 3311 | 22 |
| 5,000,000 | 6667 | 6622 | 45 |
| 7,500,000 | 10000 | 9933 | 67 |
| 10,000,000 | 13333 | 13244 | 89 |

`tests/test_fine_precision_tail_asan.c` constructs precisely that nearest
accepted, non-full frame for every rate. Its ASan command is
`tests/run_tail_asan.sh`; the current source aborts on its first (2.5 MHz)
case with a heap-buffer-overflow at `fine_precision.h:194`, the scalar
prepared-input load. The inherited partial tests use epoch zero and do not
reach this terminal boundary. This rejected experiment must not be promoted
without changing the availability check to the actual prepared-input span (or
only loading active spans) and rerunning the dedicated boundary test.
