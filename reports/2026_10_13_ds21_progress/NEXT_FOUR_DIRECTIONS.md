# Four prioritized DS21-039 investigations

Updated 2026-10-13. All new controls use fitted `c`. The release target is below
0.5 km for every eligible CH1–8 DS21 recording; it has not been reached.

DS21-039's refined joint error is 4.073 km; the quarter-scale two-start sensitivity
reached 3.930 km, but its fixed five-case transfer worsened the median and is not
promoted.
The original low/high/all comparison is 3.759 / 2.557 / 4.291 km. Its half-band
fits inherit all-band ambiguity initialization, so this is not yet a comparison
of three independently initialized pipelines.

## Current priority and assignment order

The evidence now prioritizes the four workstreams below. The historical numbered
sections retain completed controls and rationale; this table gives the current
execution order.

| Priority | Investigation | Discriminating next step | Ownership/status |
| --- | --- | --- | --- |
| 1 | Timing versus position identifiability | Audit the eight completed ±1 km compensated displacements against local curvature and assignment changes. Separate a weak position constraint from an actual timestamp/orbit-model defect. | SOL temporal/evidence worker; receipt audit active |
| 2 | Satellite association and frequency ambiguity | Locate which windows change satellite/clutter assignments along those fixed displacements; establish whether ambiguity switches or continuous nuisance compensation dominate. Use existing posterior receipts before proposing new temporal assumptions. | Coordinator integration; dedicated SOL review queued |
| 3 | Cross-band calibration and error dependence | Require reproducible structure across development cases before adding calibration flexibility or learned covariance. Retain receiver-slope, weighting and quarter-scale transfer failures as controls. Specify a training-only transfer test rather than learning shifts against known positions. | Coordinator; next SOL implementation gated on evidence |
| 4 | Initialization, independent band comparison and full DS21 coverage | Complete the reusable fitted-only initializer, expand development coverage, and explicitly compare inherited all-band versus independently derived half-band starts before attributing failures to fusion. | SOL transfer/initialization worker active; coordinator runs bounded slices |

The current agent thread limit prevents launching four additional workers at
once. Two existing SOL workers continue in parallel; the coordinator handles
integration and queues the remaining reviews. Scientific runs remain serialized.
This scheduling limitation does not change the four investigation scopes.

## 1. Satellite association across revisits

**Question:** Can weak temporal information resolve competing satellite
assignments without falsely identifying frequency-candidate slots as emitters?

The original families contain one observation each: there are zero temporal
edges. Full versus half fits change satellite/clutter assignments in 18–20% of
windows. The recorded data contain no persistent emitter identity, so continuity
is a sensitivity assumption, not a recovered physical label.

The SOL temporal worker implemented a satellite-plus-clutter hidden-state
model. It independently marginalizes frequency alternatives in each window,
permits direct satellite switches, and preserves the original stationary prior.
The prespecified one-second persistence model links only short same-RX/channel/RF
revisits within an original training block. Four matched fits used the original
and refined starts, with an independent singleton oracle before fitting. All
four converged, but selected error worsened from 4.073 to 4.410 km. This specific
intervention is not promoted; further association changes need a different,
supported hypothesis rather than another persistence setting chosen by error.

**Decision:** compare sealed positions, assignments, clutter and stationarity.
Better frequency likelihood alone is insufficient. The exact control is in the
[temporal protocol](../2026_10_13_ds21_039_association/TEMPORAL_REFRESH_PROTOCOL.md).

## 2. Calibration and satellite timing confounded with position

**Question:** Are nuisance corrections absorbing the position information or
compensating for an incorrect association?

Per-observation RF Doppler scaling already checks out. The timestamp provenance
audit found no conversion bug. A receiver-specific RF slope improved the
objective by only 0.657 and worsened position from 4.073 to 4.085 km. Repeating
that flexibility increase is therefore low priority.

The [zero-optimizer observed-curvature diagnostic](../2026_10_13_ds21_039_association/TIMING_CURVATURE_RESULTS.md)
completed at the original and refined all-band states. Profiling timing as well
as calibration weakens the smallest position curvature eigenvalue by roughly
140× and 300×, respectively. The exact prior contributes less than 1% of the
remaining weak-axis curvature. This is strong local confounding, not proof of
an incorrect physical prior or timing bug. Some per-satellite compensation
estimates vary materially between the two numerical steps. The
[eight finite-displacement checks](../2026_10_13_ds21_039_association/TIMING_DISPLACEMENT_RESULTS.md)
are complete and independently audited. All exact objective changes are positive;
the refined negative ray costs 7.302–7.307 versus a local prediction of 3.270–3.358.
Prior arithmetic closes, so the mismatch arises in the finite likelihood behavior.
The next prescribed control refits nuisances at four fixed displaced positions
to test whether the linear compensation ray is inadequate. Timing corrections
need external justification; they cannot be tightened until a desired position
appears.

