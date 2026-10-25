# Fast-scan localization: phase/shape controls and a frozen later-recording test

Date: 2026-10-25. This iteration extends the [review of prior approaches](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_25_ds24_next_directions_review/README.md) and [causal identity/component study](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_25_ds24_identity_components/README.md).
Three SOL xhigh agents handled synthetic experiments, independent numerical auditing, and input readiness/publication; the coordinator ran the later-recording comparison and synthesized the findings. No production algorithm, dataset membership, golden fixture or operational association is changed.

**The later-recording test does not reproduce the earlier RX1 correction's roughly 100 m mean gain.** On eight frozen later fast scans, the primary policy improves mean error by only 2.7 m with c=0 and 15.4 m with fitted c, while both tails worsen. The new synthetic factorial implicates both timing and shape in conditional information loss. Together these results strengthen the case for discriminating identity/geometry and specific model-coupling tests; they do not support promoting the receiver correction or narrowing orbital priors.

## What the accumulated experiments establish

The evidence favors a precision problem involving satellite timing/shape uncertainty, shared receiver effects and ambiguous identities. It does not establish one universal cause or show that maximizing the number of associated points minimizes position error. All-channel results already outperform either half on average.

| Direction | Measured result | Implication |
| --- | --- | --- |
| Graph, EM, Hough and multiple-hypothesis polynomial constructors | First DSX01 scan: roughly 90–93% of points can be assigned to polynomial fragments, before satellite identification. | Finding a smooth curve and identifying a satellite are different tasks. Polynomial coverage is not satellite-association accuracy. |
| ALGO02 versus ALGO01 | On 404 matched DS23 recordings, fitted-c mean/median error improves 1.870/1.602 → 1.508/1.249 km. | The established pipeline improvements are substantial, though still short of the desired precision. |
| All channels versus channel halves | Same 24 usable DS24 fast scans: fitted-c means 1.220 km for CH1–8, 1.558 km for CH1–4, 2.040 km for CH5–8. | All channels help, but overlapping uncertain satellite families limit their incremental information. |
| Continuous-position restarts | Thirty targeted restarts agree within 2.06 cm; four half-channel label transfers produce no qualified better full-data result. | Generic multistart is low priority for these tested identities. This does not exclude different discrete association modes. |
| More native-point recovery | DS23 fitted-c postfit coverage 70.71→74.41%; mean error 1.434→1.426 km, P95 3.082→3.202 km. | More accepted observations can increase the tail error. Coverage and position accuracy need separate reporting. |
| Cleaner receiver measurements | Remeasuring 322 RX2 curves reduces median fixed-degree scatter 78.07→22.18 Hz without a qualified cohort accuracy gain. | Measurement scatter alone is not the demonstrated main bottleneck. |
| Frozen shared RX1 correction, development cohort | On 24 DS24 scans, fitted-c mean 1.220→1.120 km; 11 improvements, seven regressions, six fallbacks. | A promising average needs a later-recording test and explicit regression accounting. |
| Known-nuisance information controls | Median conditional weak-axis scale: 534 m ordinarily, 386 m with receiver terms known, 110 m with timing known, 56 m with timing and shape known. | Orbital timing is strongly confounded with position. These are unavailable-information controls, not achieved errors or calibrated confidence intervals. |
| Causal identity competition | Two of four proposed new families have close alternatives; one changes preferred identity between c arms. | A physical fit needs an explicit unresolved outcome; a smooth residual is insufficient evidence of identity. |

Historical figures and their distinct cohorts are documented in the linked review. They are not sequential gains that can be added together. The current DS24 reference is fresh ALGO02-v1 plus qualified causal signed timing means and equal-assignment-prior family cavity, not unmodified ALGO02 alone.

ALGO02's matched accuracy comparison also has a qualification tradeoff: it returns positions on 404/413 attempts versus ALGO01's 407/413. Early [DSX01 satellite-fit experiments](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_17_dsx01_satellite_association/README.md) held the known position fixed. Their fit/association outcomes are useful diagnostics but do not measure the current regional, unknown-position inference task.

The median phase/weak-position correlation in the earlier local analysis is 0.935. Additional bands share a median 11 calibration families and have weak position axes only 17.7° apart. A new channel frequently repeats the same uncertain orbital constraint. Here **phase means orbital time displacement**, not carrier phase.

All usable DS24 fast scans in the channel comparison use 10 MS/s, so those data do not identify a causal sample-rate effect. A nominal 40° feed separation changes sky coverage; without a measured bearing or physical baseline it does not provide a triangulation angle. Same-rate differences between receivers also make sample rate alone an inadequate explanation.

