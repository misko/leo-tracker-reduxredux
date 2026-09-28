# Bounded shared-input overlap-save FFT bank for coarse acquisition

## Decision and scope

This is a design review, not an implementation or a performance claim.  An
overlap-save FFT bank is a more plausible coarse-search direction than the
now-measured-slower epoch-four lane kernel: it can share each input transform
across the 132 public coarse filters (12 anchor symbols by 11 scored CFOs).
It changes the FP32 arithmetic, so it is an approximate proposal stage only.
Every retained candidate must be repaired with the present direct kernel
before it can affect the final top-eight inventory.

The proposal applies to one normalized 20-ms receiver window at a time.  It
does not reuse IQ across windows, alter the 16-frame/epoch geometry, or change
the later fine, conditioned, and GLRT stages.  This bounds live state and
keeps a direct fallback available.

## Reference workload and operation model

The current FP32 coarse path has 12 symbols, 16 frame offsets, and
`n = nearbyint(rate / 750)` epoch positions.  This is also the integer count
formed by `(rate + 375) / 750` for the supported positive rates.  The scored
public bank has 132 symbol/CFO filters.  At the four supported rates, a filter's tap count is 11,
22, 33, or 44.  Ignoring end-of-window truncation, the full-window reference
count is `132 * 16 * n`; it is 7,039,296; 14,080,704; 21,120,000; and
28,159,296 at 2.5, 5, 7.5, and 10 MS/s respectively.  The corresponding
public direct-correlation work is:

| Rate | `n` | Taps | Nominal complex MACs/window |
|---:|---:|---:|---:|
| 2.5 MS/s | 3,333 | 11 | 77,432,256 |
| 5 MS/s | 6,667 | 22 | 309,775,488 |
| 7.5 MS/s | 10,000 | 33 | 696,960,000 |
| 10 MS/s | 13,333 | 44 | 1,239,009,024 |

The actual direct loop evaluates the internal 12th CFO lane as well and
truncates invalid end geometry.  The table is deliberately the public
132-filter comparison requested for this bank, rather than a claim of exact
executed instruction count.

Choose the fixed FFT lengths `B = 64, 128, 256, 256` for tap lengths
`11, 22, 33, 44`.  The useful overlap-save output spans are
`H = B - taps + 1 = 54, 107, 224, 213`.  A simple radix-2 operation model
assigns about `5 B log2(B) + 6 B` real operations to one filter's spectral
multiply plus inverse transform, and `8 H taps` to the same useful direct
complex MAC outputs.  It gives the following *operation-model* ratios:

| Taps | FFT length | Useful outputs | Direct model | FFT model | Direct/FFT |
|---:|---:|---:|---:|---:|---:|
| 11 | 64 | 54 | 4,752 | 2,304 | 2.06x |
| 22 | 128 | 107 | 18,832 | 5,248 | 3.59x |
| 33 | 256 | 224 | 59,136 | 11,776 | 5.02x |
| 44 | 256 | 213 | 74,976 | 11,776 | 6.37x |

This is only a reason to microbenchmark.  It excludes FFT planning/setup,
cache behaviour, scalar/NEON implementation quality, magnitude and prefix
normalization, grid scatter, boundary blocks, and the direct repair work.
The current direct kernel is highly small-loop optimized, whereas a 64-point
complex FFT has substantial fixed overhead.  No wall-time or dwell-speed
estimate should be promoted from these ratios; actual single-core ARM timing
must be the gate.

## Numerical indexing evidence, deliberately limited

`grid_prototype.py` validates the reversed-conjugate FIR indexing on four saved
2.5-MS/s receiver probes.  It uses NumPy double-precision full convolution
with FP32 operands, then the existing FP64-prefix/FP32-accumulation model.  It
is neither a float overlap-save implementation nor an ARM benchmark.

