# B059 four-arm conditional development CV

Learned catalogue detectability improves opposite-fold conditional-CFO prediction at the far fixed geography in both accepted folds. RX/channel dispersion makes a smaller improvement. The complete accepted comparisons still prefer the far geography; the nearby detectability comparison is **incomplete** because one fit fails the unchanged stationarity gate. No model or accuracy result is promoted.

## Prespecified experiment and qualification

The [protocol](MODEL_B_OBSERVATION_CV_PROTOCOL.md), commit `9b5b458ba`, declared all16 calls before outputs: two alternating20-second training folds × two existing training-derived fixed geographies × legacy joint-event, normalized conditional-CFO, normalized dispersion and normalized detectability arms. Source/model `d5a088aff` and runner `6be4886a8` were frozen before preparation. Independent source review found no blocking algebra or runner issue;23 relevant component/runner tests passed in3.46s, with Ruff passing.

The separately bounded actual-data qualification passed in22.929s:546 objective calls, zero optimizer calls. Full-data legacy objective, physical gradient and nuisance gradient replayed the original B implementation with maximum errors **exactly zero**, and posterior responsibilities matched. All260 expansion-tail coordinates across four units passed central differences at nonzero deterministic parameters: maximum dispersion error1.57425e-6 and detectability error5.28095e-8, below the unchanged declared tolerance. Actual zero-expansion nesting and conditional-minus-event `sum(log M)` closures passed. Synthetic tests cover every physical/calibration/tail derivative and unit density integrals with full/partial/no visibility. Actual physical gradients were checked against the original source oracle, rather than claiming an additional actual-data physical finite-difference audit.

Fold0 fits1521 existing training windows and predicts the other1001; fold1 reverses those sets. Each arm starts from the same complete incumbent non-geographic state, zero observation tail, and the declared far or nearby XY. Original proposal disks, fitted-c calibration, bank, orbital timing, common clocks and physical priors remain unchanged. Full-training discovery, bank, frames, clock nodes, starts and fixed geographies leak across folds: this is **conditional development CV, not untouched validation**. Original held/locked measurements and reference coordinates were never read by this experiment. The names incumbent/donor refer to the previously sealed training endpoints; this pilot performs no position-accuracy evaluation.

## Completed calls and strict acceptance

All16 optimizer calls returned, and all four unit terminals plus all16 outcomes were sealed before any opposite-fold prediction. Whole-unit elapsed times were28.973,30.397,21.035 and24.096s. Every independent call retained its original20-second/600-iteration cap; there was no retry, polish, budget reallocation or call reuse. Two workers ran alongside concurrent DS22 and operational processing, so these timings are not an isolated performance benchmark. Source guards, cache preparation and independent audits are included in the unit times.

Fourteen outcomes pass the unchanged strict KKT≤.001 gate. The two rejected outcomes are:

| Fixed geography / training fold / arm | Solver success | Reported KKT | Fit elapsed |
|---|---|---:|---:|
| incumbent /0 /legacy | true |2.027406752 |4.268s |
| donor /0 /detectability | true |.001058490 |4.285s |

Both stopped before their time caps. Solver success alone does not make either endpoint accepted. Their predictive rows remain labelled `accepted=false` and cannot complete a comparison. Accepted independently replayed KKTs range6.11e-5–4.64e-4; exact fixed XY, source domains, objective/NLL and durable return/option/seed consistency passed. All original scientific endpoints remain untouched.

## Opposite-fold predictive likelihood

The table sums predictions across both excluded folds only when both fits are accepted. It excludes all prior penalties from predictive likelihood. Event NLL and proper conditional-CFO NLL are distinct conventions and must not be compared as the same probability model.

| Fixed geography | Fitted arm | Accepted folds | Conditional-CFO NLL | Joint-event NLL |
|---|---|---:|---:|---:|
| incumbent |legacy |1/2 |incomplete |incomplete |
| incumbent |conditional |2/2 |31133.690413 |34207.201007 |
| incumbent |dispersion |2/2 |31130.291583 |34203.596377 |
| incumbent |detectability |2/2 |29944.938772 |33048.491671 |
| donor |legacy |2/2 |31534.928166 |34625.958786 |
| donor |conditional |2/2 |32165.386056 |35256.341245 |
| donor |dispersion |2/2 |31892.531383 |34983.769440 |
| donor |detectability |1/2 |incomplete |incomplete |

