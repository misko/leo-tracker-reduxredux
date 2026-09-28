# Sparse coarse implementation review

Reviewed the final proposal path in `full_search.c`, its unit coverage, and
`score_cohort.py`. This is an approximate candidate-proposal implementation;
only cells that are repaired before the ordinary peak scan have exact coarse
scores.

## Coarse proposal and repair

The proposal initializes input scaling and prefix energy exactly as
`coarse_fp32`: scale is the maximum component magnitude, samples are converted
to FP32 after division by that scale, and prefix energy retains FP64 addition
order. Each selected `(symbol, frame, epoch)` calls `coarse_fp32_add`, so it
uses the original template energy, per-position received energy, inverse
normalization, complex accumulation, and support increment.

Selected indices are `floor(i*12/S)` and `floor(i*16/F)`. They use the same
`starts[symbol] + offsets[frame]` geometry as the complete path. The valid span
is the same `count - taps + 1 - base`, capped at `n`; selected later frames may
be skipped on partial input, just as the complete monotonic-frame loop stops
after the first unsupported frame. This preserves the four native tap spans
(11, 22, 33, and 44 samples at 2.5, 5, 7.5, and 10 MS/s) and the rounded frame
offsets, including 7.5 MS/s.

For every retained proposal centre, the `±2` union is cleared and rebuilt with
the unchanged `coarse_fp32_cell`. That recomputes all 16 frames, all 12 anchor
symbols, and all 12 internal CFO lanes in the original per-cell addition
order. The sparse test compares every eligible repaired public-grid cell with
a fresh full `coarse_fp32` result using exact equality, across all four rates,
minimum accepted partial inputs, full 20-ms inputs, and zero inputs.

## Boundaries, zero input, and failures

The final eligibility mask does not use circular neighbors: an interior cell
requires its repaired left, centre, and right cells; endpoint 0 requires 0 and
1, and endpoint `n-1` requires `n-2` and `n-1`. This matches the frozen
local-maximum scan's outside-grid `-INFINITY` behavior. It avoids turning an
unrepaired neighbor into a fabricated edge peak. The helper and all-rate
endpoint injection exercise this behavior.

All-zero input clears the complete 12-lane grid and makes every epoch eligible,
matching the direct path's zero grid and its no-peak outcome. The 16-frame /
12-symbol control bypasses sparse proposal, calls the complete direct coarse
routine, marks all epochs eligible, and requires byte-exact public-grid parity.
Allocation failure in the proposal peak or scratch storage falls back to the
complete direct coarse routine with all epochs eligible. The outer routine's
ordinary allocation failure behavior is unchanged.

## Cohort scoring

The scorer imports the frozen maximum-cardinality matcher. It associates only
within one 20-ms receiver/probe window, with the frozen `<=2` sample and
`<=8 kHz` gates, preventing one native candidate from recovering two reference
hits. It accepts zero-candidate windows while retaining their 22-window
inventory check. It now also requires `glrt_complete == 1` for every emitted
candidate before reporting `actual_candidate_glrts`; the implementation runs
GLRT over every candidate after candidate ordering, so this validation makes
the label reflect the serialized evidence.

## Residual limitations and recommendation

No defect was found in support, normalization, eligibility, zero handling, or
the reviewed direct-repair path. The proposal remains unguarded approximation:
a full-grid peak outside one of the 32 selected `±2` neighborhoods is omitted,
and no numerical error bound establishes its recall. Cohort hit recovery is
therefore the admission measure, not repaired-cell parity.

The endpoint regression establishes that each injected endpoint becomes
eligible. It would be stronger to also prove that an injected endpoint is a
local maximum in a direct full grid and is present after the actual
eligible-scan and NMS retention path. That is a focused test improvement, not
evidence of a current implementation failure.
