# Fusing fractional interpolation with pilot correlation

## Assessment

The transformation is mathematically valid for each symbol, reference, CFO,
fractional offset, and interpolation-fraction pattern.  It preserves the 64
per-symbol correlations consumed by the existing ceiling and FFT statistic; it
does not shorten the pilot support or remove exact/control evidence.

It is worth a bounded prototype because the current fractional path performs a
16-tap Lanczos interpolation for every pilot sample in every supporting frame.
The fused form applies a roughly `symbol_samples + 15` coefficient vector per
symbol and reference after a one-time coefficient build.  On the 2.5-MS/s
known-state path this should reduce the dominant inner arithmetic by roughly
2--3x, depending on coefficient-build amortization and NEON layout.  It is not
plausibly a 10x whole-replay change by itself: FFT, ceiling, coefficient setup,
state, conversion, discovery, and blind fallback remain.

The principal correctness risk is not the algebra.  It is that the current C
kernel deliberately uses the *actual rounded fractional part* of
`start + k + offset`.  That fraction can change when the integer position
crosses a floating-point binade.  A table built only from nominal `offset` may
therefore change interpolation weights, source support, scores, or the selected
residual-CFO bin.  The implementation must either key tables by the observed
fraction pattern or prove the pattern identical for every frame/sample using
the table and fall back otherwise.

## Algebra

For a reference `r`, symbol `s`, frame start `a`, template sample `k`, and
fractional offset `o`, define

```text
b_a(k) = floor(a + k + o) - a
f_a(k) = (a + k + o) - floor(a + k + o).
```

The existing correlation is

```text
C[r,s] = sum_k conj(T[r,k]) R[k]
                 * sum_(t=-7..8) L(f_a(k), t) x[a + b_a(k) + t]
```

where `R[k]` is the CFO rotation and `L` includes the current Lanczos weight and
its 16-tap normalizer.  Reindexing the finite sums gives

```text
h[r,s,j] = sum_k conj(T[r,k]) R[k] L(f_a(k), j-b_a(k))
C[r,s]   = sum_j h[r,s,j] x[a+j].
```

This is exact in real arithmetic.  Each symbol remains separate, so the
subsequent sum of 64 `cabs` values, 128-point FFT, accumulated spectra,
512-point interpolation, and exact-reference residual CFO are unchanged.
Exact and rolled-control references need different `h`, but can share the
Lanczos weights, input loads, and a two-lane complex-MAC loop.

The table must preserve the current division by the interpolation normalizer.
It must not normalize the complete symbol coefficient vector or merge adjacent
symbols.  Adjacent symbol supports overlap in IQ, but their correlations and
ceilings are distinct evidence.

## Work estimate

At 2.5 MS/s, a 4.4-us symbol contains 11 samples.  One frame's current
fractional interpolation performs approximately
`64 * 11 * 16 = 11,264` real-weight complex accumulations, followed by two
reference correlations over `64 * 11` samples.  A fused application reads at
most `11 + 15 = 26` samples per symbol and reference, or 3,328 complex MACs per
frame for both references.

The table build is not free.  It distributes each of 11 template samples over
16 taps for two references, approximately 22,528 complex coefficient
accumulations per 64-symbol region.  Final scoring alternates the early and late
regions under `LEO_PRESENCE_GLRT_SYMBOL_DIVERSITY`, so a typical 15-frame call
needs two region tables.  Amortized over roughly seven or eight frames per
region, the setup remains worthwhile but limits the arithmetic gain to a few
times rather than the raw 16-to-26-tap ratio.

At 5 MS/s, each symbol contains 22 samples and fused support is 37 samples.
There is more interpolation work to remove, but table construction also doubles.
Both rates need measurement; a single scale factor is unjustified.

In the final server development replay, 51 point-check attempts at 2.5 MS/s
measured 0.1599 ms mean native kernel CPU plus 0.0048 ms selective-conversion
CPU.  Accepted-hit all-in candidate service was about 0.206 ms per visit, versus
1.522 ms reference service on those visits.  Under the experiment's theoretical
four-cold-visits-per-64 lower bound, a 10x total needs cached service at or below
about 4% of blind service, roughly 0.061 ms.  A 2--3x improvement of only the
fractional inner loop is unlikely to reach that all-in target.  The actual
development replay made 240 blind calls in 256 receiver-visits, so even a
zero-cost fused hit would not materially approach 10x until cache coverage is
solved.

## Required semantics

The prototype should change only final fractional GLRT correlation.  Preserve:

