# Source-level leave-one-NORAD-out endpoint diagnostic

Status: design checkpoint only. No fit is authorized by this document. Keep it
behind the active soft-fragment-CFO screen.

## Novelty and feasibility

No existing report performs this experiment. The candidate-generalization
audit removes one candidate at a fixed fitted position and explicitly does not
refit location. The candidate-influence audit chooses one influential group,
halves its weight, and scores the remaining tracks; it is not leave-one-source
prediction or endpoint selection.

The frozen DS11 source-balance census makes a bounded screen feasible. The
original screen indices `0,4,...,28` contain 489 tracks, only 6 ambiguous
singletons, and 138 repeated physical-NORAD groups (15--21 per scan, median
17). All 32 scans contain 539 repeated groups (13--21 per scan, median 16.5),
1,923 tracks and 36 ambiguous singletons. These counts come from the existing
training-frozen source-balance artifacts; they are not recomputed from held or
reference outcomes.

## Frozen comparison

Compare exactly four already-fitted endpoints per scan: original IID t4/100,
`source_receiver_equal`, robust t8/100, and robust t4/200. Do not add likelihood
or weighting variants. Use the eight original screen indices first.

Freeze a track's source from the original same-scan IID training endpoint and
the digest-bound candidate-ID-to-NORAD map. A track belongs to a NORAD fold only
when its original conditional candidate weight is at least 0.90. A fold is
eligible only when that NORAD has at least two tracks. It spans every receiver,
channel and RF for that NORAD. Ambiguous tracks remain in every training fold
and are never scored as an omitted source. Candidate mixtures remain complete;
the frozen identity defines membership, not a fixed candidate slot.

For endpoint family `f` and source `g`, delete every track assigned to `g` from
that family's objective, without renormalizing surviving source-balance
weights, and find the local leave-source-out solution. Score the omitted tracks
with one common original IID t4/100 predictive rule: fit each track CFO and
candidate responsibilities using only that track's training mask at the
leave-source-out geography, then evaluate full-minus-training density on its
held mask. Thus the omitted source cannot move geography, while its training
samples may estimate its track-local nuisance CFO and association mixture.
No reference coordinate enters membership, fitting, scoring or selection.

The primary endpoint score is the sum of these common-model omitted-source held
log densities over all eligible folds. Every held observation in an eligible
source contributes once. Select the largest total only when all four endpoints
have identical fold and observation coverage. Report an equal-source mean of
per-observation fold scores only as a sensitivity table; it cannot select an
endpoint or replace missing folds.

## Influence approximation and exact audit

Let `theta_f` be the qualified full-data endpoint, `u_fg` the score gradient of
source `g` under family `f`, and `H_f,-g` the observed negative Hessian of the
retained objective at `theta_f`. The fixed first-order deletion estimate is

```text
theta_IF(f,-g) = theta_f - inverse(H_f,-g) u_fg.
```

Compute three-dimensional E/N/time Hessians by central differences of analytic
gradients. Bind the derivative steps to the existing optimizer audit steps.
Require finite symmetric Hessians, positive eigenvalues, relative step-halving
agreement at most 0.005, condition number at most `1e10`, and an estimate inside
the unchanged fit bounds. Preserve an unavailable fold when any check fails;
do not ridge, clip, retry, or substitute another source.

Before using approximate scores, validate exact deletion refits on scan indices
0 and 16. For each of the four families, take the eligible source with largest
predicted E/N displacement and the deterministic median-displacement source
(NORAD ascending breaks ties), giving at most 16 local refits. Start at the
corresponding full endpoint, use the standard bounds/cap, and preserve failures.
For every qualified audit refit require E/N discrepancy at most the larger of
50 m or 10% of exact displacement, time discrepancy at most 0.02 s, and omitted
common-model held-score discrepancy at most 0.1 nat. All 16 planned audits must
qualify and pass before the approximate eight-scan ranking is interpreted.
This gate validates a local approximation, not discovery of a global mode.

## Required output and decision

Record every membership, omitted observation count, source gradient, Hessian
spectrum/condition, approximate shift, exact-audit result, and common held
score, with hashes of plans, banks, identity sidecar, model sources and existing
endpoint receipts. Report failures and weak geometry on the full denominator.
Also report endpoint-selection counts, aggregate common score margins, source
concentration, and geographic errors only after selection is sealed.

This is an exploratory diagnostic on an exposed panel. Advancement would
require 8/8 selectable scans, at least five selected-position wins over IID,
at least 10% median error reduction and nonworse P90, followed by the already
frozen additional panel with no rule changes. Likelihood success alone does not
establish geographic validity.

## Leakage and interpretation limits

Membership and the four endpoint families were developed on these recordings;
the 0.90 assignments also use each omitted source's training samples. The
diagnostic therefore tests conditional source-level tension, not blind physical
identity or calibrated out-of-source generalization. The common scorer profiles
nuisance CFO and association on omitted-source training data, so only geography
is source-held-out. Held observations select among the four endpoints and may
never subsequently tune memberships, thresholds, weights or noise scales.
Weak source-deleted geometry, local-mode dependence, conditional or wrong NORAD
labels, shortlist truncation, and correlated extraction/orbit errors remain
explicit limitations.
