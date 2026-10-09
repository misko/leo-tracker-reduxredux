# Does B7 use satellite identity persistence?

**Source audit and preparation only.** No recording, reference error, reserve,
numerical fit or new RF data was accessed for this note. Iteration106 remains a
separate frozen experiment; this proposal does not change its model or protocol.

**The final B7 score is an independent-window satellite/clutter mixture.** The
pipeline already uses temporal structure upstream, but does not carry a joint
satellite-identity probability along a track into the final likelihood. A small
soft identity-persistence model therefore addresses a real missing assumption.
There is not yet evidence that this omission causes a material position error.

## What the code actually does

1. [Preparation](../../src/leo/application/regional_position_inputs.py) selects
   the highest original GLRT-margin candidate per source window, retaining its
   measured CFO, actual RF, receiver, channel and time. It reconstructs orbit-blind
   Hough tracklets, then keeps tracks with at least 15 rows and 15 seconds of span,
   up to 12 per receiver, as **calibration bootstrap tracks**. The numerical
   `PositionObservations` contract contains no track identity or transition model.
2. [Persistent-hop reconstruction](../../src/leo/analysis/persistent_hop_trajectory.py)
   builds lane-local tracklets keyed by channel, edge, receiver and actual RF.
   Its default gap limit is 4 seconds, CFO residual gate 2,500 Hz, and minimum
   support eight. It can also construct cross-lane trajectory hypotheses, but
   position preparation consumes `trajectory.tracklets`, not the inferred
   cross-lane physical groups. A Hough tracklet is a measured frequency path,
   not a verified satellite identity; crossings and blends remain possible.
3. [Regional association](../../src/leo/analysis/regional_position_association.py)
   discovers satellite timing modes at the inferred calibrated position.
   [T1-AT selection](../../src/leo/analysis/t1_at.py) groups supporting windows
   by receiver/channel, splits gaps over 5 seconds, and requires runs of at least
   ten windows spanning at least 5 seconds. Greedy selection and one-out repair
   resolve competing support. This already rewards persistent support; describing
   the entire pipeline as temporally independent would be incorrect.
4. [The regional runner](../../src/leo/application/hard60_runner.py) carries the
   selected satellite bank and initial timing vector into final fitting. It
   passes **all prepared observations**, not fixed T1-AT row assignments. The
   final [B7 satellite-correction objective](../../src/leo/analysis/hard60_satellite_correction.py)
   calls [the hard60 likelihood](../../src/leo/analysis/hard60_score.py), which
   sums satellite Gaussian terms plus clutter separately for each row and then
   sums log scores. Responsibilities are recomputed independently by row.
   Shared clocks, satellite slopes, timing and position couple predictions, but
   there is no Markov state connecting one row's satellite label to the next.

Thus an HMM would add an **identity-persistence prior**, not additional measured
information. It differs from the existing greedy association by marginalizing
alternative labels during final optimization instead of selecting a bank and
timing seed once. It also differs from a temporal-innovation model, which links
frequency errors conditional on an identity. These mechanisms should not be
introduced together in the first experiment.

## The smallest justified next step is an ambiguity audit

Before adding position fits, freeze a metadata/evidence-only grouping rule and
measure whether there is ambiguity for persistence to resolve:

- Use the existing frozen bootstrap-track row memberships, avoiding a new
  reconstruction or retrospective choice of particularly successful tracks.
  Report their limited coverage of the full observations. Keep every uncovered
  row under the current independent likelihood.
- Within each track, retain only adjacent observations with the same receiver,
  channel **and exact actual RF**, and positive gap no larger than 2 seconds.
  Reset at every boundary or larger gap; never interpolate absent windows or
  connect different RF lanes. This conservative 2-second research rule is a
  proposal to freeze, not a claim about emitter coherence time.
- If a row belongs to multiple bootstrap tracks, leave it independent rather
  than duplicating its evidence or choosing the track with the best satellite
  fit. Do not join tracks across receivers, frequency hops or hidden intervals.
