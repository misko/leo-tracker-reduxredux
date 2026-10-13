# DS21 localization progress

Updated 2026-10-13 18:39 UTC. This is an interim measured-results report, not a
claim that the accuracy target has been achieved. The user authorized periodic
report publication to remote `main`; research implementation remains separate.

Three approaches have been implemented and tested on five fixed development
recordings. All numbers below use **fitted `c`** and a training-objective-selected
solution. Reference position is joined after results are sealed; lower frequency
loss is not treated as proof of lower position error.

| Approach, with shared proposals | Median error km | Maximum error km | Below 0.5 km | Below 1 km |
| --- | ---: | ---: | ---: | ---: |
| [A: sequential band calibration](MODEL_A.md) | 2.601 | 6.229 | 0/5 | 1/5 |
| [B: Doppler-shape proposals](MODEL_B.md) | 2.492 | 8.600 | 0/5 | 0/5 |
| [C: joint native association](MODEL_C.md) | 1.957 | 4.899 | 0/5 | 0/5 |

The current target is **less than 0.5 km for every eligible CH1–8 DS21 recording**,
including failures as misses. None of the three approaches currently meets it.
The table covers five development recordings, not the full dataset.

## Current four-direction investigation

The [next four priorities](NEXT_FOUR_DIRECTIONS.md) incorporate the negative
controls below: temporal association; calibration/timing confounding;
likelihood-to-prior scale and correlation; initialization and dataset coverage.
Two SOL workers are implementing the next controls in parallel, with bounded
scientific runs serialized by the coordinator.

The user prioritized DS21-039, session
`fast-4b6fff793fba610ed2674dcc6d2908ba`. The original joint-model errors are
3.759 km for CH1–4, 2.557 km for CH5–8 and 4.291 km for CH1–8. Its all-band result
is worse than either half-band result.

1. **Optimization versus objective:** test whether another training-selected
   position admits a lower all-band objective after profiling calibration and
   timing. Distinguish a missed solution from a model that prefers a worse
   geographical position.
2. **Calibration, timing and RF:** verify per-observation sky-frequency Doppler
   scaling and actual receive-time clock corrections; compare physical correction
   functions and quantify local confounding with position and satellite timing.
3. **Association and frequency ambiguity:** hold the original satellite bank
   fixed and cross geometry/timing with calibration between full and half-band
   states. Measure posterior changes, clutter, visibility and discarded native
   candidate alternatives, without claiming confirmed emitter identities.
4. **Observation weighting and correlation:** measure concentration by band,
   receiver and acquisition block; inspect predetermined equal-band/equal-block
   likelihood sensitivities at frozen states. Raw window counts do not establish
   independent information.

Three SOL 6.1 high workers own the first three directions; the coordinator owns
the fourth and integration. Input inventory is complete, selecting historical
start 5 by training objective in each view. Initial replay will use no optimizer
calls. The subsequent bounded profile slice is 18 fitted-`c` fits. At this update,
the corrected four-direction diagnostic has completed in 38.73 seconds, with
zero optimizer calls and all 13 outputs/source checks passing. There are 69
passing focused diagnostic tests and eight passing profile-runner tests. The
prescribed 18 fixed-position fits have completed under a separate freeze: 17
stationary outcomes, one retained nonstationary outcome, and no retries.
The detailed [measured diagnostic results](../2026_10_13_ds21_039_root_cause/DIAGNOSTIC_RESULTS.md)
and [investigation plan](../2026_10_13_ds21_039_root_cause/README.md) retain controls,
the first run's numerical-summary failure and acceptance criteria.

The saved objectives replay exactly and RF scaling is correct. However, full
versus half fits change the preferred satellite/clutter assignment in 18–20% of
windows. Copying a half-band correction alone into the full-model physical state
worsens frequency likelihood in both bands. Equal block weights weaken one
preference but do not reverse either within-band comparison. This prioritizes
the calibration/association interaction. The completed
[fixed-position profiles](../2026_10_13_ds21_039_root_cause/OPTIMIZATION_RESULTS.md)
found an all-band objective of **32,398.260** at the high-band anchor, improving
the original **33,172.423** by 774.164 within the original search domain. Both
bands' likelihood contributions improve. This establishes a missed feasible
solution in the original search, but does not establish a position improvement.
The cold starts also fail to recover the known original objective at its own
position, so these profiles cannot rank globally optimized positions.

