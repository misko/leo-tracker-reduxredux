# Frozen B: diagnosis of the five full-recording fitted-c results

Written 2026-10-17 from the five saved `results/S0*-full-fitted-c-B.json`
records, their original and continuation counterparts, and the frozen source.
This diagnosis does not change B, refit an endpoint, read new RF data, or select
parameters using the temporal or c=0 results. It concerns the development
full-recording fitted-c arm only; it does not establish excluded-data gains or
a fitted-c versus c=0 effect.

The common result is negative: B retains 11,222/20,084 associations (55.875%),
and 96/693 challenge associations, exactly the original counts. Four recordings
return their original states. S03 retains a lower-objective research iterate,
but its frequency likelihood and RMS worsen and it is strongly nonstationary.
There is no demonstrated association or localization improvement from B here.

## Track coverage and posterior concentration

Every row belongs to exactly one segment, so coverage is 100% and evidence is
not multiplied by overlapping segment windows. The useful measure of shared
identity coverage is the fraction of rows in segments with at least two points.
Singleton count is `tracklets - multi_point_tracklets`; all remaining rows
belong to the multipoint segments.

| Scan | Rows | Segments | Multipoint segments | Rows in multipoint segments | Mean multipoint length | Mean initial max-identity posterior |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S01 | 4,797 | 1,289 | 716 | 4,224 (88.06%) | 5.90 | 0.3518 |
| S02 | 3,524 | 1,173 | 649 | 3,000 (85.13%) | 4.62 | 0.4375 |
| S03 | 3,988 | 1,416 | 649 | 3,221 (80.77%) | 4.96 | 0.6915 |
| S04 | 3,719 | 1,280 | 635 | 3,074 (82.66%) | 4.84 | 0.5935 |
| S05 | 4,056 | 1,300 | 711 | 3,467 (85.48%) | 4.88 | 0.5886 |

Across the corpus, 16,986/20,084 rows (84.57%) are in multipoint segments.
Insufficient track construction is therefore not the main explanation for the
negative result. Segment lengths are capped at 24 points and durations at 45 s;
the longest segment in every scan reaches the point cap. The average segment
is still short, and independent segments do not share identity globally across
gaps, channels, or receiver lanes.

The saved mean maximum identity posterior averages over segments, not rows, and
excludes the all-clutter class from the maximum. A low value can therefore mean
clutter rather than uncertainty among satellite identities. It is also a
posterior under this proposal model, not a validated identity probability.

The saved `candidate_alternatives` contain only the 24 longest segments per
scan. They report **initial-state** posteriors, not post-proposal posteriors.
They show frequent collapse toward either one identity or the all-clutter
class:

| Scan | Sampled segment rows | Top identity > 0.99 | All-clutter > 0.99 | Neither extreme |
| --- | ---: | ---: | ---: | ---: |
| S01 | 563 | 4/24 | 19/24 | 1/24 |
| S02 | 429 | 14/24 | 10/24 | 0/24 |
| S03 | 528 | 23/24 | 1/24 | 0/24 |
| S04 | 487 | 13/24 | 10/24 | 1/24 |
| S05 | 551 | 14/24 | 9/24 | 1/24 |

These are length-selected examples, not population estimates. In particular,
S01 has long coherent-looking carrier segments that the current candidate,
calibration, timing and visibility state collectively explain as clutter. The
saved diagnostics cannot determine whether those segments are real unmatched
satellites, incorrect carrier links, or actual clutter.

## Surrogate improvement does not transfer to the common objective

The two saved surrogate values have different definitions:
`initial_trajectory_nll` excludes the timing penalty, whereas
`proposal_surrogate_with_priors` includes it and the scaled calibration-change
penalty. Comparing these raw fields would incorrectly suggest every proposal
worsens its own surrogate.

For a matched initial value, add
`0.5*(common_timing_s/3)^2 + 0.5*sum((relative_timing_s/2)^2)`
to the initial trajectory NLL. Those are the live HARD60 common and relative
timing prior widths; the calibration-change penalty is zero at the initial
state. The following deltas use this matched initial value. Negative means a
lower score. Exact common J is measured after common refit, not at the unsaved
raw proposal.

| Scan | Initial trajectory plus matching priors | Best proposal surrogate | Surrogate delta | Exact common J delta after refit | Refit KKT | Returned state |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| S01 | 56,235.1140 | 56,136.8654 | -98.2486 | +6.6539 | 290.1321 | Original |
| S02 | 38,868.8380 | 38,814.7661 | -54.0719 | +0.7069 | 371.1903 | Original |
| S03 | 35,776.7938 | 35,752.2657 | -24.5281 | -0.3859 | 197.2754 | Feasible research iterate |
| S04 | 36,970.2395 | 36,886.5731 | -83.6665 | +5.0560 | 342.2636 | Original |
| S05 | 41,009.6895 | 40,971.2344 | -38.4551 | +2.8161 | 146.0904 | Original |

Every method run uses the same conservative total of 180 calls: one initial
common score, one initial trajectory score, 48 trajectory optimizer calls, and
130 exact common refit calls. One initial orbit derivative projection is
reported separately. All five refits end at the evaluation cap, with KKT far
above the 0.001 acceptance threshold; recorded fitting times range from 3.58 to
14.98 s. The wall allowance is not the binding limit in these saved runs.