## New experiment: separate generating timing and shape deviations

We completed a paired 2×2 design on the same eight artificial realizations: two fast-scan geometries, two artificial locations and two noise seeds. All four cells share native IDs, noise, receiver coefficients, source constants, aliases, selection and inference priors. Only the generating orbital timing and physical-shape deviations change. Inference receives neither their true values nor the artificial position.

The original and both-removed cells reuse the preceding 32 fit outputs unchanged. The two new cells require 32 additional c-arm fits. Every attempt completed; 30 new fits pass the original gates. Both failures belong to the same zero-shape realization and fail the original slope checks. All completed outcomes remain in these diagnostic summaries.

| Generating condition | Mean error c=0 / fitted-c, km | Maximum c=0 / fitted-c, km | Qualified per c arm |
| --- | ---: | ---: | ---: |
| Original timing and shape deviations | 0.460 / 0.469 | 1.059 / 1.094 | 8 / 8 |
| Timing at causal prior mean; shape retained | 0.397 / 0.403 | 0.944 / 0.993 | 8 / 8 |
| Shape deviations zero; timing retained | 0.402 / 0.405 | 0.837 / 0.832 | 7 / 7 |
| Both removed | 0.295 / 0.297 | 0.522 / 0.571 | 8 / 8 |

![Every artificial realization and generating cell](synthetic/factorial_errors.png)

The mean marginal error reduction is about 85/88 m for timing removal and 80/85 m for shape removal in c=0/fitted-c. Neither dominates consistently; some realizations worsen. Removing both has a larger effect than either alone. The observation construction itself contains a phase–shape interaction because the shape design changes with orbital phase. Endpoint interactions therefore do not isolate optimizer error.

![Paired timing, shape and interaction contrasts](synthetic/factorial_effects.png)

These are interventions on synthetic truth with unchanged inference, not deployable corrections or a reason to narrow real priors. The simulator fixes labels and inherited selection and uses engineering orbit modes; it does not validate satellite identity, model every real receiver defect, or establish a precision floor. The [full findings](synthetic/FINDINGS.md) preserve all failures, paired contrasts, native observation archives, objective components and limits. Independent preflight and terminal audits pass. The 32-fit batch took 58.36 s, with 199.99 s through fixed gate replay under the 600 s cap.

## Later-recording validation

The first eight chronologically eligible, complete 10 MS/s recordings after the previous cutoff were selected before full contract validation or new geographic reads. Their canonical capture times span 2026-10-24 15:22:09–21:53:51 UTC. These research labels RX1V-0001…0008 do not change DS24 or create DS26. All eight input validations and fresh baseline reconstructions completed; no case was replaced. The scoped exposure audit found prior metadata mentions but no matching research outcome in its checked authorities. It cannot prove nobody inspected a production outcome elsewhere.

The candidate is the unchanged `fast_rx1_rf50`: a smooth shared RX1 correction, 31 Gaussian centers at 10 s spacing from 0…300 s, width 5 s, 50 Hz prior scale at 11.5 GHz, proportional RF loading and affine projection. All original observations, identities, aliases, masks, powers, physical priors and predictive evidence remain fixed. The original paired RF/phase gates alone decide adoption; a rejected pair retains the exact fresh baseline. No geography, improved RMS, or choice of the better c arm is used to select a result.

A matched cold baseline uses exactly the candidate's cold start, five phase rounds and 48 optimizer iterations per round without the added RX1 basis. Its position, RMS and objective reproduce the fresh reference exactly for every case and both arms. The candidate differences therefore do not arise from this restart/budget distinction.

| Arm | Method | Qualified / selected | Mean error, km | Median, km | P95, km | Maximum, km |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| c=0 | Fresh reference | 8 / 8 | 1.242579 | 0.933348 | 2.830039 | 3.415129 |
| c=0 | Frozen RX1 policy | 8 / 8 | 1.239835 | 0.891124 | 2.998630 | 3.720985 |
| fitted-c | Fresh reference | 8 / 8 | 1.239054 | 0.884425 | 2.829220 | 3.405038 |
| fitted-c | Frozen RX1 policy | 8 / 8 | 1.223610 | 0.876498 | 2.955866 | 3.665544 |

