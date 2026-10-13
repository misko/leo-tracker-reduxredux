# DS21-039: warm profiles and geographic continuations

Training-only selection chose **`free-cold-high`**, with all-band objective **32380.954534756**, an improvement of **791.468894349** over the original all-band winner. Root's subsequent sealed position evaluation improved error by only **0.218712 km**, from **4.291227 to 4.072515 km**. The requested **<0.5 km** target remains unmet. Reference positions and held observations never entered these fits, their initializers or selection.

Exactly seven fitted-c calls ran: three fixed-position warm profiles from the same original all-band training winner, then four independent free-geography continuations from the original all-band winner and the three previously sealed cold-profile winners. The free starts were fixed before the warm outcomes; warm outcomes did not seed or select the free stage. Every call used the same original all-band native inputs, 43-satellite bank, RF/time/group frame, priors, applied sampling branches and 20-second/600-iteration allowance. All seven calls used the original all-band physical start-5 center and its unchanged 25-km disk; warm XY was additionally fixed at its training-selected anchor.

Warm-all and all four free initializers replayed their known parent objective and likelihood NLL with **zero stored delta**, before any optimizer call. The warm-all oracle guards against a model or representation mismatch. Initializer receipts, attempted outcomes and retained known states remain separate; an incumbent is never presented as a successful new fit.

| Prescribed call | Initial objective | Final objective | KKT statistic | Outcome |
| --- | ---: | ---: | ---: | --- |
| Warm low anchor | 35119.956197804 | 33174.962255679 | 0.000081478 | Stationary |
| Warm high anchor | 42917.772622152 | 32681.996584191 | 0.000037480 | Stationary |
| Warm all anchor | 33172.423429104 | 33172.423429104 | 0.000658342 | Stationary; reproduces known solution |
| Free original all winner | 33172.423429104 | 33172.423429104 | 0.000535660 | Stationary; unchanged within numerical precision |
| Free cold low winner | 36780.247959074 | 36761.807895895 | 0.000122875 | Stationary |
| Free cold high winner | 32398.259712359 | **32380.954534756** | 0.000070418 | **Selected by training objective** |
| Free cold all winner | 33842.714337471 | 33829.939458278 | 0.000178271 | Stationary |

All seven attempted outcomes were stationary and interior; no call failed, regressed against its own initializer, or needed a fallback or retry. Warm-all and free-original changes of approximately 2.2e−11 and 1.7e−10 are numerical equivalence, not substantive gains. The fit phase took 47.251 seconds, with 46.635 seconds summed reported optimizer time, within the 140-second optimizer allowance. The coordinator reported 72.506 seconds including preparation, within the 240-second external bound.

The warm low profile removes most of the cold low profile's 3607.825 objective deficit. Warm-all recovers the original objective which the six cold starts missed by 670.291. However, **warm high is 283.737 worse than cold high at exactly the same fixed point**. That is a comparison between discovered nuisance basins, rather than a regression against its own initializer. These differences establish optimization-path sensitivity; neither warm nor cold profiles are guaranteed global nuisance minima.

The free winner pool comprised the original **fully stationary** all-band incumbent and the four actual newly stationary free fits. Cold fixed-XY endpoints were eligible initializers, not automatically stationary solutions to the free-geography problem. Independent receipt arithmetic verified this selector, all seven launch/termination/outcome bindings, fixed-point and disk constraints, and selected decompositions without running a predictor or optimizer.

| Same all-band model ledger | Original all winner | Selected free continuation | Change |
| --- | ---: | ---: | ---: |
| Low-band likelihood NLL | 20075.963986297 | 19705.895666688 | −370.068319609 |
| High-band likelihood NLL | 12893.535783642 | 12519.285355446 | −374.250428196 |
| Total likelihood NLL | 32969.499769939 | 32225.181022134 | −744.318747806 |
| Common-timing prior | 0.119286550 | 0.130190546 | +0.010903996 |
| Relative-timing prior | 202.405030368 | 155.243574436 | −47.161455932 |
| Group-calibration prior | 0.399342247 | 0.399747639 | +0.000405393 |
| Total prior cost, counted once | 202.923659165 | 155.773512622 | −47.150146543 |
| Full objective | 33172.423429104 | 32380.954534756 | −791.468894349 |
| Posterior native residual RMS, Hz | 104.396460339 | 92.162359124 | −12.234101215 |
| Expected signal windows | 2068.045452763 | 2167.247596343 | +99.202143580 |

All four selected decompositions have exact stored low-plus-high NLL closure and exact objective closure when band NLLs and the single shared-prior total are added. These band contributions use the all-band frame; they are not scores from separately fitted half-band models. Native residual RMS is conditional on signal assignments, and satellite responsibilities remain model posteriors rather than measured identities.

Relative to its cold high initializer, the selected free continuation lowers objective by another **17.305178** and moves **1.656034 km** from that fixed high-band point. Root's historical high-only position error is approximately **2.557 km**, better than the selected continuation's **4.073 km**. Thus this local descent moves away from a more accurate observed point while improving the training objective. The experiment exposes both a missed objective basin in the original optimization and a mismatch between local objective descent and position accuracy. It does not establish the global optimum, global objective preference, measured satellite identity, or a sufficient correction for localization.

The locally retained post-seal position evaluation, `local/refinements-v1/development-error.json`, used the configured station location; it was not independently surveyed here. It binds the already sealed terminal and protocol. Only that separate evaluation supplies the position-error comparison. No held scoring was performed.

Evidence is retained locally under `local/refinements-v1`: `fits/terminal.json`, `fits/initializer-replay.json`, `fits/initializers.json`, `freeze.json` and source archives. These raw receipts are not part of the report-only publication. See also the [immutable cold-profile report](OPTIMIZATION_RESULTS.md). All 323 live scientific source files, their archived snapshots, and frozen input/parent hashes matched. Implementation `e2e261702` passed nine new component tests and 28 combined focused tests; Ruff and independent source review were clear. The two experiments used **18 cold + 7 refinement = 25 new fitted-c calls**; original upstream fits were reused as parents and were not rerun.

| Sealed artifact | SHA-256 |
| --- | --- |
| Refinement terminal | `682bee3af1de693cd5a736e9a5eb36558db594c8b88784371909d3743298a493` |
| Refinement freeze | `6d96b165a88ad852722a7fdd0957821fa70bad2f31372e1cca261926a8b52e91` |
| Initializer replay | `506f97b03ff58cf6c5812a4789b92b927e289a81e6be35e83bfba7f0e7680899` |
| Root post-seal position evaluation | `af29fb6a6f7fce596130e3fdc71fa4d505158758b0f260d4020f0940193dfef6` |