Across its four 36,663-cell grids, the largest absolute grid difference from
the saved direct reference was `1.28585301129025e-07`; all four retained
eight-peak inventories matched.  With the experiment's `128 * FLT_EPSILON`
score guard, each probe selected eight high cells and 24 cells after adding
their local epoch neighbours, and each reference peak was inside that guard.
This supports the stated convolution orientation and makes the bounded repair
set plausible on these probes.  It does not provide an error bound for a float
FFT, other rates, unseen IQ, or exact top-eight preservation; the fallback
rules below remain required.

## Bank layout

For each symbol/CFO pair, construct the existing rotated template as a
reversed conjugate convolution kernel:

```
h[q] = conjugate(template[taps - 1 - q])
```

where `template` includes the existing CFO rotation and has its current tap
length.  An overlap-save block is the normalized complex input with `taps-1`
history samples.  For a desired direct correlation at input position `i`, its
convolution output is read at `taps - 1 + i` in the block's linear-output
coordinate.  This index rule, rather than an implicit FFT shift convention,
must be unit tested against the direct complex result.

For each input block:

1. take one forward FFT of the normalized input block;
2. multiply that spectrum by each precomputed reversed-conjugate kernel
   spectrum;
3. inverse transform one filter at a time;
4. read only the valid `H` outputs, calculate the coarse magnitude, and scatter
   it to every matching `(symbol, frame, epoch)` cell; and
5. discard the inverse output before processing the next filter.

The forward input spectrum is therefore shared by all 132 filters.  Kernel
spectra can be precomputed once per workspace.  Inverse buffers should stream
directly into the existing coarse accumulator, avoiding a bank by full-window
output tensor.  At 10 MS/s the 132 length-256 complex kernel spectra require
about 270 KiB if stored as complex float, so the bank itself is modest; the
dangerous allocation is an unnecessary `filters * full-window-positions`
output array, which must not be made.

The same global input coordinate must feed the present rounded schedule
`anchor_start + nearbyint(frame * rate/750) + epoch`.  Build this schedule
explicitly for each rate and map only valid output indices.  It prevents the
7.5-frame timing relation from becoming an unreviewed FFT index shift.

## Exact-result guard and fallback

An FFT result will not be bit-exact with the present FP32 time-domain dot
order.  Therefore it may rank coarse cells only as a proposal.  The final
coarse grid used for NMS must be repaired by the existing direct FP32 kernel
for every provisionally high-scoring cell and its local epoch neighbours
before NMS and top-eight separation.

The bounded guard should be:

1. form the approximate grid and collect a generous deterministic candidate
   set: all local maxima plus neighbours whose approximate score is within a
   configured margin of the eighth provisional score;
2. recompute those cells with the original direct symbol/frame/tap arithmetic,
   local FP64 prefix subtraction, FP32 inverse conversion, and original
   accumulation order;
3. run NMS/top-eight only on repaired values if the guard has a demonstrated
   error envelope; otherwise run the full direct coarse grid for that window;
4. record whether the direct fallback occurred and never hide it in a timing
   average.

Recomputing merely an empirically chosen top-K set cannot prove preservation
of the exact top eight: an omitted cell can be lifted by FFT error.  Exact
preservation requires either a validated conservative bound that includes all
cells capable of crossing the repaired eighth score, or the full direct
fallback whenever that bound is unavailable or ambiguous.  This distinction
must remain explicit in any future report.

## ARM qualification microbenchmark before implementation expansion

Use one bounded prototype and measure it on CPU0 at all four rates against the
latest CZT build.  Report separately: forward FFT count, inverse FFT count,
spectral products, direct-repair cell count, fallback count, coarse CPU, and
end-to-end 11-window/two-receiver dwell CPU.  Test at least random inputs,
zero inputs, saved windows near the selection boundary, and the full saved
cohort.  The acceptance record must compare exact repaired top-eight ordering,
coarse epochs/CFOs, and final candidate decisions with the direct baseline.

Proceed only if the ARM measurement shows a material end-to-end gain after
guard repairs and no unaccounted ambiguity.  Otherwise retain the direct
coarse kernel; its current bounded memory behaviour and established parity are
more valuable than an unmeasured FFT operation-count advantage.
