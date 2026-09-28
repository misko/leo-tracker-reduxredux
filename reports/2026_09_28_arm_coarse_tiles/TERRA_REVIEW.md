# FP32 coarse four-epoch tile review

This read-only review covers the current qualified FP32 path in
`reports/2026_09_27_plutoplus_static_arm/optimize/work/goal40mag/src/native_presence/coarse_fp32.h`.
It does not propose a new search geometry, run a benchmark, or change code.

## What is already cached

There is no remaining template-rotation work to remove.  Workspace creation
calls `coarse_fp32_templates()`, which computes `float_reference_energy` and
the 12-CFO, FP32 rotated-reference tables once.  `coarse_fp32()` only
normalizes incoming samples and evaluates the grid.  A four-epoch tile should
reuse those existing tables; it must not duplicate cache construction or alter
the fixed `symbol * 45 * 12 + 12 * tap + CFO` layout.

## Four-epoch tile invariant

The existing `coarse_float_add()` is vectorized across the twelve CFO
hypotheses (three NEON vectors).  For one `(symbol, frame, epoch)` it:

1. starts twelve real and imaginary FP32 accumulators at zero;
2. visits taps in ascending order and updates each CFO lane;
3. applies `coarse_magnitude()` and the already rounded FP32 inverse norm;
4. adds one result per CFO to that epoch's `float_accumulated` row.

Tiling four epochs may make four independent copies of those accumulator
chains live at once.  It must keep steps 1--4 in precisely that order *within
each epoch and CFO lane*.  In particular, it must not combine partial sums
from different epochs, vectorize a tap reduction across epochs, change a
multiply/add into an FMA, or accumulate a symbol/frame contribution in a new
order.  The expected result is equality with the current FP32+NEON kernel,
not equality with the scalar `sqrtf` fallback or the FP64 coarse oracle.

`coarse_magnitude()` deserves its own guard.  It protects zero squared
magnitude before `vrsqrteq_f32`, then executes exactly two
`vrsqrtsq_f32` Newton refinements and multiplies by the original squared
magnitude.  The tile should call that exact helper for every epoch's three
CFO vectors.  Replacing it with `vsqrt`, `sqrtf`, an extra or missing
refinement, or a reciprocal-square-root shared across lanes changes the
qualified FP32 result.

The denominator path remains FP64 until `inverse=(float)(1.0/denominator)`.
Compute each tiled epoch's `prefix[position+taps]-prefix[position]`, clamp,
`sqrt`, finite check, and cast independently.  A FP32 energy prefix or a
common normalization factor is not equivalent.

## Boundary and support risks

- The main scan limits `valid` separately for each `(symbol, frame)`, then
  advances by `epoch_stride(w)`.  A tile must cover
  `epoch, epoch+stride, epoch+2*stride, epoch+3*stride`; peel one to three
  remaining epochs at the end.  Do not assume stride one.
- Do not cross `valid`, `w->n`, or a frame's `position+taps <= count` limit.
  `coarse_fp32_cell()` performs sparse local refinement with the same bounds;
  keeping it on the single-epoch helper initially is the least risky choice.
- `coarse_fp32_add()` increments `support[epoch]` even when the denominator is
  zero.  A tile must preserve that increment for every valid symbol/frame
  contribution.  Skipping it changes the grid denominator.
- A wholly zero dwell is a distinct early return: it writes every grid cell as
  `0.0` and never enters the add path.  Preserve this result and do not emit
  `-INFINITY` from untouched support rows.

## Targeted qualification

Add a native unit comparison of the tiled helper against the current
single-epoch NEON helper, with a bytewise FP32 comparison of the twelve
updated accumulation values and support counts.  Exercise four aligned
epochs plus 1-, 2-, and 3-epoch tails.  Include known zero, 3-4-5-like,
very small, and large finite real/imaginary lane values so the zero-safe
reciprocal-square-root path and both Newton refinements are exercised.  The
comparison should be compiled for ARM NEON; comparing only against the scalar
fallback would test a different square-root implementation.

At the workspace level, test all 2.5, 5, 7.5, and 10 MS/s geometries with:

1. all-zero IQ, asserting the full `12 * w->n` grid is finite zero;
2. nonzero IQ containing zero-energy symbol/frame regions, asserting tiled
   and untiled grids plus support counts match;
3. counts at the minimum valid geometry and at the final valid epoch for each
   symbol/frame, including tile tails and sparse `coarse_fp32_cell()` calls;
4. deterministic CI16-like full-scale and low-amplitude data, checking every
   coarse FP32 grid cell against the untiled NEON path before peak retention.

Only after those tests should corpus qualification compare coarse candidate
rank/order, the retained eight, fine and conditioned CFO, and final
exact/control GLRT across all four rates.  The previously observed FP32 coarse
basin change makes retained-eight and final outputs necessary acceptance
metrics even when grid-cell numerical differences are small.

## Implementation audit (current tile source)

`coarse_fp32_add4()` is called only for `epoch_stride(w) == 1`; it peels the
remaining one to three epochs through the original helper.  Its
`epoch + 3 < valid` guard is sufficient for the `vld2q_f32` load at the final
tap: all four complex samples from `position + tap` through
`position + tap + 3` remain inside the input.  CFO coefficient loads and the
four epoch-major accumulation rows are likewise in bounds.  I found no other
layout or per-epoch arithmetic error in `coarse_tile.c` or the tiled header.

The ARM branch of `test_coarse_tile.c` currently places its `STORE` operations
inside the tap loop.  That reference accumulates an intermediate magnitude
once per tap and is not the single-epoch kernel it intends to reproduce; move
the stores after the tap loop before treating its NEON result as a parity
check.  The scalar host reference has the intended scope, so a host pass does
not exercise this ARM-only mistake.

The full-grid byte comparison covers all four rates, two finite input lengths,
and an all-zero dwell.  It does not expose support counts directly.  A tile
unit or debug hook should also compare support arrays for a mixed-energy case,
where a zero denominator still increments support, before relying on grid
equality alone.