- At the unchanged ordinary B7 endpoint, describe responsibility entropy,
  top-two odds, satellite/clutter switches and sensitivity to tiny hypothetical
  prediction perturbations. A switch alone is not an error: crossings, genuine
  identity changes and clutter can cause it. Freeze fitted-derived memberships
  for both c arms; do not select groups using reference errors.
- Test whether adjacent evidence improves **held-out** label/frequency
  predictive score against the independent model, using whole recording groups
  for any global parameter selection. Track construction used measured CFO, so
  such a test must explicitly condition on frozen track membership or rebuild
  it using training observations only. It cannot claim unconditional held-out
  validation while using held-out CFO to form the tracks.

If memberships are sparse, assignments already decisive, or apparent switches
only occur at excluded gaps, stop. In those cases a persistence extension has
little demonstrated opportunity. No responsibility audit has been executed here.

## Conditional prototype: soft persistence with an exact independent limit

If the audit supports it, use one globally fixed persistence strength on these
short segments. Preserve a clutter state and allow identity changes. A reset-plus-
sticky transition has the form `T = rho I + (1-rho) 1 piᵀ`, so forward/backward
updates cost O(K) per row rather than O(K²), with K satellite/clutter states.
At `rho=0`, the objective and gradients must recover the current B7 mixture
exactly. This is preferable to one hard satellite label for an entire Hough track.

That schematic transition is not yet an implementation specification. Visibility
and the current point-process/detection normalization vary by row and hypothesis.
The prototype must separate properly normalized categorical weights/emissions
from the current per-window detection factor, handle newly invisible states and
clutter resets, and restore the entire original score at `rho=0`. Multiplying
current responsibilities as if they were independent emission densities would
double-count the observations. Dropping normalization would create a different,
uncontrolled position preference. Finite-difference checks must cover both
physical and clock gradients, including any geometry-dependent transition term.

Required synthetic controls: exact independent nesting; exhaustive enumeration
agreement on a tiny sequence; total probability normalization; one ambiguous
crossing and one genuine identity switch; clutter interruption; gap/channel/RF
reset; overlapping-track no-op; wrapped-frequency invariance; and no improvement
claim based solely on a lower in-sample score. Analytic forward/backward gradients
would keep this suitable for an embedded implementation. No long-lived filtering
state across recordings or unobserved hop intervals is proposed.

Any later position experiment must keep ordinary reference-free starts, candidate
bank, windows, clock priors and fit budgets fixed, with matched fitted-c/c=0 and
an exact independent control. Report all DS16/17/18 members, no-op coverage,
qualification/fallbacks, position and predictive/frequency effects separately.
Do not tune persistence per scan or deploy based on this consumed-data study.

## Why this is not a repeat of the earlier weighting proposal

[Iteration17 density weighting](../2026_10_08_position_error_iter17/README.md)
worsened mean and worst error. A joint identity model retains every observation
once and changes dependence; it must not silently become inverse track-count
weighting. [Iteration25 slope flexibility](../2026_10_08_position_error_iter25/README.md)
improved a pooled mean but regressed newer cohorts and the worst case: more
freedom or a better residual score is insufficient evidence of localization gain.

[Iteration87](../2026_10_09_position_error_iter87/RESULTS.md) found residual
temporal correlation after B7, but assignment-selected residual correlation does
not establish persistent identity or calibrate a transition probability.
[Iteration90](../2026_10_09_position_error_iter90/RESULTS.md) showed much apparent
receiver-satellite contrast overlaps existing clock directions, cautioning
against naming an inferred statistical effect as an RF hardware defect.

The OU innovation idea was already proposed in
[iteration86](../2026_10_09_position_error_iter86/NEXT_MODELS.md) and
[iteration106](../2026_10_09_position_error_iter106/PREPARATION.md). This note's
concrete contribution is separating **identity dependence absent from the final
score** from **temporal support already used upstream** and from **correlated
measurement noise**. The evidence currently justifies the bounded ambiguity
audit, not an accuracy claim or an immediate HMM rollout.