**Decision:** distinguish a supported clock/orbit correction from nuisance-driven
movement along weakly constrained directions. Report position and frequency
effects separately, including sensitivity to the prespecified assumption.

## 3. Correlated errors and likelihood versus prior strength

**Question:** Does treating repeated observations as independent make the joint
likelihood overwhelm useful physical constraints?

Equal-band and equal-block controls did not improve localization. Those controls
preserved total likelihood weight; they did not test effective information or
the overall balance between likelihood and priors. Residual block structure
persists, but cross-receiver/band correlations change sign between solutions.
There is not yet evidence for a stable learned covariance.

The prespecified global likelihood-scale sensitivity completed: original scale
versus one-quarter scale, with every physical prior unchanged. It improved
DS21-039 error from 4.073 to 3.930 km, with four stationary fits. This modest
change tests joint regularization strength; it does not estimate covariance or
effective sample size. Native branch second moments are retained in the
diagnostics so ambiguity cannot disappear through averaging residuals. The next
check used these same fixed scales on five existing development cases, with
historical fitted states and matched budgets. All 60 calls completed, 58
stationary. Median error worsened from 1.957 to 4.061 km and maximum from 4.899
to 5.216 km, with zero cases below 0.5 km in either condition. Quarter-scale
weighting is not promoted. The [transfer report](../2026_10_13_ds21_039_association/FIVE_CASE_TEMPERING_RESULTS.md)
retains all cases and the DS21-003 boundary solution.

**Decision:** an intervention must improve position across development cases,
not merely reduce its differently scaled objective. Unsupported low-signal
tails and failures remain visible in the report.

## 4. Initialization, optimization and full-DS21 coverage

**Question:** How much error is due to missed solutions, and do results survive
independent initialization and expansion beyond five recordings?

The original joint search missed a feasible lower-loss solution, but refinement
only reduced position error from 4.291 to 4.073 km. Optimization is a confirmed
contributor and is insufficient by itself. Keep stationary source incumbents,
record failed starts, and select by training criteria with fixed budgets.

The SOL joint worker implemented a training-only adapter around the existing
fitted-c discovery core. Its 10 owned tests passed again in the integration
worktree. A first bounded DS21-007 slice completed 100 points in 335.007 seconds,
with exact census evidence and a causal catalogue pinned before inference.
Discovery states are not final
position estimates. Completed points can be reused; failed or orphan attempts
cannot be silently retried.

DS21-007 has now completed the fitted shape, fresh bootstrap, absolute hybrid,
cold bootstrap and six-proposal export chain. All nine shape and nine hybrid fits
were stationary. The [initialization report](../2026_10_13_ds21_release_readiness/PROPOSALS_007_RESULTS.md)
records the 32-satellite pool and six physical proposals per view. The baseline
[joint comparison](../2026_10_13_ds21_release_readiness/JOINT_007_RESULTS.md)
has completed: all 18 fits stationary, all/low/high errors 3.524 / 3.738 / 4.325 km.
Combining improves this case, but none meets 0.5 km. The half-band fits inherit
all-training ambiguity initialization. The historical shape selector's zero-c choice is replaced
explicitly; core shape math is unchanged, and its projection of RF-constant
offsets is not claimed to learn RF calibration. Twenty-eight development
recordings still require initialization.

**Decision:** build the missing development initializations, then compare all
three band views with matched budgets and documented seed provenance. Report
coverage and failures alongside accuracy.

## Execution and dataset acceptance

SOL workers can implement and review in parallel; expensive scientific runs
are serialized in bounded slices. Two workers are currently active. Four
directions do not mean four simultaneous optimizer campaigns.

Test supported changes first on the five fixed development cases, then all 34
fast development recordings. Freeze the algorithm and training-only selection
rule before running the 20 locked fast recordings. Report all 54 fast members,
each low/high/all error where available, failures as misses, median, upper
quantiles, maximum and count below 0.5 km. Adaptive CH1–4 recordings require
separate preparation and are not CH1–8 acceptance cases.

Reference coordinates enter only after sealing results. Accuracy is relative
to the configured reference, which is not independently surveyed. No per-case
choice of whichever model is geographically closest is allowed. Reaching
0.5 km remains a measured acceptance condition, not a promised outcome.
