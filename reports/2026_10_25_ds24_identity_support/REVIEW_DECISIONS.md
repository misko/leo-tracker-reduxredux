# Review decisions: fast-scan precision

This review uses the completed DS23/DS24 comparisons and the separately bounded
identity-support/witness iteration. It does not promote an algorithm. The
reference remains ALGO02-v1 with qualified causal signed orbital-timing means
and equal-assignment-prior family comparison. Numerical replay and visibility
checks cannot establish a position improvement.

## Evidence that should determine the next work

- The full-channel DS24 reference already beats both channel halves in mean
  error: c0/fitted-c 1.202/1.220 km versus 1.538/1.558 km for CH1-4 and
  2.040/2.040 km for CH5-8, on the same 24 usable scans.
- Added association is not an accuracy surrogate. On the same 410 DS23 scans,
  the ALGO04 recovery candidate raises fitted-c association from 70.08% to
  75.08% but worsens mean error from 1.469 to 1.591 km and P95 from 3.157 to
  3.473 km. c0 also worsens.
- The strongest demonstrated ambiguity is position versus orbital timing and
  shape. Conditional local weak-axis scale is about 534 m, 386 m with receiver
  terms known, 110 m with timing known and 56 m with timing plus shape known.
  These are diagnostic scales under assumed identities/model, not achieved
  accuracy, calibrated uncertainty or a physical error floor.
- Continuous multistart, cleaner CFO alone, generic recovery and broader
  receiver flexibility have already had adequate targeted tests. Thirty
  restarts agree within 2.06 cm for the tested assignments. RX2 remeasurement
  improves scatter without a qualified cohort location gain. RX1 correction's
  development gain shrinks to 2.7/15.4 m mean on later c0/fitted-c scans while
  both tails worsen.
- The completed parent-orbit covariance variant admits zero of four matched
  pairs. Its rejected raw means worsen about 8/10 m. Explaining a residual by
  a fitted correction does not independently identify its physical cause.
- Real new-family alternatives remain close in two cases. The existing easy
  synthetic positives and historically label-selected RX1 witnesses do not
  establish reliable decisions on those difficult alternatives.

Numbers and source links are in the published review at commit
82bc36cbd138b7024bd7af4f988032f1da5255cd, path
reports/2026_10_25_ds24_review_next_actions/README.md. Cohorts differ; their gains
must not be summed. All 32 reviewed DS24 examples are exposed for future work.

## Next directions in priority order

1. **Resolve a hard satellite decision with a controlled observation law.**
   The old twelve-draw numerical regression is now closed within its fixed
   budget: 17/24 arm comparisons completed and 15 have interval-certified
   finite-pool ordering; none met the stronger absolute-score precision check.
   Two completed comparisons failed the unchanged strict null arithmetic guard
   and seven lacked a complete result at the deadline. No position fits ran.
   Do not expand this extreme-score numerical campaign. A next
   small falsification panel should contain physically confusable catalogue
   alternatives and an unresolved outcome, with one fixed background shared by
   generation, ordinary nomination and scoring. Compare ordinary labels with
   known labels on the exact same observations and background. No true-label
   backfill. A failure only in the ordinary path points to nomination/identity;
   a failure in both points toward nuisance information or inference. Six
   examples can falsify a mechanism but cannot calibrate error probabilities.

2. **Seek additional independent geometry, beginning with existing sources.**
   The metadata-selected RX2 witness feasibility check for DS24-0013 is now
   complete: all three unused curved whole-scan sources, totaling 124 native
   IDs, have full nominal visibility support throughout phase [-15,+15] s at
   the saved c0 RF estimate. No CFO comparison or identity decision has run.
   Temporal overlap is useful for receiver calibration but is not a necessary
   condition for an orbit to explain two sources. Keep the all-scan curved pool
   separate from the original overlap/adjacency inventory. If geometry permits,
   later score every selected source through ordinary causal-catalogue nomination
   with shared uncertainty, without forcing 60108 into the shortlist. Support
   for 60108 would motivate a bounded matched position test; absence or ambiguity
   closes that source branch. Rank useful recovery by added weak-direction
   information after nuisance uncertainty, as well as defensible identity.
   Shorter sources may beat longer ones; local information is not actual error.

3. **Test the specific active-parent approximation still omitted.**
   At a few fixed RF-selected positions, compare the current active-parent
   treatment with orbit-mode design evaluated at each nonlinear timing value.
   Keep data, labels, priors, aliases and normalization identical. The existing
   target identity kernel already evaluates that dependence; repeating it is
   not new work. Start with objective/gradient closure and independent numeric
   checks. Continue to position fits only if the approximation changes the
   result materially and reproducibly. The prior frozen-shape nonlinear-phase
   calculation found at most 22.8 m predicted movement.

4. **Check measurement-selection bias or a new observable only after verifying
   an existing fixture.** A tiny verified known-pilot waveform through the actual
   peak-selection path could test conditional CFO bias and reported uncertainty.
   This is distinct from smoothing CFO. Existing pose/power/antenna records could
   support a bearing feasibility check only if they contain a calibrated
   reference. Nominal 40-degree feed separation is not a measured bearing.
   All current comparison scans are 10 MS/s, so sample rate remains unisolated.
   No new RF collection or trajectory work follows from this recommendation.

## Decision standard

Use small mechanism tests before broader evaluation. Preserve c0/fitted-c
observations, candidate sets, other priors and budgets. Separate RF fit,
polynomial membership, postfit-only association and likelihood membership from
position accuracy. Preserve abstentions, all selected scans and tail regressions.
   Do not tighten priors or choose corrections from the evaluation coordinate.

Only a qualified small mechanism justifies a broader frozen DS23/DS24 comparison.
A new validation claim needs an exposure-checked unused time/session block; a
new split of familiar data is development. New-location transfer is untested.
Keep the operational reference and move on when a bounded branch has no useful
information. Ninety-percent association remains an aspiration, not an acceptance
criterion.
