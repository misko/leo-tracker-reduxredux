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
| 1 | Shared initialization/source/coverage failure | DS21-013 denser discovery plus unchanged downstream fits reduces CH1–8 errors from 267–269 km to A 1.510 / B 2.021 / C 1.847 km; the final audit passes, but no row reaches 0.5 km. Fixed-policy DS21-009 discovery and initialization now complete; its final fits are underway. Keep transfer testing separate from the saved-function projection diagnosis. DS21-025 remains metadata-ready only. | SOL initialization audit and fixed-function diagnostic implementation/review; coordinator bounded fits |
| 2 | Timing versus position identifiability | Finite-displacement asymmetry persists. The 75-endpoint timing audit finds seven boundary states on DS21-009, none on DS21-011 or original DS21-039 controls; active saturation is not shared by every combination failure. Further attribution must distinguish continuous nuisance compensation and association changes from an actual timestamp/orbit defect. | SOL timing reconstruction and independent audit complete |
| 3 | Satellite association and frequency ambiguity | Locate which windows change satellite/clutter assignments along those fixed displacements; establish whether ambiguity switches or continuous nuisance compensation dominate. Use existing posterior receipts before proposing new temporal assumptions. | Coordinator integration; dedicated SOL review queued |
| 4 | Cross-band calibration, transmitter dynamics and error dependence | Paired-receiver increment diagnostic completed without a reproducible shared positive excess. CH1/CH8 lack adequate support; do not add transmitter terms from this result. Retain prior negative controls and require training-only transfer evidence. | SOL independent receipt audit completed; no intervention promoted |

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
The four fixed-geography nuisance fits have now completed and passed independent
receipt audit. All are stationary for nuisance-only optimization and improve the
saved ray states, but the refined endpoint's minus/plus costs remain 6.504 / 3.004
above its original objective. The finite asymmetry persists after this local
relaxation; neither global profiling nor improved accuracy is established.
See the [fixed-geography results](../2026_10_13_ds21_039_association/FIXED_GEOGRAPHY_TIMING_PROFILE_RESULTS.md).
Timing corrections
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
offsets is not claimed to learn RF calibration. The reusable initializer then
completed [DS21-009](../2026_10_13_ds21_release_readiness/PROPOSALS_009_RESULTS.md),
including 100 discovery points, nine stationary shape fits, nine stationary
hybrid fits and 18 physical seed exports. The subsequent
[DS21-011 chain](../2026_10_13_ds21_release_readiness/PROPOSALS_011_RESULTS.md)
also completed, followed by [DS21-013](../2026_10_13_ds21_release_readiness/PROPOSALS_013_RESULTS.md).
Nine development cases have complete proposal sets and 25 still require
initialization. DS21-009, DS21-011 and DS21-013's final comparisons are now complete.
The [DS21-013 results](../2026_10_13_ds21_release_readiness/THREE_MODEL_013_RESULTS.md)
show a shared severe miss: A/all 266.840 km, B/all 268.879 km and C/all 267.760 km.
Of 54 calls, 52 are stationary; the two C failures remain excluded without retry.
All seven selected boundary flags are false. The configured reference is inside
the original 250 km prior but outside all six 25 km proposal disks; its nearest
disk gap is 157.457260 km in optimizer coordinates. The saved search ends at 100 points with 76 deferred
cells, allocating 16 / 16 / 24 / 44 points at 100 / 50 / 25 / 12.5 km spacings.
Its all-view best-first score does not certify bounds for finer cells. Fixed
local refinement cannot recover the reference, but why discovery missed and
which replacement policy works remain unresolved. The subsequent
[discovery coverage control](../2026_10_13_ds21_release_readiness/DISCOVERY_COVERAGE_013_RESULTS.md)
completed the same 100-point budget with levels 50 / 25 / 12.5 km and the original
all-view priority. It used 80 / 12 / 8 points at those levels, with 299/300
stationary fits. Its three training-selected discovery locations are
6.719 / 18.496 / 14.009 km from the reference, joined only after sealing.
All three 25 km disks now contain it. This supports broader initial coverage on
this case, but does not establish final accuracy or full-DS21 transfer. A new
qualified authority adapter preserves the original downstream numerical
stages and budgets. Its [five-stage initialization](../2026_10_13_ds21_release_readiness/COVERAGE_PROPOSALS_013_RESULTS.md)
has now completed, including nine stationary shape fits, nine stationary hybrid
fits and 18 physical exports. The union grows 37 to 40, with stored source-function
closure at most 7.275958e-12 Hz, distinct from the larger bootstrap projection
losses retained in the report. The final-model consumer passed tests and review,
model initialization completed, and the
[new A/B/C comparison](../2026_10_13_ds21_release_readiness/COVERAGE_THREE_MODEL_013_RESULTS.md)
has completed 54 calls, 52 stationary. All-band errors are A 1.509542 / B 2.021218 /
C 1.846733 km. B low/high gives 2.895507 / 7.808977 km; C gives
3.104978 / 1.065469 km. No row passes 0.5 km. The search-region miss is recovered
on this case, while C still combines worse than its high half. All selected
boundary flags are false and both C failures are retained. Candidate and physical
initialization changed together; neither a unique downstream cause nor transfer
to other cases is established. All original namespaces remain intact.
DS21-025 has passed metadata checks but has
not been frozen or initialized. No reference-derived seed or added nuisance term
is justified by these errors.

