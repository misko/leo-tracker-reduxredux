# ALGO05: timing-gap fragments with conditional satellite refresh

ALGO05 adds the evaluated `gap_conditional` recovery to ALGO04. It keeps the original native GLRT observations and graph polynomials, partitions eligible unassociated parents only at recorded gaps greater than five seconds, and independently tests each eligible fragment. This addresses a parent that fails as a whole even though one disconnected component has usable satellite evidence.

## Frozen inference procedure

1. Consume a completed, validated ALGO04 terminal through the public storage/export ports. Preserve its exact incumbent point-to-satellite owners separately for `c=0` and fitted `c`.
2. Consider retained full graph parents whose ALGO04 attempt was `RF_rejected`, whose independent nomination was `conditionally_supported_identity`, and whose points are all absent from the published incumbent. Exclude synthetic branches, graph bundles and inactive fragments.
3. Partition at adjacent time gaps strictly greater than 5 s. Require at least 12 native points and 10 s span. Reject a component equal to its entire parent. Keep the original CFO measurements, integer alias lifts and polynomial source metadata.
4. Re-run causal satellite competition on each component: three candidates, three distinct randomized whole-group partitions, the existing 12 s group/2 s guard policy, and the existing uncalibrated phase mixture. Parent confidence is not inherited. These are randomized groups, not arbitrary individual-point withholding or chronological extrapolation.
5. For independently supported components, run the paired inclusion and matched no-addition control with `--conditional-satellite-refresh`. Use the existing ALGO04 centered position derivatives and ±30 s numerical reference window. There is no new GPS constraint, no post-observation TLE and no constrained-position acceptance variant.
6. Replay exact orbits for both controls and both proposals. Require the existing frequency/residual gates, phase convergence ≤0.01 s, unchanged incumbent owners, native observation membership, and identical newly added point/owner sets in both `c` arms. Every target point must belong to the independently nominated satellite. A better frequency score alone cannot authorize publication.
7. Choose one qualified trial by highest minimum identity margin, then most added points, then stable parent track ID. Independent fits are never unioned. Publish its fitted-`c` endpoint and retain the controlled `c=0` result. On no qualification, timeout, changed input or proof/read-audit failure, retain the exact ALGO04 endpoint.

The worker has a 1,200 s add-on limit; individual prepare/annotation/inclusion/audit caps are 180/240/240/180 s. It processes the original retained attempt order. Budget exhaustion can prevent consideration of later fragments and is recorded; it does not relax any scientific gate. New completions are eligible after an explicit deployment cutoff. Existing v1/v2/v3 outputs remain immutable. The new model is `algo05-causal-gap-conditional-v1`, persisted under `fast-scan-graph-position-v4`.

## Evidence and limits

The [DS26 controlled evaluation](../2026_10_31_ds26_confident_recovery/README.md) found 505 added points in five scans for this variant, increasing pooled association from 71.03385% to 71.11149% over 148 usable fast scans. Mean position error changed from 1,323.061 to 1,318.08 m for `c=0` and 1,306.536 to 1,301.06 m for fitted `c`. Eleven unavailable scans stay unavailable. This is a modest aggregate gain, not evidence of a 500 m accuracy guarantee.

The earlier DS27 targeted experiment recovered a 35-point RX1 CH2 fragment in DS27-0004. That study considered four nominated parents; the production rule applies the same eligibility test to every retained parent, so the targeted experiment is not a complete ALGO05 cohort evaluation. Full-run results must be labeled separately from cached policy comparisons.

Shorter components have weaker sample-size-dependent tests. Passing after a timing-gap split does not prove that the original correlation vanished or that every fragment belongs to the same emitter. Controls, exact replay, independent nominations and paired ownership remain mandatory. Added totals can include incidental points also present in the no-addition control; report direct fragment gains separately when attributing localization changes.

## Implementation and deployment

The scientific adapter is `tools/algo05_gap_stage.py`; orchestration and proof reconstruction are in `tools/algo05_recovery_worker.py` and `tools/algo05_production_worker.py`. New contract, storage, application and CLI modules use the v4 suffix. The new API composition entrypoint is `python -m leo.api.production_v4`. All frozen ALGO04 scientific members are retained unchanged. Nested historical exports are verified and preserved byte-for-byte; only active scientific inputs are relocated. A process-tree read audit prevents the inference worker from reading reporting GPS, unrelated recordings or future catalogues.

Release identity, installed canaries, deployment status and post-update residual-track figures are recorded in the accompanying promotion report. Source publication alone is not a claim that a service has been activated.
