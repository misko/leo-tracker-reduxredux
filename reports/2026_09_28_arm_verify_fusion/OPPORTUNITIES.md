# Bounded 2.5-MS/s opportunity review

This review reads `/var/tmp/leo-host-screen-rotation-v1` only.  It does not
change the selected source, start a benchmark, or claim a speedup.

## What the present coarse loop can and cannot share

At 2.5 MS/s, `n = nearbyint(rate / 750) = 3,333` and each of the twelve
anchor-symbol templates has eleven taps.  `coarse_fp32` evaluates up to 12
symbols × 16 frames × 3,333 epochs = 639,936 normalized dot positions per
20-ms receiver window.  Each position evaluates all 12 internal CFO lanes,
so its nominal inner work is 639,936 × 12 × 11 = **84,471,552 complex
multiply-accumulate terms** before magnitude, support normalization, and
edge truncation.  The public inventory reads eleven CFO rows; the twelfth lane
is still evaluated by the qualified vector kernel.

The prefix-energy denominator is already O(1).  The remaining repeated input
windows differ by epoch, symbol start, and rounded frame offset.  More
importantly, each symbol/frame contribution is normalized by its own received
energy and its magnitude is added before the epoch's final support division.
Therefore the terms cannot be summed or folded across frames before magnitude
without changing the statistic.  A direct sliding FIR recurrence needs an
arbitrary eleven-tap update and does not remove the twelve CFO correlations.
An FFT proposal for this eleven-tap case was already measured as a poor
candidate and is not reopened here.

This leaves ordinary implementation improvements (load layout, small-kernel
instruction scheduling, or cache behavior) with a bounded ceiling: they act
on one eleven-tap kernel, not on the number of hypotheses.  They cannot remove
the 22 exhaustive 20-ms searches in a 120-ms dual-RX dwell.

## Exact final-score fusion is the useful local change

For every retained full-search candidate, `full_search.c` calls
`normalized_score` three times at the same epoch and CFO:

1. exact template on the even-symbol acquisition set;
2. exact template on the odd-symbol verification set; and
3. control template on that same odd-symbol verification set.

At 2.5 MS/s the 300 pilot symbols span essentially all 3,333 samples; each
parity set is about half.  The present three calls consequently process about
`1.5 n` selected samples per supporting frame.  A fused routine can traverse
the pilot frame once, keep three independent accumulators and energies, and
perform about `n` selected-sample operations.  That removes at most one third
of this verification scan and its duplicate phasor/template construction.  At
the maximum eight candidates and fifteen complete frames in a 20-ms window,
the arithmetic count falls from about 599,940 selected sample visits to
399,960: **about 199,980 visits avoided per window**.

The fusion is algebraically straightforward only if each accumulator preserves
the existing increasing-symbol/increasing-sample order, retains each separate
normalization and empty-support result, and retains the existing tie and final
candidate ordering.  It still changes floating-point execution and must be
qualified against complete candidate objects.  It reduces verification work;
it does not reduce the coarse grid, conditioned search, or final GLRT, so it
cannot be presented as a real-time solution by itself.

## Required algorithmic shift

The recorded screen-rotation result is 33.913 CPU seconds per 120-ms dual-RX
dwell.  The 60%-CPU continuous budget is 72 ms/dwell, leaving a **471×** gap.
Even the impossible ceiling of eliminating ten of eleven exhaustive windows
per receiver only reduces exhaustive coarse work by 11×, still far short of
that gap.  Local kernel and verification changes therefore cannot plausibly
reach real time while preserving exhaustive all-window coverage.

The bounded next experiment should be a *causal previous-window/dwell
candidate reuse* evaluation, not a kernel rewrite:

1. Order each recording by capture time and seed a window only from candidates
   emitted by earlier windows/dwells in that recording.  Reset state on a gap,
   rate/edge change, or failed confirmation; never use a later window or the
   offline baseline as a seed.
2. Translate a prior epoch by the known 10-ms window advance and use its prior
   tracking CFO only to center a narrow local confirmation port.  Run the
   unchanged exact final scoring and GLRT for every proposed seed.
3. Define an explicit confidence failure and make it run the current complete
   exhaustive search.  Log every fallback, seed age, candidate count, and the
   exact work submitted to the confirmation port.
4. Score individual-hit recovery against the frozen original baseline, using
   the existing two-sample epoch and 8-kHz tracking-CFO matching rule.  Report
   causal 80% and 90% recovery operating points separately, plus added hits,
   delayed recovery, and fallback-conditioned recovery.

For scale, exhaustive 2.5-MS/s coarse work is roughly 22 × 84.5 million =
**1.86 billion nominal complex MAC terms per dual-RX dwell**.  A stateful
confirmation path with two seeds for every one of the 22 windows would enter
only 44 final-confirmation candidate paths; using the current 64-symbol,
eleven-sample-symbol, roughly fifteen-frame final GLRT gives an
order-of-magnitude raw correlation floor near 0.93 million template MAC terms
before FFTs, local acquisition, and bookkeeping.  That comparison motivates
measuring the causal port; it is not a wall-time estimate and does not
establish recovery.

Fallback frequency is the hard constraint.  With no other cost at all, a
33.913-s exhaustive dwell could occur in under 0.212% of dwells to fit a
72-ms average budget.  At the simple `33.913 / 22` per-window allocation, one
exhaustive 20-ms window costs that same 72-ms budget: it can occur in at most
4.7% of **dwells**, equivalently 0.212% of all 22 window opportunities.  Real
confirmation work lowers both limits.  The causal experiment must report this
distribution before any real-time claim.