The first generic A/B/C initialization on DS21-009 failed with a bounded
carried-calibration projection convergence error, before any location fits or
reference evaluation. Its `models-v1` namespace and source archive are retained.
Read-only inspection shows Model A overwrites its initial all-view vector and
uses only timing from its initial high-view vector, making their initial
calibration projections unnecessary. The receipt does not identify which
projection failed. The subsequent [bounded replay](../2026_10_13_ds21_release_readiness/PROJECTION_009_DIAGNOSTIC.md)
finds all 18 A projections succeed; B/all/`cold-0` fails at 200 iterations despite
a residual RMS of 5.19e-12 Hz. Removing unused A projections would not fix this
failure. A new adapter must independently verify feasible physical transfer or
provide a numerically justified projection without weakening position-fit checks.
The [v2 adapter](../2026_10_13_ds21_release_readiness/INITIALIZATION_009_V2_RESULTS.md)
has now completed real DS21-009 initialization: two B/all seeds pass independent
physical source transfer, all other required A/B projections succeed unchanged,
and the native C initialization is unchanged. This initialization result alone
does not establish accuracy.
The subsequent [three-model comparison](../2026_10_13_ds21_release_readiness/THREE_MODEL_009_RESULTS.md)
completed all 54 fits, all stationary. A's final-all result is 0.658299 km;
B all/low/high gives 5.327196 / 0.790354 / 0.772167 km; C gives
1.595252 / 4.547625 / 1.758365 km. No result reaches 0.5 km. Combining bands
improves C and worsens B relative to both halves. B's selected all/high fits
reach timing constraints, not their 25 km geographic disk edges. A-0's three
original fits were retained through an exact, separately versioned metadata
review; no refit or scientific-source change occurred. All 12 reviewed outcomes
were sealed before reference evaluation. A is closest on this case, which is
not a basis for per-recording algorithm selection by reference error.
The subsequent [DS21-011 comparison](../2026_10_13_ds21_release_readiness/THREE_MODEL_011_RESULTS.md)
also completed 54 stationary fits. A/all gives 2.491943 km; B all/low/high gives
0.743996 / 1.142057 / 6.735033 km; C gives 0.479573 / 1.080449 / 3.818150 km.
Only C/all passes 0.5 km on this recording. Both B/C combinations improve on
their own halves and all selected physical boundary flags are false. These
case-dependent outcomes do not justify per-case model selection by reference.
The [75-endpoint receipt-only timing audit](../2026_10_13_ds21_039_association/TIMING_SATURATION_009_011_039.md)
has completed and passed independent reconstruction. It covers all 36 B/C
endpoints from each of 009 and 011, plus the three original 039 C controls.
Seven endpoints reach timing limits, all on 009. Its selected B/all and B/high
states bind different catalogue candidates; candidate 66266's lower bound
recurs in several other starts/views, but none binds across all six starts of
any view. No 011 endpoint or original 039 control reaches a timing/geographic
boundary. Saturation therefore cannot explain combination failures universally.
The audit makes zero new scientific calls and does not establish candidate
support or emitter identity from these limits. Its recipe was fixed before
inspecting the 011 fit results. Continuous timing/calibration confounding and
association changes remain separate unresolved mechanisms.
DS21-011 discovery also completed:
100 points, 300 fits, 293 stationary, in 446.480 seconds. Its later initialization
stages are now complete, with nine stationary shape fits, nine stationary hybrid
fits and 18 exports; this is not a position-accuracy result.

The [transmitter dynamics audit](../2026_10_13_ds21_039_association/TRANSMITTER_DYNAMICS_AUDIT.md)
identifies channel-dependent transmitted frequency corrections as a credible
omitted-effect hypothesis, not an established DS21 cause. The
[two-fixed-state, zero-fit paired-receiver diagnostic](../2026_10_13_ds21_039_association/SHARED_RECEIVER_INCREMENT_RESULTS.md)
has completed. It finds no clear reproducible shared positive excess and inadequate
CH1/CH8 support. This does not exclude beam-specific effects, but it does not
justify adding fitted transmitter corrections. Mixture assignments still do not
establish emitter identity.

**Decision:** continue the bounded development comparison and missing
initializations with unchanged objectives, matched budgets and documented seed
provenance. Report A's dependent final-all selection and B/C's own-view fits;
do not label shared bank/seed initialization as independent half-band pipelines.
Keep coverage, failures, boundary flags and frequency diagnostics separate from
accuracy. The historical five-case table remains unchanged, and the 0.5 km target
is unmet.

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