Six candidate pairs pass; two fall back. In both arms, three policy results improve and three worsen. The two unchanged results are exact fallbacks. Raw candidate diagnostics, including both unqualified pairs, have mean errors 1.234156/1.222359 km and four improvements/four regressions. They do not become eligible by having a smaller geographic error.

![Every later recording, both c arms, exact fallback and raw diagnostics](validation/report/paired_errors.png)

| Later case | Fitted-c reference → policy, km | Outcome |
| --- | ---: | --- |
| RX1V-0001 | 0.701 → 0.583 | Improve |
| RX1V-0002 | 0.735 → 0.551 | Improve |
| RX1V-0003 | 0.685 → 0.685 | Exact fallback; raw candidate fails a curved residual gate |
| RX1V-0004 | 0.197 → 0.202 | Worsen |
| RX1V-0005 | 1.760 → 1.638 | Improve |
| RX1V-0006 | 1.034 → 1.068 | Worsen |
| RX1V-0007 | 3.405 → 3.666 | Worsen; largest error in both methods |
| RX1V-0008 | 1.396 → 1.396 | Exact fallback; raw candidate fails a predictive residual gate |

On 0003, the rejected curved source is RX1 CH7 T004, 27 points, associated with 52288; its c=0 conditional slope z is 3.238. On 0008, the rejected predictive source is RX1 CH3 T003, 31 points, associated with 62897. Both pairs are rejected under the unchanged rules. Their identities are inherited model assignments, not newly established satellite truth. No gate is relaxed because the 0003 diagnostic happens to improve position.

![Later-panel error distributions, all eight selected cases](validation/report/error_ecdf.png)

Frequency fit improves much more consistently than geography. Primary-policy mean curved RMS falls 81.195→77.526 Hz for c=0 and 81.172→77.510 Hz for fitted-c. Mean negative-twice-ELBO changes are −92.889/−93.012 on the unchanged observations. The largest-error scan 0007 improves fitted-c RMS by 5.917 Hz while position error increases by 261 m. This is direct later-panel evidence that improved fit does not identify a beneficial position correction.

![Same-data RF fit changes versus geographic error changes](validation/report/RF_vs_position.png)

The actual position likelihood remains **24,122/33,859 distinct native GLRT points (71.2425%)** in every method and both c arms. Postfit accepted coverage is a separate output: 24,726→24,949 (73.0264→73.6850%) for c=0 and 24,703→25,013 (72.9584→73.8740%) for fitted-c. The primary policy loses no baseline accepted IDs. The two unqualified raw candidates together lose 58 baseline postfit IDs per arm; those losses remain in the diagnostic table and are not hidden or converted into a new adoption gate. Postfit extensions are not additional observations in this position comparison.

The eight-case campaign took **584.26 s wall time**, four case workers and one BLAS thread each, under its frozen 1,200 s total and 600 s/case caps. Cases took 119.83–327.12 s. These timings include input export/preparation, fresh baseline association, cavity comparison, four control/candidate refits and postfit coverage checks; they are not an embedded runtime estimate for the RX1 basis alone.

The independent RF audit replays all 48 saved endpoints and original decisions in 29.79 s cumulative audit time. Its first pass preserved a technical failure: the original curved-only 0001 baseline summary stores its final phase change in the five-epoch history rather than a top-level field. A separately frozen, tested audit-only accessor reads that existing value (6.626e−5/4.738e−5 s), without modifying any scientific result. The initial failed audit/seal is retained. The authoritative [RF_seal02.json](validation/RF_seal02.json) passes; the frozen evaluator ran once afterward. [Independent geographic checks](coordinator_geographic_checks.json) reproduce all 64 table distances and aggregate statistics exactly, including raw diagnostics.

Six supervisor tests cover immutable outputs, qualification checks, deadline handling and owned process-group cleanup; ten evaluator fixture tests cover sealed inputs, exact fallbacks, partial/unavailable outcomes and plot denominators. The synthetic transformation tests and independent audit-accessor tests are preserved with their branch receipts. No test rewrites a scientific fixture or changes a production component.

**Decision: retain the current reference; no ALGO promotion.** The new panel has small mean gains and worse tail errors, so the earlier development gain is not replicated at a comparable magnitude. Eight same-site recordings do not estimate a universal effect, and their P95 is a small-panel descriptive statistic. Retuning a selector on these outcomes would require another validation panel. The [complete table and evaluator](validation/report/FINDINGS.md) preserve all selected cases, qualifications, frequencies, ownership, fallbacks and raw results.

## Directions that remain worth testing

