# Review of fast-scan localization and the next decisions

> **Correction (2026-10-25):** The 2,442.510 Hz archived residual below was
> carried unchanged when the CH5 row was relabeled; it is **not a verified
> 57450 fit residual**. See the [provenance correction](../2026_10_25_ds24_ch5_prediction/mechanism/FINDINGS.md)
> and [exact original files and annotation hashes](../2026_10_25_ds24_ch5_prediction/correction/annotation_receipt.json).
> The new catalogue/evidence results are unaffected. The original review is
> preserved at [commit 392faed8](https://github.com/misko/leo-tracker-reduxredux/blob/392faed8c5119279c832a56443aae77d76eb090e/reports/2026_10_25_ds24_rx2_witness/REVIEW.md).
> This report's original publication manifest and scientific seals bind that
> immutable commit's bytes, not these subsequently annotated Markdown files.

Review date: 2026-10-25. The user's current question is what the accumulated
experiments justify trying next. This synthesis accompanies the bounded
three-source RX2 investigation. It does not promote an algorithm or change
inference. The operational reference remains fresh ALGO02-v1 with qualified
causal signed orbital-timing priors and equal-assignment-prior family comparison.

The strongest demonstrated precision problem is weak separation of position
from satellite orbital timing/shape. Association, graph ownership and receiver
model failures also occur. We have not established an irreducible physical
accuracy floor, a globally correct set of satellite identities, or a reliable
new fast-scan improvement beyond the retained reference.

## What survives review

Results below refer to different explicitly matched cohorts; their gains cannot
be added together. Both c=0 and fitted-c controls exist in the source reports.

| Comparison | c=0 mean error, km | Fitted-c mean error, km | Interpretation |
| --- | ---: | ---: | --- |
| ALGO01 to ALGO02, 404 common DS23 outputs | 1.870 to 1.520 | 1.870 to 1.508 | Substantial within-site improvement; qualified coverage decreases from 407/413 to 404/413. |
| Signed-prior reference to equal-prior family comparison, 410 DS23 scans | 1.509 to 1.479 | 1.498 to 1.469 | Modest gain with temporal dependence and many unchanged scans. |
| DS24 all eight / CH1-4 / CH5-8, 24 usable fast scans | 1.202 / 1.538 / 2.040 | 1.220 / 1.558 / 2.040 | All eight help on average; shared satellites limit independence. |
| Smooth RX1 correction, 24 development scans | 1.202 to 1.112 | 1.220 to 1.120 | Encouraging development result. |
| Same frozen RX1 correction, eight later scans | 1.243 to 1.240 | 1.239 to 1.224 | Much smaller mean gain; P95 worsens in both arms. Retain reference. |

The full DS23 recovery candidate raised fitted-c association from 70.08% to
75.08%, while mean error worsened from 1.469 to 1.591 km and P95 from 3.157 to
3.473 km. Its c=0 arm also worsened. A different RX2 measurement refinement
reduced median polynomial scatter from 78.07 to 22.18 Hz over 322 curves without
a qualified cohort position gain. These results are direct reasons to separate
coverage, frequency precision and position accuracy.

The graph/EM/Hough/multiple-hypothesis work established high polynomial coverage.
It does not establish satellite identity. The current 24-scan DS24 position
likelihood uses 78,067/108,600 original winners (71.8849%). Polynomial membership,
satellite-compatible postfit extensions, and observations entering the position
likelihood must remain distinct measures.

Source comparisons, figures and links are collected in the
[previous reviewed synthesis](https://github.com/misko/leo-tracker-reduxredux/blob/82bc36cbd138b7024bd7af4f988032f1da5255cd/reports/2026_10_25_ds24_review_next_actions/README.md).
The ALGO01 comparison is independently recorded in the
[full ALGO02 evaluation](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_19_algo02_ds23_full/README.md).

## What explains the limited precision

Moving the receiver and shifting a satellite along its predicted orbit can
produce very similar Doppler changes. In the reviewed DS24 cohort, the strongest
orbital-timing/weak-position correlation has median 0.935. Channel halves share
a median 11 calibration families, with only 17.7 degrees between their least
constrained directions. More measurements of those families share their orbit
uncertainty.

A local conditional diagnostic has median weak-direction scale 534 m. Treating
receiver terms as known changes it to 386 m; treating orbital timing as known
changes it to 110 m; timing and shape known changes it to 56 m. These are
information diagnostics under fixed identities, noise and local geometry,
not achieved errors, calibrated confidence limits or permission to tighten
priors. Noiseless known-label simulations recover within 0.8-2.5 m, while noisy
realizations can pass gates and remain about 1 km wrong. The simulation and
approximate inference laws differ, so they do not establish a physical floor.

Thirty targeted continuous restarts agree within 2.06 cm. This makes generic
continuous multistart low priority for those tested assignments. Different
discrete identities remain possible. All usable fast scans in the reviewed
sample are 10 MS/s, so sample-rate causality is untested. A nominal 40-degree
feed separation supplies different coverage, not a measured bearing or a
spatially separated baseline.

## What the new RX2 diagnosis adds

All three complete unused curved sources and all 124 native IDs remain in the
test. Previous rejected nominees are excluded from nomination inputs. The
ordinary search uses the full 1,487-element causal catalogue at the same saved
c=0 RF position for both arms. Satellite 60108 is not forced or backfilled.

The ordinary search places 60108 at rank 87 for CH3, rank 197 for CH5, and ranks
143/145 for CH4 in c=0/fitted-c. The original rejected nominees independently
reappear first: 65871 for CH3 and 57450 for CH5/CH4. These ranks establish no
new identity, and absence from the shortlist is not exact exclusion under the
more complete model. Full nominal visibility for 60108 did not establish
cross-receiver corroboration.

All six complete-source comparisons finish. Each compares eight ordinarily
nominated physical candidates with the same proper polynomial unresolved-source
model. Every winner has a numerical bound establishing its order within that
finite pool; no comparison certifies all individual objectives to the stricter
0.001 absolute-score criterion. Model ordering and precise individual scores
are separate outcomes.

| Source | c=0 winner / minimum log-evidence margin | Fitted-c winner / minimum log-evidence margin |
| --- | --- | --- |
| CH3/T002, 24 points | Unresolved / 21.21 | Unresolved / 20.87 |
| CH5/T001, 57 points | 57450 / 29.23 | 57450 / 28.45 |
| CH4/T000, 43 points | Unresolved / 34.42 | Unresolved / 30.73 |

These are conditional finite-pool evidence bounds, not identity probabilities
or calibrated physical adequacy tests. The CH5 winner is the same historical
rejected label. Original and new scoring have different conditioning and
nuisance treatment, so this is not an isolated ablation explaining why the old
pipeline rejected it. Satellite 57450 is absent from the original active curved
and predictive family sets; no already accepted 57450 owner supplies automatic
corroboration. The other two sources have no accepted physical winner.
No operational association or position fit is added. Baseline likelihood
coverage stays 3,784/4,808 points (78.7022%) in both arms.

Independent polynomial diagnostics distinguish three failure signatures:

- CH3 has a high-leverage isolated endpoint after a 7.8 s gap. Quartic complete
  RMS is 21 Hz, but leave-one-out RMS is 380 Hz. Substantial quadratic curvature
  remains without that endpoint; it is not a wholly spurious curve.
- CH4 has distributed correlated residuals (adjacent correlation 0.823), not
  just one influential endpoint. A graph join, smooth model mismatch and an
  inadequate polynomial are still competing explanations.
- CH5 is a stable quartic: 20.4 Hz complete RMS and 22.8 Hz leave-one-out RMS.
  Its archived physical nominee leaves 2,442.5 Hz RMS. This clean curve is a
  particularly useful identity/physical-model challenge.

These are examined development sources, previously considered under rejected
labels. They are unused by the baseline position likelihood, not unseen data.
No point is removed, no gate is loosened, and no new position improvement is
claimed from this investigation.

## Recommended decisions

1. **Explain and independently challenge CH5/57450.** The complete three-source
   result supports a concrete question: which difference in old/new position,
   conditioning, alias, orbital timing, physical modes or receiver uncertainty
   explains why this same label now beats the alternatives? First reconstruct
   those differences on the same 57 observations. Then define only the small
   matched comparison needed to isolate the implicated term. A concrete
   prediction test uses CH5 alone to infer the proposed 57450 correction, then
   predicts each other complete source under shared satellite/radio uncertainty.
   CH4 is especially informative because it overlaps CH5 but independently
   favors the unresolved model. Retain CH3 and all failures too. Compare a
   shared-family witness against its unresolved and ordinary alternative
   models, keeping CH5 physical in every comparison and accounting for shared
   covariance. This is a development consistency test, not unseen validation.
   If no such support exists, retain development-only candidate status. Do not
   rerun old RX1/60108 sources as new corroboration or relax CH3/CH4 failures.

2. **Measure identity/selection failure in a small consistent-law control.**
   Freeze a conditional background and use identical generating/scoring laws
   for a few confusable catalogue pairs and a proper null. Compare ordinary
   nomination against a known-label diagnostic on the same draws; never insert
   the known label into the ordinary search. Keep the existing response-selected
   parent-cavity path as a separate sensitivity. This is an identity-stage
   control, not full IQ-to-position simulation or calibrated error-rate study.
   Predeclare numerical/model closure and nomination-recall criteria. A true
   label omitted by nomination despite an adequate generating-model fit points
   toward search/selection. An error in a noisy realization, even with its label
   known, is not by itself an inference failure: legitimate prior/noise overlap
   must be distinguished from a failed implementation or approximation.

3. **Test the specific remaining active-parent phase/shape approximation.**
   On two fast contexts, compare a few fixed RF-selected position probes while
   reevaluating the physical-mode design at each orbital-timing node. Hold the
   prior law, observations, normalization, noise treatment and c controls fixed.
   Predictive-target kernels already do this; repeating them would add no new
   test. Stop before optimization if objective-gradient changes are negligible
   or unresolved. Earlier fixed-shape nonlinear-phase integration produced at
   most 22.8 m predicted local movement, so expectations should remain modest.

4. **Use additional geometry to allocate recovery effort.** When a candidate
   has defensible identity, compare length-selected and information-selected
   sources from the same metadata pool and compute budget. Estimate information
   after accounting for shared receiver/orbit nuisance variables. Preserve all
   existing likelihood IDs. Only then run a small matched position comparison.
   Independent owners help model checks but do not create independent satellite
   orbit errors. A larger coverage number alone cannot select the result.

Endpoint influence is an exploratory graph diagnostic supported by the new CH3
example, not a validated acceptance rule. A later continuation/segmentation comparison should score all
points under both hypotheses and penalize splits, without dropping a bad-looking
endpoint. Blanket splitting and temporal mixtures have already been explored;
they are not a new general solution established by this one diagnostic.

If these tests produce no additional position information, inspect whether the
existing corpus contains calibrated pose/power/antenna information that could
support another observable. Nominal feed direction is insufficient. This is a
bounded metadata feasibility question, not authorization for hardware changes,
new RF collection, stationary pooling or a moving-trajectory prototype.

## Work to stop repeating and promotion criteria

Deprioritize unchanged generic multistart, unrestricted point recovery,
blanket prior narrowing, broadly flexible receiver drift, active-family-only
soft labels, Gaussian log-volume removal and extreme-loser integration
precision. Existing results already constrain these ideas. The recent numerical
identity work is enabling diagnosis; it has not established an accuracy gain.

Keep mean, median, P90/P95, qualification/coverage, observation ownership,
frequency fit and runtime separate. Every position experiment uses matched
c=0/fitted-c observations, candidate sets, other priors and search budgets.
Use causal TLEs and the 25 by 25 km region centered at 37.906, -122.545. The
evaluation coordinate is read only after RF decisions are fixed.

All currently reviewed DS24 cases are exposed development evidence. A new
validation claim requires an exposure-checked unused session/time block.
Promotion requires a frozen broader comparison, including full DS23 evidence,
and reporting adverse tails and failures. New-location generalization remains
untested. The next agent wave should be two bounded scientific tests and one
independent reviewer, with a stop decision for every branch.