The subsequent seven-call control completed in 72.51 seconds with every outcome
stationary. It used three warm fixed-position fits and four free-position
continuations, with seeds and selection fixed before execution, preserving the
original objective, candidates, fitted c and geographic search domain. Its
training-selected all-band solution improves objective to **32,380.955**, but
post-seal reference evaluation shows only a small position improvement:
**4.291 km → 4.073 km**. It remains worse than the historical high-band anchor's
2.557 km. The search deficit is real, but addressing it alone is insufficient;
the subsequent matched controls examined observation weighting and native-candidate
prior mass. Neither yielded a supported fix.
The [refinement report](../2026_10_13_ds21_039_root_cause/REFINEMENT_RESULTS.md)
contains the full outcomes and post-seal position comparison.
Detailed [calibration](../2026_10_13_ds21_039_root_cause/CALIBRATION_RESULTS.md) and
[association](../2026_10_13_ds21_039_association/RESULTS.md) reports are available.

All twelve weighting fits and four candidate-prior fits were stationary. Their
post-seal, training-selected CH1–8 errors are:

| DS21-039 control | Error km |
| --- | ---: |
| Unweighted refined baseline | 4.073 |
| Equal band weights | 4.314 |
| Equal acquisition-block weights | 4.106 |
| Equal band, then block weights | 4.592 |
| Detector-winner-preserving native alternatives, fixed 25% alternative mass | 4.410 |
| One additional receiver RF contrast, common c still fitted | 4.085 |
| Satellite refresh across short within-block revisits | 4.410 |
| Fixed one-quarter likelihood weight, original physical priors | 3.930 |

None is promoted. The weighting controls preserve total likelihood weight and
prior scale; they do not test effective sample size or a correlated-error model.
The [native-prior report](../2026_10_13_ds21_039_association/DETECTOR_PRIOR_RESULTS.md)
shows another frequency-fit improvement accompanied by worse position accuracy.
Across these DS21-039 experiments, **53 completed fitted-c calls produced 52 stationary
outcomes**, retaining the one nonstationary cold profile. The 0.5 km target remains
unmet. One additional tempering invocation failed during fitter construction,
before optimizer callbacks; that failure is preserved separately. This is still
development work, not a full-DS21 accuracy result.

The [UTC provenance audit](../2026_10_13_ds21_039_root_cause/UTC_TIMING_PROVENANCE.md)
found no timestamp-conversion bug. The recorded host-clock bracket is 250.269 ms
wide with good internal clock continuity, but no independent absolute-sync or
sample-clock accuracy attestation. This is not a horizontal position-error bound.

The [receiver RF score audit](../2026_10_13_ds21_039_root_cause/RECEIVER_RF_SCORE_AUDIT.md)
found opposing receiver contributions hidden by a stationary shared `c`. The
prespecified four-call sensitivity test completed in 38.49 seconds, with all
four outcomes stationary. Retaining fitted common `c` and adding one receiver
RF contrast improved the selected objective by only 0.657, while position error
worsened from 4.073 to 4.085 km. The selected contrast was 17.471 Hz/GHz, inside
its bounds. This intervention is not promoted; see the
[receiver RF results](../2026_10_13_ds21_039_root_cause/RX_RF_CONTRAST_RESULTS.md).
The [antenna evidence audit](../2026_10_13_ds21_039_association/ANTENNA_EVIDENCE.md)
found no capture-bound pointing or beam-response data to justify a directional
satellite prior.

The [two-state residual audit](../2026_10_13_ds21_039_association/CORRELATION_RESULTS.md)
completed in 28.19 seconds with zero optimizer calls. Receiver/band block
structure persists, but cross-products change sign between the two fitted
solutions. Virtually unsupported channel tails also inflate some conditional
summaries. No stable common-clock covariance or effective sample size is
established. This leaves the coupled calibration/association model and the
information supplied by the observations unresolved; adding flexibility or
improving the in-sample frequency objective has not delivered accurate position.

