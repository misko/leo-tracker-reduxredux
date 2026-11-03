# Coarse interval source audit and next experiment

This is a read-only audit of frozen
`full_search_reference.c` SHA-256
`b1b74aecd47b730f214f8d44061a42a5d3200579220b017ab99301641633cb25`.
It does not attribute CPU within the 46.0-second coarse interval by inference;
the current timer encloses the complete coarse function.

For each receiver in visit 301, the corrected geometry has 21 CFO bins,
10,000 epochs, 12 anchors, at most 16 frames, and 33 taps per symbol. Applying
the frozen frame bounds gives 1,742,196 valid anchor/frame/epoch iterations,
57,492,468 energy-tap iterations, 1,207,341,828 CFO-tap correlations, and
36,586,116 interval-bound contributions. The two receiver rows double those
counts. These are source-derived call counts, not a timing attribution.

The coarse path contains no FFT execution or FFT planning. FFT work starts in
the separately measured acquisition stage. Trigonometric work constructs the
rotated reference once per anchor/tap/CFO: only 8,316 `sincos`-eligible points
per receiver. Frontier allocation and sorting happen after the full grid and
cover about 41,000 possible cells per receiver; exact repair touched 24 cells
per receiver. These operation counts make FFT planning, coefficient rotation,
and exact-cell repair poor explanations for the 46-second stage without a
contrary measurement.

The hot scan performs, per valid anchor/frame/epoch:

1. one 33-tap received-energy sum;
2. one FP32 correlation across all 21 CFOs, vectorized four CFOs at a time;
3. one denominator square root;
4. 21 magnitude square roots, divisions, accumulations, and outward interval
   updates.

The final ARM DSO imports `nextafter@GLIBC_2.4`; disassembly contains a PLT call
inside the interval-bound update. That call site can execute up to 36,586,116
times per receiver for visit 301. This establishes a measured-work candidate,
not its share of elapsed time. The correlation loop still performs over 1.2
billion CFO-tap iterations per receiver and may remain dominant.

Existing experiments already reduced this same work without changing science:

- four-CFO register accumulation preserved every non-timing field over the
  frozen host panel and reduced representative ARM coarse time about 26.6%;
- certified FP32 interval screening repaired about 24 cells per row, preserved
  the 80-call host panel, and reduced the earlier three-call ARM CPU total
  16.2% from register-four and 33.3% from scalar;
- corrected 21-bin visit 301 remains much larger: 46,015.884 ms coarse CPU for
  both receiver rows.

The smallest next isolated experiment is an exact-bit replacement of only the
hot positive-finite `nextafter(value, +INFINITY)` interval-contribution call.
A local helper can increment the binary64 representation for positive finite
values, including the explicit `+0` case, while leaving every other outward
rounding call and the correlation arithmetic untouched. This is worth testing
because it removes tens of millions of ARM PLT/libm calls without pruning a
cell or changing a tolerance. It must not be promoted based on source counts.

Required evidence for that experiment:

1. bit equality with libc `nextafter` for zero, subnormals, normal boundaries,
   powers of two, adjacent values, maximum finite input, and deterministic
   random nonnegative finite values;
2. sanitizer coverage and a proof/assertion that the specialized call receives
   only finite nonnegative values;
3. byte-exact non-timing output for visit 301 and the corrected 32-visit panel,
   including candidate order, all gates, interval telemetry, and fallback;
4. physical ARM A/B timing of the same visit 301 artifact before deciding
   whether correlation needs a separate optimization.

If the helper does not materially reduce physical coarse time, the next
profiler should time broad kernels by A/B isolation or sampling rather than
placing clocks inside the epoch/tap loops. The subsequent target would be the
21-CFO correlation kernel, preserving each CFO's tap summation order and the
interval certificate. No fixed-K pruning, coarser grid, reduced anchor set, or
relaxed certificate is justified by this audit.

