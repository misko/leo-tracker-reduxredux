# Review of retrospective causal-region coverage

`coverage.py` is correctly labeled as an optimistic retrospective region
coverage calculation.  It is not a detector, a candidate-reuse implementation,
a GLRT recovery measurement, or a runtime measurement.

For each receiver within one saved dwell, probe zero and every periodic refresh
probe are given the complete original-oracle candidate list.  A non-refresh
probe retains an already-known oracle candidate only if its epoch/CFO lies in
a region centered on candidates from the preceding probe.  Retained negative
candidates may seed the next probe, while a candidate outside a retained
region cannot seed.  This makes the chain causal within the 11 probes of a
dwell, but it resets at every dwell and does not evaluate the proposed
previous-dwell state transfer.

The result therefore assumes the hard parts of a local search: it has the
original candidate identities, their precise epochs/CFOs, their margins, and
no false local candidates.  It neither executes the narrow port nor tests
whether its output survives final exact scoring/GLRT.  `covered_hits` means
oracle positive candidates lying in an available region; it is not recovered
detector hits.  The useful conclusion is limited to whether a causal-region
idea may merit implementation.

## The reported 90% point is still infeasible

For 2.5 MS/s, the selector's lowest-full-window method reaching 90% oracle
region coverage is refresh every two probes, radius two samples, and 8 kHz
CFO radius.  It covers 4,148 of 4,573 oracle positive candidates (90.71%) but
still marks 1,824 of 3,344 windows as full: **54.55%**.  Even if every local
window were free, applying the measured 33.913 CPU-s/dwell exhaustive cost in
that proportion leaves about 18.5 CPU seconds per 120-ms dwell, roughly 257×
the 72-ms 60%-CPU budget.  It cannot establish a real-time route.

The best listed 80% point likewise requires 1,260 full 2.5-MS/s windows
(37.68%) for 82.27% oracle region coverage.  This remains far above the
fallback allowance derived from the budget: at most 4.7% of dwells may afford
one exhaustive window with no other work, equivalent to 0.212% of all window
opportunities.  Actual local confirmation work makes that allowance smaller.

## Timing-coordinate issue to resolve before using the percentages

The native coarse grid has an integer period `n = (rate + 375) / 750`; at
2.5 MS/s this is 3,333.  The coverage script instead passes `rate / 750`
(3333.333...) as the period to `distance`.  Its test deliberately makes a
25,000-sample (10-ms) shift exact under that fractional period.  The native
epoch coordinate is an integer grid with rounded frame offsets and uses `w->n`
for circular epoch separation, so that equality is not yet justified for
candidate propagation.

Before treating the numeric coverage points as even optimistic evidence,
validate the exact next-window epoch transform on recorded candidate objects
or rerun with the native integer grid convention.  This may worsen coverage;
it cannot validate detector recovery.

The appropriate next step remains a bounded causal implementation with exact
final scoring/GLRT, a direct fallback, complete fallback accounting, and
80%/90% individual-hit recovery measured against the frozen baseline.