The equal-budget continuation gets all 180 evaluations on the common objective.
For S02 it reaches J=42,882.4020, versus the B fallback J=42,887.0338. On the
other scans continuation leaves the common J essentially unchanged. The B
proposal overhead therefore has a measurable opportunity cost on S02 under
this particular budget.

For S03, the small common-J decrease of 0.3859 is entirely explained by a
0.6951 decrease in the prior penalty overcoming a **0.3092 increase in frequency
NLL**. Associations remain 3,091: five new assignments replace five losses,
and six retained assignments change selected identity. Assigned RMS increases
from 142.5680 to 142.7550 Hz; on the retained intersection it increases from
142.4085 to 142.6379 Hz. Challenge assignments remain 28, with RMS increasing
from 157.6041 to 157.6354 Hz. Position moves 0.0326 km, while distance to the
operator-configured station reference changes from 5.2395 to 5.2072 km. This
small movement does not establish improved localization, especially with no
surveyed independent position truth and a nonstationary endpoint.

The returned S01/S04/S05 originals pass the saved broad endpoint audit. S02's
returned original is feasible but its broad endpoint audit has KKT=9.9869,
despite its immutable saved baseline audit recording KKT=0.0009145 under the
original audit options. That discrepancy concerns audit scope/options or its
reconstruction; B returns the original vector and does not create the mismatch.
It must remain visible rather than being labelled a newly accepted B fit.

## Why this local proposal has little ability to escape

The following are implementation mechanisms and plausible explanations, not
an identified causal decomposition of the observed failures.

1. **A local gradient search cannot discover distant posterior islands.** Each
   satellite gets only a +/-3 s change around the saved timing, starting at
   zero change. There is no coarse timing profile, alternate identity seed,
   discrete timing jump, or second geometry start. All recordings begin from
   already optimized full-data physical endpoints. A new segment identity that
   requires a timing displacement beyond this local box is never proposed.
   Even inside the box, an all-clutter segment can provide almost no gradient
   toward its other identity mode.

2. **The robust clutter model deliberately suppresses distant residuals.** At
   sigma=125 Hz and visibility one, the point signal-to-clutter density ratio
   is approximately `5319*exp(-0.5*(residual/125)^2)`. Signal and point clutter
   are equal at about 518 Hz; at 1,000 Hz the ratio is only 6.7e-11. Multiplying
   by a tiny segment identity posterior suppresses its gradient further. This
   protects the fit against isolated clutter, but does not attract a currently
   unexplained coherent segment toward a distant candidate trajectory.

3. **The trajectory model and production model reward different states.** The
   proposal uses one fixed normalized-q identity prior per segment, a 12% point
   clutter mixture, and a 10% segment all-clutter prior. Production uses the
   original conditional singleton density, detection odds and its normalizer
   per row, plus the fitted full-bank q budget. Proposal q, visibility, clock
   nuisance, position and segment links stay fixed. Only timing and the five
   calibration terms move in the surrogate. A high-confidence trajectory
   identity therefore need not beat production clutter after normalization.

4. **Orbit prediction is linearized once.** Timing derivatives are taken only
   at the initial point, and visibility is frozen for the entire surrogate
   optimization. Exact refit restores the actual orbit interpolation,
   visibility and full nuisance fit. Several-second changes can cross
   interpolation or visibility structure that the proposal did not model.
   The current saved outputs do not retain the raw proposal, its exact score,
   or linearization error, so they cannot establish how much of the rejection
   comes from linearization rather than the likelihood mismatch.

5. **A fixed local partition cannot repair a mistaken link.** The robust common
   RX/channel chirp estimate makes carrier linking possible, but a wrong
   segment cannot change identity midway. The 450 Hz continuation gate,
   residual slope bounds, gap breaks and 24-point cap can split or merge tracks.
   Clutter can absorb individual errors; no posterior source-break operation
   repairs the partition during optimization. Conversely, separate segments
   cannot reinforce a common identity beyond their shared physical parameters.

6. **Only 130 common calls remain to restore a different-objective proposal.**
   Every exact refit is still strongly nonstationary when the call cap binds.
   This shows incomplete restoration at the allotted budget, not proof that a
   fully converged proposal-start fit would succeed. Increasing the budget
   alone would also increase the baseline's allowance in a fair comparison.

## Practical next experiment

Keep these frozen negative results. A useful next implementation would replace
the single local gradient proposal with a bounded **training-only timing
profile over the existing candidate bank**, using exact orbit predictions at
a small declared set of timing nodes inside the existing physical bounds.
Profile robust coherent segment evidence, retain alternative identity/timing
modes before posterior collapse, and rank a small number of candidate-wide
timing proposals using the unchanged common objective. Preserve the original
seed as a portfolio member and reserve an explicit portion of the same total
budget for exact common refit. This is an experiment to test, not an improvement
already demonstrated by these records.

Before a new benchmark, save each proposed vector, its exact common score,
separate surrogate data/prior terms, linearized-versus-exact prediction error,
and post-proposal track posteriors. Those cheap diagnostics distinguish
incorrect surrogate ranking from inadequate exact optimization. Count all
projection/scoring work explicitly. Retain component tests for disjoint
evidence, crossing identities, source breaks, far-frequency clutter and held
CFO invariance, then repeat matched temporal and c=0 controls. No DSX window,
candidate hypothesis, held measured CFO, or configured station location should
be an algorithm input. The missing candidate in the fixed-bank experiment
remains unrecoverable without a separately labelled bank-expansion arm.
