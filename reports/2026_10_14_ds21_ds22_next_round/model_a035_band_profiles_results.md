# A035 complete-state profiles: lower training score, no accuracy gain

The sole strictly accepted fixed profile and its free-position continuation
lower the contrast model's training objective, but increase its configured
position error from **7.264394 to 7.296745 km**. The shared model retains its
**7.223109 km** incumbent. This conditional development experiment does not
achieve the localization target or justify promoting the contrast model.

| Own model | Eligible full selector | Objective before → after | NLL before → after | Error before → after (km) | New selected KKT |
|---|---|---:|---:|---:|---:|
| Shared satellite detectability | Retained full incumbent | 28882.674102 → unchanged | 28571.605383 → unchanged | 7.223109 → unchanged | Incumbent 9.97e-8 |
| Band contrast detectability | Low-half complete state → fixed XY → FREE | 28647.017116 → 28554.575754 | 28323.943810 → 28276.700316 | 7.264394 → 7.296745 | 0.000465717 |

Objectives are ranked only within their own models. Their priors differ.
The contrast improvement decomposes into 47.243494 lower NLL and 45.197867
lower prior penalty; the selected geography moves about 81 m. A better
training fit therefore remains distinct from better position accuracy.

## Frozen finite experiment

For each shared/contrast model, both training-selected LOW/HIGH positions
were crossed with the current full or corresponding half complete nongeographic
state. Timing, clock, RF calibration and propensity states were transferred
together without resetting them. These are conditional views of the same
full-derived bank, frame and frozen learned shifts, not independently trained
half-only A models. Both models retain their original 25 km disk, fixed bank55,
smoothing width 1e-5, priors, fitted c and strict projected KKT ≤0.001.

The source-frozen qualification used **10 objectives, zero fits, 5.695 s**:
two independent full-incumbent replays and all eight feasible fixed seeds.
The initializer check forbids new projection; it retains the established tiny
timing gauge tolerance. Eight fixed outcomes then completed before any FREE
continuation. Every strictly accepted fixed state was released. The current
full incumbents remained eligible throughout.

Each numerical attempt retained 20 s and at most 600 actual objective calls,
including the independent endpoint audit (599 optimizer evaluations reserved,
one final audit). The experiment consumed **9 optimizer calls and 4672 actual
objective evaluations**, plus the 10 qualification evaluations. There were
eight fixed attempts, one FREE attempt, and seven explicit zero-call skips.
The fixed wave used four single-thread workers; the continuation wave needed
one worker. No failures were retried.

## Every fixed outcome retained

| Fixed source | Actual objectives | Fit seconds | Result |
|---|---:|---:|---|
| Shared LOW XY / full nongeo | 479 | 20.026 | Time unavailable, no returned endpoint |
| Shared LOW XY / half nongeo | 526 | 20.065 | Time unavailable, no returned endpoint |
| Shared HIGH XY / full nongeo | 589 | 20.032 | Time unavailable, no returned endpoint |
| Shared HIGH XY / half nongeo | 579 | 20.052 | Time unavailable, no returned endpoint |
| Contrast LOW XY / full nongeo | 381 | 11.154 | J28642.414267; rejected KKT0.005051745 |
| Contrast LOW XY / half nongeo | 600 | 17.174 | J28555.400561; accepted KKT0.000387686 |
| Contrast HIGH XY / full nongeo | 599 | 17.306 | Evaluation cap, no returned endpoint |
| Contrast HIGH XY / half nongeo | 599 | 17.126 | Evaluation cap, no returned endpoint |

The accepted contrast LOW/half profile's FREE continuation used **320 actual
evaluations in 8.750 s**. It reduced J by another 0.824807 and passed the
independent strict full audit. Missing endpoints have no invented score or KKT.

The original metadata validator incorrectly refused even rejected timeout
outcomes whose final evaluation ended 26–65 ms beyond the wall budget. The
original frozen runner and all receipts are preserved. A new receipt-only
adapter pinned all eight original launch/call/terminal/termination inventories
and the exact qualified seeds. It treats overruns as **unavailable**, never
eligible, and launched no replacement fixed fits. Both the original and
adapter sources remain frozen. Component checks passed **12 tests**, including
actual shared/contrast fixed fitting, rehashed seed tampering, orphan rejection,
complete-state transport, and rejection of over-budget accepted endpoints.

All eight fixed outcomes were pinned before the single new FREE fit; all
eight explicit FREE outcomes and the own-model selectors were sealed before
the configured reference was read. The global seal is
`sha256:72ccfa7858610f6ab4eeaffb6dfb48c9a2c3c93bd31b26af2f025f9b554d2511`.

## Interpretation and next falsifiable control

The contrast result demonstrates another attainable strict full-model basin
with a lower training objective and slightly worse configured position. It
does not establish that timing, clock or detectability alone causes the shared
bias. Opposing band gradients at a full optimum are expected and are not
themselves evidence of model misspecification. The earlier randomized-block
A035 contrast CV result remains **469.017885 worse opposite-fold NLL**;
this profile experiment adds no held-out validation.

Convergence attrition is substantial: only **1/8 fixed profiles** was strict,
and the four shared profiles exhausted time before the evaluation cap. A
limited next control could compare the same four shared fixed seeds under
declared 20/60 s budgets in a new namespace, with the same finite evaluation
cap and every failure retained. This would test budget sensitivity rather
than introduce a new calibration parameter or claim a model comparison.
No further fits were launched here. The contrast score/accuracy discrepancy
remains negative regardless of that unresolved shared search inventory.

Sources: bulk `model-a035-band-profile-control-v1` and
`model-a035-band-profile-continuation-v1` under
`/srv/bulk/leo-research-ds21-ds22/2026_10_14`;
[complete numeric inventory](model_a035_band_profiles_results.json).
The configured reference and physical continuity remain unconfirmed. The
recording was already exposed development data. No held-out measurements,
new RF collection, reference-chosen seed or model selection by accuracy was used.
