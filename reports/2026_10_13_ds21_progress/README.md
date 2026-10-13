# DS21 localization progress

Updated 2026-10-13 16:15 UTC. This is an interim measured-results report, not a
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
the next matched control examines observation weighting within the joint objective.
The [refinement report](../2026_10_13_ds21_039_root_cause/REFINEMENT_RESULTS.md)
contains the full outcomes and post-seal position comparison.
Detailed [calibration](../2026_10_13_ds21_039_root_cause/CALIBRATION_RESULTS.md) and
[association](../2026_10_13_ds21_039_association/RESULTS.md) reports are available.

## Full DS21 validation

DS21 contains 108 recordings: 54 fast CH1–8 and 54 adaptive CH1–4. The frozen
acquisition-hour split reserves 34 fast recordings for development and 20 for
locked evaluation; adaptive recordings have 35 development and 19 evaluation
members. Within recordings, randomized whole 20-second groups keep correlated
observations together. The [metadata-only readiness audit](../2026_10_13_ds21_release_readiness/README.md)
finds preparation receipts for all 34 fast development members, but discovery and
proposal caches for only five; 29 need initialization. The 54 adaptive members
have no tracking-input binding in this membership and require separate preparation.

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
research worktree, diagnostic/profile evidence through commit `ae81c4a71`, and its immutable
membership inventory SHA-256
`a701553b01ae023ea8b68b4ea6757fc7a75dc9ac7c754118b69bd8bce6003c39`.
The original protocol and detailed local receipts are retained; this report
publication does not deploy an algorithm or publish the radio corpus.
