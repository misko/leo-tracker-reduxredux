# B059 accepted CV-state preservation changes the selected full-training mode

The training-only full-target selector now chooses an accepted nearby continuation at **1.129758km**, versus332.957657km for the preceding same-common-start propensity experiment and333.217856km for original B. All three accepted CV states were continued exactly once; the two existing full-target incumbents remained eligible. No reference entered starts, fitting or selection. This repairs the gross wrong-mode selection in this development case, while remaining above both1km and.5km targets.

## Independent full-target replay before fitting

Source/protocol `88fae6803` passed three owned tests and Ruff before source/input freeze. The [protocol](MODEL_B_CV_CONTINUATION_PROTOCOL.md) declared all three accepted CV propensity states, their original disks, both existing full-q incumbents, exact target likelihood/priors and strict acceptance. The rejected nearby CV fold0 state was excluded and remains unchanged.

Eight objective calls and zero fits in13.199s replayed five full-target states and three original fold-training states. All source-fold posterior/residual/q transport errors were **exactly zero**, all additive NLL/prior checks passed, all original disks/nuisance boxes were feasible, and original fitter initializer adjustments were zero. Fold acceptance and full-target stationarity were kept separate:

| Accepted CV source | Full-target objective before continuation | Full-target FREE KKT |
|---|---:|---:|
| incumbent fold0 |29538.421700 |1936.188510 |
| incumbent fold1 |29681.793488 |1864.332085 |
| donor fold1 |28410.688381 |2658.515305 |

All three were full-nonstationary and could not be selected as accepted full solutions at this stage. Nevertheless the nearby state's full objective was943.306348 below the accepted far incumbent. This verified a missed coupled nuisance/timing basin under the same model, rather than assuming its likelihood fundamentally preferred the far location. The [common-start report addendum](MODEL_B_DETECTABILITY_FULL_RESULTS.md) preserves that distinction and the original eight-call outputs.

Both existing full propensity endpoints independently replayed exact objectives and strict FREE KKT (.000417021/.000141713), preserving their incumbent eligibility.

## Three fixed-budget continuations and sealed selection

Exactly three free full-training calls ran in declared order, starting from each complete unchanged accepted CV vector/nuisance. They retained original own25km disks, full bank/metadata, folded B frequency physics, fitted-c calibration, orbital timing/common clocks/group offsets, sigma125Hz, whole-bank sum(q)=1.6, q basis/box±2/N(0,1) prior/scales.5. No common-incumbent nuisance was substituted, no call was skipped after an early improvement, and no bound or tolerance changed.

Every call kept20s/600 iterations. The one-worker whole slice completed in32.636s within internal180/TERM195/KILL200, including guards/preparation/independent audits. All three outcomes and the five-state training selector sealed before any reference join.

| Endpoint | New call | Accepted | Full objective | Conditional-CFO NLL | Development error km | KKT |
|---|---|---|---:|---:|---:|---:|
| existing incumbent |no |true |29353.994729 |28724.200156 |332.957657 |.000417021 |
| existing donor |no |true |29541.663720 |29133.866596 |1.563192 |.000141713 |
| CV incumbent fold0 |yes |true |29231.138839 |28653.047217 |332.381759 |.000312017 |
| CV incumbent fold1 |yes |false |29141.945625 |28503.808472 |333.738178 |.002250071 |
| CV donor fold1 **selected** |yes |true |28054.858757 |27715.632058 |**1.129758** |.000136640 |

The rejected far fold1 call reported solver success after4.634s, so its failure was not a20-second timeout. Its raw return remains preserved; it received no retry or acceptance relaxation. The other optimizer times were9.980s and3.800s. The accepted nearby endpoint wins the best accepted far endpoint by1176.280081 objective units:937.415159 better likelihood plus238.864922 lower total prior. This is a genuine same-model training score reversal with independent stationarity, not choosing a closer but worse-scoring endpoint.

The selected total prior is339.226699, including q prior32.117368 and group-offset prior.404903; the accepted far continuation's total prior578.091621 includes q19.439775/group.373230. Remaining penalties are original orbital timing and common-clock priors. Likelihood and prior effects remain separately reported; the likelihood itself now favors the nearby accepted state.

## What this establishes and what remains

Preserving complete training-derived CV states changes which full-training basin the optimizer reaches. The earlier same-common-start far selection was therefore not sufficient evidence of an unavoidable target-model preference for the far mode. The controlled new source inventory used all accepted CV propensity states, original disks and unchanged target parameters, rather than privileging the one known nearby state or retrying a rejected CV fit.

This result does not isolate whether nonuniform q is essential: matched normalized-uniform/legacy CV-state continuations have not been performed. It also does not prove a global optimum, validate catalogue identities, resolve RF-mapping authority, or establish generalization. Original held/locked observations were never read. CV bank/frame/discovery/initializers/geographies were derived from full training, so its predictive evidence remains conditional development CV.

The new selected error is below the historical original B low/high results6.741339/2.563161km on this same case, but those halves use the original score convention. The new propensity model's halves have not been refitted under a matched protocol; this is not a consistent-version three-view promotion or a sub-km success. Original histogram/baseline outputs remain unchanged. The total additional optimization cost in this observation-model sequence is16 CV +8 common-start full-training +3 continuations =27 calls, beyond all earlier upstream work; it is not a three-call standalone localization method.

## Frozen receipts

Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-cv-continuation-059-v1`.

| Receipt | SHA256 |
|---|---|
| eight-objective qualification |`b32e8dedd30d40b25d2416ebc0b0977a9eb95dfb0edac4a8e1aafa6c78290f69` |
| three-outcome terminal/selector |`163a6eb949f6dda1e7a440d6136db6df6f5873f8fe0325c86d4e9e1f3596aed7` |
| pre-reference scientific seal |`20d979d9f293d3f718723e45902c3d788738122ade785b17181490c409c68238` |
| postseal error evaluation |`c8bf773d917d0a06ea7658a5d1e8ba3da7b72141cdc77249343d9abda41ffef3` |

Postseal reference evaluation took12.781s and zero optimizer calls. Numerical replay used internal120/TERM135/KILL140; the three-call optimizer slice used180/195/200. Original held/locked observations remained untouched in every stage.