The [temporal metadata audit](../2026_10_13_ds21_039_association/TEMPORAL_EVIDENCE.md)
explains the zero temporal edges: each RX/channel/visit/RF family has one
observation. Removing visit from the key would still give zero edges under the
original 25 ms limit; the shortest same-RF revisit is 352.244 ms. The recorded
candidates have no persistent emitter/frame identity. Cross-visit continuity
therefore requires an explicitly new modeling assumption, not a graph bug fix.
A new satellite-only temporal refresh component and runner passed 19 synthetic
tests, including original-model singleton closure and linked gradient checks. Its
[matched four-call protocol](../2026_10_13_ds21_039_association/TEMPORAL_REFRESH_PROTOCOL.md)
uses a fixed one-second persistence assumption, direct satellite switches and
the original stationary satellite/clutter prior. All four calls completed and
were stationary in 60.562 seconds overall. The linked model increased selected
error from 4.073 to 4.410 km and is not promoted; the
[temporal result and receipt audit](../2026_10_13_ds21_039_association/TEMPORAL_REFRESH_RESULTS.md)
record all four outcomes. The actual singleton oracle
replayed both source objectives and NLLs, with maximum comparison difference
below 6e-11; the linked model had 1,616 edges across 1,182 families. This is a
negative result for this prescribed continuity assumption, not evidence against
all temporal information.
A separate [quarter-scale likelihood sensitivity](../2026_10_13_ds21_039_association/LIKELIHOOD_TEMPERING_PROPOSAL.md)
completed four stationary calls in 39.051 seconds overall. It modestly improved
error from 4.073 to **3.930 km** (142 metres), while untempered NLL worsened from
32,225.181 to 32,227.699 and the prior penalty decreased from 155.774 to 154.666.
The [likelihood-scale results](../2026_10_13_ds21_039_association/LIKELIHOOD_TEMPERING_RESULTS.md)
retain all four outcomes and the independent receipt audit.
The scale is not an estimated noise covariance or effective sample size. It
remains worse than both original half-band results and is not promoted for
release; transfer to the five existing development cases is the next check.
The [first invocation's interface failure](../2026_10_13_ds21_039_association/LIKELIHOOD_TEMPERING_FAILURE_V1.md)
was preserved with its original source archive. A corrected v2 wrapper restores
the geographic-prior port, and 24 tests pass, including actual tiny-fitter tests
for both scales. The v2 run uses a separate freeze and result namespace.

## Full DS21 validation

DS21 contains 108 recordings: 54 fast CH1–8 and 54 adaptive CH1–4. The frozen
acquisition-hour split reserves 34 fast recordings for development and 20 for
locked evaluation; adaptive recordings have 35 development and 19 evaluation
members. Within recordings, randomized whole 20-second groups keep correlated
observations together. The [metadata-only readiness audit](../2026_10_13_ds21_release_readiness/README.md)
finds preparation receipts for all 34 fast development members, but discovery and
proposal caches for only five; 29 need initialization. The 54 adaptive members
have no tracking-input binding in this membership and require separate preparation.

A new training-only adapter around the existing fitted-c discovery core passed
all 10 owned tests in the integration worktree. Its first bounded DS21-007 slice
[completed 100 points in 335.007 seconds](../2026_10_13_ds21_release_readiness/DISCOVERY_007_RESULTS.md),
with 295 of 300 per-view fits stationary and five failures retained. Exact census
evidence, partition and causal catalogue were bound before inference. A cached
terminal validation passed without new fits. This adds one discovery result:
28 development recordings still need discovery, and 29 need downstream proposal
caches. No new position-accuracy result is claimed.

DS21-007's [fitted shape stage](../2026_10_13_ds21_release_readiness/SHAPE_007_RESULTS.md)
subsequently completed nine stationary fits in 17.446 seconds, supplying the
three required shape parents. Fresh bootstrap, absolute hybrid fitting, cold
bootstrap and six physical proposal exports remain before its final comparison.
In parallel, the [fixed five-case likelihood-scale protocol](../2026_10_13_ds21_039_association/FIVE_CASE_TEMPERING_PROTOCOL.md)
prescribes paired alpha=1 and alpha=0.25 fits from each recording's six historical
all-band endpoints. This transfer test has not yet produced results.

After a supported DS21-039 fix, test the five existing development cases, then
all 34 fast development recordings. Freeze the release before evaluating the 20
locked fast recordings. Report all 54 fast results, failures, median, upper
quantiles, maximum and count below 0.5 km. Adaptive CH1–4 coverage is reported
separately. Locked inference has not been opened; DS21-065 has a documented
preparation-only exception for five clipped-window exclusions.

Accuracy is relative to the configured reference, not an independently surveyed
location. No per-case reference tuning or selection of whichever model happens
to be closest is permitted. If the target is missed, subsequent reports will
retain the failure and distinguish development iteration from untouched
evaluation.

## Provenance

These summaries are derived from the sealed shared-proposal comparison in the
research worktree, diagnostic/control evidence through commit `c0e2941d7`, and its immutable
membership inventory SHA-256
`a701553b01ae023ea8b68b4ea6757fc7a75dc9ac7c754118b69bd8bce6003c39`.
The original protocol and detailed local receipts are retained; this report
publication does not deploy an algorithm or publish the radio corpus.
