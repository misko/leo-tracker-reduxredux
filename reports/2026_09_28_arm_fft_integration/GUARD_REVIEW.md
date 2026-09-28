# FFT coarse proposal guard review

## Scope and evidence

Reviewed `coarse_fft_proposal.h`, `full_search.c`, and
`test_fft_integration.c` against the conditioned-CZT host baseline and the
sealed coarse-FFT design.  The source keeps the 2.5-MS/s direct path and
selects FFT lengths 128, 128, and 256 at 5, 7.5, and 10 MS/s respectively.
The overlap-save output index is `j + taps - 1`; its reversed-conjugate
kernel matches the direct FP32 expression `sample * conjugate(template)`.

An isolated host build and qualification completed successfully on 2026-09-28:

```
python3 build.py --output /var/tmp/leo-fft-guard-host
```

The current all-rate fixture covers centered complex partial inputs at two
overlap boundaries, full 20-ms centered complex inputs, full zero inputs, a
forced direct fallback, and the high-dynamic-range condition fallback.  The
full nonzero cases retained the same top-eight inventory as the direct grid.
The independent `test_fft_edges.c` fixture additionally injects a dominant
zero-CFO anchor at epoch zero, the final epoch, and both sides of the 5-MS/s
overlap-save step (106 and 107).  Each direct maximum matched the injection,
retained inventory matched, and no fallback was taken.  These are host
qualification results only; they do not establish ARM or end-to-end dwell
performance.

## Guard disposition

The implementation now falls back to the complete direct grid if the bounded
repair loop has not converged after four passes.  Its final-selection comment
also identifies the `128 * FLT_EPSILON` test as an engineering acceptance
screen, not a formal bound.

This remains the material limitation: windows accepted without a direct
fallback are engineering-qualified proposal results, not a proof of exact
top-eight preservation.  The margin may support an empirical acceptance
record but cannot certify an omitted cell unless a conservative error bound is
established.

## Test gaps

The edge fixture now covers endpoint peaks and the specified 5-MS/s
overlap-save boundary.  Still add adjacent/tied maxima and a repaired cell
that moves the eighth separated boundary so an additional repair pass is
required.  Preserve the established linear local-peak edges, circular
separation distance, and stable CFO-bin then epoch ordering.

The implementation now includes a weak-local-window/high-dynamic-range test
and falls back when local received energy is below an engineering fraction of
the containing block's energy.  That is a useful containment rule, though it
is not a proof for all conditioning or FFT error cases.