At the incumbent geography, detectability reduces proper predictive NLL by1188.751641 versus the normalized baseline; both folds independently improve (−475.430790 and−713.320851). Both bands and both receivers improve in each accepted fold, and each channel improves in both folds. This is not a cancellation between the two bands. Dispersion changes the complete incumbent score by only−3.398829: fold0 worsens12.189379 while fold1 improves15.588208.

At the donor geography, dispersion improves both folds and reduces proper predictive NLL by272.854673. The normalized baseline and dispersion still prefer the incumbent geography by1031.695643 and762.239799 respectively. The complete accepted legacy donor score differs materially from its normalized-control fit; changing event convention is not equivalent to subtracting one constant from independently optimized endpoints.

In fold1, where both detectability fits are accepted, the donor proper NLL17414.018470 beats incumbent18205.048005 by791.029534. Low and high bands each favor the donor there (−371.146 and−419.883). The rejected fold0 donor endpoint has diagnostic predictive NLL11678.430502 versus accepted incumbent11739.890767, but this cannot be used to declare a completed nearby detectability win or justify crossing the stationarity threshold. Its raw two-fold diagnostic sum29092.448973 is explicitly ineligible.

## Parameters and interpretation

Dispersion sigma ranges by training fold are incumbent73.393–186.481Hz /92.962–140.318Hz and donor75.674–210.244Hz /73.731–106.448Hz, within the frozen62.5–250Hz limits. This is fitted normalized likelihood, not an estimate from truncated posterior residual RMS. Dispersion-tail prior penalties are2.8715/1.5069 at incumbent and3.1310/3.4498 at donor, reported separately from predictive NLL.

Detectability retains sigma125Hz, every candidate, and the exact whole-bank probability budget1.6. Fitted q ranges are incumbent[.005817,.144984]/[.006779,.183375] and donor[.004106,.141145]/[.004122,.149847]. Observation-tail prior penalties are17.6999/16.6316 at incumbent and22.8978/27.0129 at donor. The catalogue-basis coefficient lower bound is active for2 coordinates in each incumbent fold, and3/4 coordinates at the donor in folds0/1; these are declared constrained fits, not a reason to enlarge bounds after seeing predictions. Per-window P0, visible probability/odds sums and selected-CFO normalizers are retained in the evaluation summaries. Orbital relative timing, common-clock and group priors remain original parameters; observation tails are explicitly labelled and are not reported as physical group clocks.

This supports investigating stable, nonuniform catalogue propensity rather than another blind noise-weight scan. It does not establish a beam footprint, correct satellite identities, generalization to DS22, or improved free-position accuracy. Full-derived metadata leakage, two conditional folds, local optimizer termination, fixed geographies, and the missing accepted nearby fold are practical limits. The next discriminating step is a frozen zero-fit coefficient-bound/gradient and cross-fold q-agreement audit, followed only after review by matched full-training normalized-control versus detectability nuisance profiles and accepted releases. No rejected CV endpoint is retried.

## Reproducible receipts

All outputs live in `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-observation-cv-059-v1`.

| Receipt | SHA256 |
|---|---|
| source/input protocol |`f53d0e811aa8c5eb815f4e859211175732f3346ef2b19e6447435d5153876850` |
| qualification |`eae0304da360c3133fd4534206a3a7807a22fda68f2638a618a8b14c442fb9e5` |
| all16 terminal |`62220ee6758fff584579484a64f05c6d435a50293551eddcbad01b7b473f150f` |
| all16 scientific seal |`29f7d05e2758f4559b9a3f08debdd1ae0219a46c2524cd31fdb09582239286f4` |
| postseal predictive evaluation |`bbfbf68cec1e0561fdd26ae3d6ead195ea30e1e55ec046a460b868987c109975` |

The source-frozen CLI actions are `freeze`, `qualify`, four independent `run --unit ...`, `seal`, then `evaluate`. Every numerical process used internal180/TERM195/KILL200 bounds and native single-thread BLAS. The pilot adds16 calls to the explicitly disclosed upstream fits and zero-fit qualification; it is not an end-to-end matched discovery-budget comparison.
