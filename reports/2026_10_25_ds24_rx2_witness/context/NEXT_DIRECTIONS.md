# What the evidence warrants next

Independent review checkpoint, updated with the terminal six-context summary.
The coordinator's later final [REVIEW.md](../REVIEW.md) is authoritative for the
next decision, including the concrete CH5-to-other-owners predictive challenge.

This review uses completed studies, current metadata/structure checks and the
coordinator's reported RX2 checkpoint. It runs no new scores and recommends
no operational change. The reference remains ALGO02-v1 with the qualified causal
timing means and equal-prior family comparison.

## Established gains and ideas to retire

The clearest position gain is the ALGO01→ALGO02 comparison: fitted-c mean error
1.870→1.508 km on 404 common DS23 outputs, with a qualification tradeoff.
Equal-prior family replacement then supplies a smaller approximately 30 m mean
gain on 410 available scans in both c arms. All eight DS24 channels outperform
either half on average. These are matched comparisons on different cohorts;
their gains cannot be added. Temporal dependence and single-site exposure limit
their interpretation. [Completed review and primary report links](https://github.com/misko/leo-tracker-reduxredux/blob/82bc36cbd138b7024bd7af4f988032f1da5255cd/reports/2026_10_25_ds24_review_next_actions/README.md).

Several attractive proxies have failed the position test. ALGO04 increases
association from 70.08% to 75.08% while worsening the fitted-c mean from 1.469
to 1.591 km. RX2 remeasurement reduces polynomial scatter without a qualified
cohort localization gain. The roughly 100 m development RX1 gain shrinks to
2.7/15.4 m c0/fitted-c on eight later scans, with worse tails. The completed
parent-orbit covariance variant qualifies 0/4 pairs; its rejected raw means
worsen about 8/10 m. This rejects those implementations, not the existence of
receiver error or physical orbit uncertainty. Repeating unchanged recovery,
more continuous restarts, prior narrowing or gate relaxation is low value.

The latest identity-support replay is useful numerical closure, not new
localization evidence: 17/24 arm comparisons complete, 15 finite-pool orders
proved, zero stronger absolute-precision qualifications. It uses old easy
fixtures and retains the full-parent-generator/cavity-scorer mismatch. Do not
extend that extreme-score campaign or count a repaired integral as an accuracy
gain. [Completed replay](https://github.com/misko/leo-tracker-reduxredux/blob/1c65753ab91538d3ace88351d6fe9e18a99b14b9/reports/2026_10_25_ds24_identity_support/README.md).

## Bottleneck: strong evidence of confounding, incomplete causal diagnosis

The local known-nuisance calculation changes weak-position scale from about
534 m to 386 m with receiver terms known, 110 m with orbital timing known and
56 m with timing plus shape known. Together with stochastic known-label
simulations, this makes position/timing/shape ambiguity the strongest supported
mechanism. These conditional scales are neither calibrated confidence nor a
physical accuracy floor. Wrong identities, graph continuity errors and model
approximation can coexist with that ambiguity.

The current forensic check adds a concrete measurement-construction concern.
CH3 has an authentic native endpoint after a 7.795 s gap, with quartic leverage
0.99917: complete RMS 21.22 Hz hides leave-one-out RMS 379.73 Hz. Yet quadratic
curvature remains −33.94 Hz/s² without that endpoint, versus −39.67 with it.
The point does not create all curvature. CH4 instead has distributed correlated
quartic residuals; CH5 is comparatively stable. A join or systematic effect is
plausible, not identified. No deletion or new quality gate follows from this
selected example. [Structure evidence](../structure/FINDINGS.md).

All three RX2 sources were previously graph-nominated and information-ranked
under rejected labels. They are unused by the baseline, not unseen data.
Metadata-independent inclusion and nominal visibility make them worth testing;
neither establishes identity or an independent orbit measurement. Both baseline
c arms retain 3,037 curved +747 predictive IDs and zero postfit-only IDs.
[Exact exposure and membership](FINDINGS.md).

The new ordinary screens now test all 1,487 causal candidates for all three
owners. The coordinator reports that 60108 is absent from every top eight:
CH3 rank 87, CH5 rank 197 in both arms, and CH4 rank 143/145 c0/fitted-c.
The top nominees remain the historical 65871/57450. All six exact comparisons
now complete: CH3 and CH4 favor the proper polynomial null; CH5 favors physical
57450, in both arms. Their orders are interval-certified but the stronger
absolute-score criterion is unmet. CH5 requires an old/new conditioning
explanation before any independent-owner or position follow-on; its old
2,442.5 Hz residual and new marginal evidence are different statistics.
The terminal audit finds zero accepted curved/predictive parent owners or
points for 57450; independent corroborating-owner availability is unestablished.
This closes the proposed ordinary
60108 witness route for these sources; nominal visibility did not corroborate
the label. Do not insert 60108 manually into a conditional test. An unrestricted
full-catalogue exact ranking is not implied by its coarse-screen rank.

## Three bounded tests with decisions

1. **A tiny same-law hard-identity falsification panel.** Use two fixed inherited
   layouts and a predeclared small panel, for example at most six fresh draws:
   physically confusable catalogue alternatives and an unresolved case. Freeze
   one response-free conditional background before drawing; generation,
   ordinary nomination and exact scoring must use that same background and
   observation/support law. Compare ordinary nomination with a known-label
   control on identical observations, differing only in label availability.
   Keep any response-dependent cavity path a separate sensitivity. Report
   whether truth is lost by nomination, survives but is statistically ambiguous,
   or the known-label model/inference itself fails its numerical or recovery
   checks. A wrong stochastic winner alone does not prove an inference bug.
   Use score/nomination checks first; freeze any small recovery comparison
   separately and stop if its law cannot be matched. This tests the missing
   interface, not another round of easy positives or a calibration claim from
   six examples. No true-label backfill in the ordinary path; no rerolls.

2. **One active-parent phase/shape approximation check.** On two predetermined
   fast contexts, select an active family from existing RF-only nuisance/
   information diagnostics, not geographic error. At the saved RF position
   and fixed weak-direction perturbations, compare the original local treatment
   with that family's orbit-mode design evaluated at each nonlinear timing
   value. Hold observations, aliases, prior domain/normalization, noise and
   other nuisance conditioning matched, with independent numerical references
   and both c arms. Start with objective and gradient closure; make no position
   fit unless a material, resolved difference survives. An effect below the
   frozen sensitivity scale, or unresolved integration, closes this branch.
   This precise active-parent dependence is missing. A generic nonlinear-phase
   slice is not: previous fixed-shape parent work found at most 22.8 m predicted
   movement, and target/identity kernels already evaluate B(phi). It is not
   a reason to restart a full Bayesian rewrite or generic importance campaign.

3. **A source-continuity falsification before another recovery policy.** Use a
   tiny truth-known graph fixture on the actual native probe schedule: one
   continuous physical curve, and two different curves whose gap/continuation
   produces a deceptively small complete polynomial residual. Freeze the
   construction from timing/geometry before noise draws, keep all observations,
   and run the unchanged graph/quality ports. Compare source joins, curvature,
   endpoint leverage and predictive continuation against known source ownership;
   no orbit label or position fit is needed. Stop if the existing construction
   reliably separates them: CH3 then supplies no evidence for a new graph rule.
   If it repeatedly joins known distinct sources while passing its old quality
   criteria, that is a construction failure worth testing on separate fixtures,
   not permission to delete real endpoints. Cap the pilot at two mechanisms and
   a few seeds within minutes. Polynomial/Hough/graph comparisons already exist;
   the new contrast is this selection-aware gap/continuation failure, not another
   global fitter tournament or a threshold tuned on CH3. It remains conditional
   on declared measurement/noise assumptions, not an empirical false-join rate.

The current RX2 comparisons are complete. Before the three mechanism tests,
explain CH5 from saved old/new background and nuisance contributions; it is the
concrete surviving real-data lead. Any later
discovery-conditioned question must keep D physical in both models and compare
W same-family versus W unresolved, preserving shared orbit/radio covariance,
distinct constants and joint-minus-D evidence. That unrun design is useful only
for a defensible surviving hypothesis; it does not rescue this absent 60108
nomination. The old 53+85/36/15 RX1 tests are already done.
[Exact conditional model](../audit/CONDITIONAL_DESIGN.md).

Known-pilot peak-selection bias and calibrated pose/power are fallback
feasibility checks, not yet available new observables. Nominal 40-degree feed
separation is coverage, not a measured bearing. All current fast comparisons
use 10 MS/s; sample rate is unisolated. Generic sample-clock coupling and
cross-family dependence have prior mixed/negative tests. No new RF collection
follows from this review.

Promotion still requires matched c0/fitted-c observations, priors, candidates
and budgets; qualification and exact fallbacks; separate association, RF-fit
and geographic metrics; and a broader full-DS23/DS24 comparison with confident
full-DS23 gain. The 24 original and eight later DS24 examples are exposed for
future choices. Fresh validation needs an exposure-checked unused session/time
block; new-location transfer remains untested. A favorable selected scan is
mechanistic evidence, not a new ALGO.
