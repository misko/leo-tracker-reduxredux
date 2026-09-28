# Cross-window coarse-search reuse review

## Decision

Do not make a large strict cross-window magnitude cache the next ARM change.
The geometry can remove nearly half of the normalized dot products when the
normalization is shared, but the current per-window peak normalization is
identical for only about 34% of adjacent saved-window pairs.  The resulting
strict opportunity is roughly 15--16% of dot work before cache traffic,
bookkeeping, cache misses, and the still-required prefix work.  That is not a
credible route from a 34.33-second dwell toward the requested one-core 40%
headroom.  The separately measured four-epoch lane kernel is bit-exact but
slower (1,746.50 ms versus 1,559.84 ms for the latest CZT build, about 12%).
It is therefore not a priority either; retain its parity result and stop
spending optimization effort there.

This review is read-only with respect to the sealed source snapshots.  It
examines `/var/tmp/leo-arm-conditioned-czt-v3`, whose `cohort_probe.c` forms
eleven 20-ms probes per receiver from a 120-ms dual-CI16 dwell at a 10-ms
stride.

## What the current statistic actually computes

`coarse_fp32()` first finds a *window-local* maximum component `scale`, then
forms `float_samples[k] = (float)(samples[k] / scale)` and an FP64 energy
prefix over those double normalized values.  For every anchor symbol, coarse
frame, and epoch it:

1. computes 12 FP32 complex correlations and their FP32 magnitudes;
2. derives the symbol energy as the FP64 subtraction
   `prefix[position+taps] - prefix[position]`;
3. converts the resulting inverse norm to FP32; and
4. adds the normalized 12-bin result to the FP32 grid accumulator in its
   current symbol/frame order.

The source has 12 CFO lanes (`CFO_COUNT`), though the public coarse-grid copy
and full-search peak scan expose the first 11.  Any cache must retain all 12
internal lanes; treating the twelfth as padding would change the kernel.

At rate `R`, each 20-ms window searches `n = ceil(R/750)` sample epochs.  The
16 frame offsets are `nearbyint(frame * R/750)`, and a frame contribution is
at

```
window_start + anchor_start[symbol] + nearbyint(frame * R/750) + epoch
```

The 10-ms window stride is not an integer number of frame periods (7.5
frames).  Thus an overlapping raw correlation generally reappears under a
different `(frame, epoch)` pair.  It must be addressed by its global sample
position, never by assuming `epoch` or `frame` has a fixed adjacent-window
shift.  This matters especially at 2.5 and 7.5 MS/s, where rounding of
`nearbyint(frame * R/750)` supplies the boundary samples.

Ignoring normalization, the sixteen adjacent frame intervals plus the epoch
extent cover approximately 21.33 ms in a window.  Advancing 10 ms makes their
raw-correlation coverage overlap by approximately 11.33 ms, so a 120-ms
eleven-window dwell has about 1.8--1.9x as many independent correlation
positions as one could obtain by evaluating each window separately.  This is
the attractive upper bound, not an exact speed prediction.

## Exact cache design, if it is later justified

The reusable unit is the **unnormalized FP32 magnitude produced by one call to
the current dot loop**, addressed by:

```
(receiver, scale bit pattern, symbol, CFO lane, global sample position)
```

For a hit, retain the cached magnitude and perform the current window's FP64
prefix subtraction, `sqrt`, FP32 inverse conversion, and FP32 grid add in the
same symbol/frame traversal order.  This preserves the statistical operation
and avoids changing the accumulator's summation order.  It also correctly
handles the same raw position being needed as, for example, frame 7 in one
window and frame 0 or 1 in the next.

The cache may be valid only when the scale values compare bit-identically.
With equal scale, conversion of the same CI16 sample through the existing
double division and float cast is the same, and the raw FP32 dot/magnitude can
be reused.  The per-window FP64 prefix must still be built from the window's
own start and subtracted locally.  A prefix over the 120-ms dwell followed by
subtraction is *not* exact: binary64 summation rounds at different points, so
the subtraction can change `received`, the FP32 inverse norm, and ultimately
the ranked grid.

Likewise, caching normalized scores is invalid: their denominator is local to
each symbol/frame/window.  Caching a final per-epoch sum is invalid both
because frame membership differs at the 7.5-frame shift and because its FP32
addition order is observable.

An implementable bounded form is a two-window ring, one receiver at a time.
Store only the prior window's overlap tail, plus its scale bit pattern and a
global-position origin; on a scale mismatch, discard it and execute the
ordinary dot path.  Do not allocate a 120-ms by symbol by CFO cache.  At
10 MS/s, a float magnitude cache for all 12 symbols and all 12 lanes over the
11.33-ms reusable tail is about 65 MB per receiver; retaining the complete
previous 21.33-ms correlation interval is about 123 MB.  Metadata, alignment,
and coexistence with the existing FP32 sample workspace make the latter an
unattractive default on the target.  A ring also keeps the maximum additional
memory bounded by rate rather than dwell duration.

Qualification must compare every 11-window, two-receiver coarse grid byte for
byte, at all four supported rates, against the current FP32 baseline.  Cases
must include zero windows, scale changes, a single scale-stable adjacent pair,
longest observed stable runs, and both sides of every frame/epoch rounding
boundary.  The current all-rate grid parity fixture is useful for the inner
kernel but does not exercise the cross-window global-position map.

## Measured strict gate

`scale_reuse.py` measured exact integer peak scales on the 704-dwell saved
DS7 inventory.  Adjacent pairs are counted separately for each receiver:

| Rate | Dwells | Adjacent receiver-pairs | Equal scales | Fraction |
|---:|---:|---:|---:|---:|
| 2.5 MS/s | 152 | 3,040 | 1,027 | 33.7829% |
| 5 MS/s | 216 | 4,320 | 1,471 | 34.0509% |
| 7.5 MS/s | 184 | 3,680 | 1,250 | 33.9674% |
| 10 MS/s | 152 | 3,040 | 1,034 | 34.0132% |

No receiver had all eleven windows at one scale.  Multiplying the roughly
48% geometric overlap by the roughly 34% scale-stable edge rate gives only
about 16% raw-dot avoidance in the optimistic independent-edge estimate.  It
is lower for broken runs and does not include lookup or memory cost.  The
strict cache therefore cannot support a claimed near-1.8x coarse reduction.

## Larger, approximate/requalified path

A power-of-two normalization chosen for each input type could make CI16 to
normalized-double conversion exact in binary and allow raw magnitudes to be
shared across all windows.  It would remove the scale gate and could approach
the geometric coarse reduction; if coarse dominates, the rough dwell-level
projection is about 1.35x rather than enough by itself for the headroom goal.

It is **not** exact relative to the present FP32 baseline.  Changing the
normalization changes the float cast and dot rounding even where normalized
real values are mathematically scale invariant.  This is a new detector
variant, requiring the full scientific parity/recovery qualification and a
guarded fallback to the current window-local path until it passes.  A safe
rollout would cache/reuse only under an explicit variant flag, run the current
kernel for every guard or mismatch, and publish no performance claim until
all-window candidate ordering and final decisions are rechecked.

The prioritization is therefore: do not advance the slower epoch-four lane;
retain the strict cache design as a later, bounded experiment; consider the
power-of-two variant only if a more promising coarse-search redesign still
leaves a deficit large enough to justify a new qualification campaign.