- the integer-offset direct-sample branch, including the `1e-12` classification;
- the 16-tap range `[-7, +8]` and the per-fraction Lanczos normalizer;
- original early/late symbol selection and terminal late-to-early fallback;
- the left-seven/right-eight boundary checks and unsupported-frame stopping;
- all 64 symbol correlations for exact and control in their original order;
- libc `cabs`, ceilings, FFT sizes, spectrum accumulation, peak tie rule, and
  residual-CFO mapping; and
- selective CI16 conversion bounds and receiver stride.

The five integer epoch-lattice evaluations in blind acquisition do not execute
fractional interpolation and should remain on the existing path.  The fused
path targets the final fractional call and known-state point/local calls.  A
local timing recovery may evaluate four different offsets; coefficient setup
for every offset is part of its measured cost.

## Cache key and lifetime

A safe workspace-local cache key contains:

```text
rate/template identity, exact CFO bits, exact offset bits,
integer-vs-fractional branch, early/late region,
and the observed base-shift/fraction pattern
```

The workspace already owns fixed templates and rate, but source code should
still make those dependencies explicit.  Do not quantize CFO or offset to gain
reuse; that changes the statistic.  Exact `double` equality matches the current
rotation cache policy.

`epoch`, `count`, and frame index determine which regions are supported and
whether a late frame falls back to early.  They need not enter a coefficient
key only when the implementation verifies that every selected frame has the
same local base shift and fractional pattern as the table.  Otherwise use a
separate pattern table or the original loop.  Keep the cache per workspace;
sharing mutable tables between detector threads adds no useful reuse and risks
cross-call contamination.

For the common case, compute the actual fraction for every template `k` at the
first supported frame, then verify the corresponding fraction and
`floor(position)-start` for later frames before applying the table.  A mismatch
must choose a matching table or fall back.  This inexpensive verification also
handles positions that cross powers of two without assuming that local sample
counts are always too small to matter.

## Floating-point limits

Fusing changes summation order.  Current code first accumulates 16 weighted IQ
samples, divides once by the normalizer, multiplies by rotation, and then adds
template products.  A precomputed coefficient path distributes the division and
template product into each input coefficient.  Bit equality is therefore not a
reasonable general requirement, even with the same FP64 types.

The resulting differences matter in three places:

1. exact/control margin near the strict 0.025 research gate;
2. the 64-magnitude ceiling, where the source already warns that tiny changes
   can be amplified on flat non-pilot surfaces; and
3. the 512-bin peak and residual CFO, which feed cache identity and the 8-kHz
   innovation rule.

A prototype must report maximum absolute/relative errors for the 64 complex
correlations, ceilings, exact/control scores, margin, and residual CFO.  It must
also report FFT winner changes and gate changes, not just final pass counts.
If a conservative numerical error bound is established, ambiguous margins or
near-tied FFT peaks can fall back to the original kernel.  Such fallback cost is
part of the benchmark.  Without a bound, retain the fused path as a separately
qualified numerical implementation rather than claiming exact equivalence.

Compiler behavior belongs in the comparison.  FP contraction, NEON reduction
order, `-fcx-limited-range`, rounding mode, and FFT backend must be frozen for
both baseline and candidate.  Coefficients should be generated in FP64 first;
FP32 coefficients are a different experiment.

## Bounded prototype and tests

The first implementation can remain private to the research translation unit
and select the old/fused kernel at creation time.  A useful bounded sequence is:

1. Compare per-symbol complex correlations before the FFT on deterministic
   random, rail, impulse, pilot, tone, and noise inputs at 2.5 and 5 MS/s.
2. Cross offsets throughout `[-2, 2]`, including exact integers, values just
   inside/outside the `1e-12` integer rule, `nextafter` neighbors, and the
   offsets produced by local parabolic recovery.
3. Place frame/sample positions on both sides of every reachable binary binade
   boundary.  Verify fraction-pattern selection and the left/right support
   endpoints explicitly.
4. Cross CFO zero and the +/-400-kHz endpoints, early/late regions, terminal
   fallback, receiver strides for RX0/RX1, and frame limits 2/4/16.
5. Compare complete exact/control/margin/residual-CFO outputs and input
   immutability.  Require deterministic repeat output for each implementation.
6. Replay development and synthetic controls, listing every correlation, FFT
   winner, detection, identity, or cache-trajectory difference.  Freeze code,
   tolerances, and fallback policy before validation; do not use holdout to tune
   them.
7. Benchmark coefficient build, coefficient application, FFT/postprocessing,
   and total point/local/blind service separately.  Then use only the all-visit
   causal replay for the headline speed ratio.

The prototype should be abandoned if coefficient build plus two-reference
application does not clearly beat the current fractional loop on server before
an ARM port, or if preserving near-boundary numerical decisions requires enough
fallbacks to erase the gain.  A server win still requires a matched saved-IQ
Cortex-A9 measurement before any ARM claim.