1. **Make new-family identity decisions falsifiable.** Use the existing full causal catalogue nomination, symmetric aliases, timing/shape uncertainty and an unresolved alternative. Test whether the rule rejects plausible wrong satellites and whether the true synthetic source reaches its shortlist. An injected source must not force its true identity into the candidate set. Where an independently selected complete curve exists, predict it from the discovery curve while carrying shared satellite and receiver uncertainty. The existing four nominees are explanatory cases, not an untouched accuracy benchmark.
2. **Allocate recovery effort to additional position information.** On an identical candidate pool and fixed budget, compare length/count ranking with improvement in the weak position direction after accounting for timing, shape and receiver uncertainty. A long additional curve from an already uncertain family can be less useful than a shorter curve with different geometry or missing time coverage. Information ranking allocates search effort; it does not certify identity. A small comparison with at most one recovered source per scan is more informative than another unrestricted recovery campaign.
3. **Investigate a specific missing coupling, not generic extra flexibility.** The new factorial makes phase-dependent shape design a concrete candidate for a bounded fast-scan approximation check. Earlier DS23 nonlinear-phase integration already found at most 22.8 m predicted local shifts with shape design and noise precision held fixed. A new test must include an omitted coupling, use the same prior law on both sides, compare fixed RF-selected positions and demonstrate numerical convergence before fitting a new position policy. It is possible that the existing model is already adequate; failed numerical qualification must remain a result.
4. **Require independent support for receiver corrections.** The RX1 model's later-panel mean/tail result lowers its priority as a general localization fix. For a new physical receiver hypothesis, use existing same-satellite observations across receivers/bands and fixed native IDs. Differences can diagnose relative hardware behavior but share their source observations; adding them again as independent likelihood terms would double-count evidence. Prefer a physically witnessed correction to more arbitrary per-track polynomials. The 0007 regression is a useful falsification case, but should not be used to invent a geographic veto or tuned blacklist.

The opportunity is to add constraints that distinguish position from orbit/receiver changes, and to reject misleading constraints. Repeating generic multistart, increasing association percentage without an information test, narrowing priors using evaluation GPS, or repeating old soft-label and local phase-integral experiments unchanged has low expected value.

A useful decision sequence is: first test whether the correct identity survives ordinary nomination; then whether independent whole-source evidence distinguishes it; then whether its addition supplies a new position direction after nuisance uncertainty is included. Only after those checks should a new family move the position estimate. If an experiment with known identities and a matching generative model still has large errors, examine information and inference; if that experiment succeeds while real data disagree, investigate missing physical effects and selection. The present synthetic and real cohorts differ, so their mean errors cannot be subtracted to estimate a real-data model-bias magnitude.

The literature is consistent with investigating orbit uncertainty. Stock, Schwarz and Knopp report orbit information as the largest error contributor in their standalone static Starlink Doppler error-budget study; that is supporting context, not a diagnosis of our recordings ([primary abstract](https://www.ion.org/publications/abstract.cfm?articleID=20093)). Hasan et al.'s differential framework uses a separate known-position base receiver, so its results do not transfer directly to our two co-located feeds ([primary paper](https://arxiv.org/abs/2409.05026)). Both sources were checked on 2026-10-25; the first was reviewed at abstract level.

## Controls, interpretation and replay

Both experiments retain matched c=0/fitted-c observations, candidate sets, other priors and search budgets within each comparison. Frequency fit, qualification, observation ownership, postfit association and geographic error remain separate. The search region is the existing 25×25 km box centered at 37.906,-122.545; 37.849061591561885,-122.48574968092912 is evaluation-only. No postscan TLE inference, GPS-selected candidate, stationary-position pooling, new IQ collection or moving-trajectory prototype is introduced.

The later panel's hardware/configuration matches the earlier deployment, but the contracts do not independently certify no relocation. Any geographic comparison retains the stated same-site assumption. A later same-site block cannot establish transfer to a new location.

[Replay notes](REPLAY.md), [readiness findings](readiness/FINDINGS.md), [execution protocol](validation/PROTOCOL.md), [independent RF and evaluation review](audit/RF_AUDIT_FINDINGS.md), [identity falsification design](audit/IDENTITY_FALSIFICATION_DESIGN.md) and the linked branch artifacts explain exact inputs, code, dependencies and remaining limits. The publication preserves new code, derived results, synthetic observations, figures and hashes; it does not duplicate all original tracking inputs, causal TLE banks or the full runtime. A hash binds external bytes but does not supply them. No standalone clean restoration is claimed.
