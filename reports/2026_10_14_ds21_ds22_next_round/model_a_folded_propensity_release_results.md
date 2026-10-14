# A035/A053: complete-fold-state full-training propensity release

**A053 reaches 0.256462 km configured error with a strict accepted, training-selected propensity fit. A035 worsens to 9.004813 km.** This is a two-case development result, not achievement of the cohort median target. Configured reference coordinates remain unconfirmed physical truth, and no original held data were consumed.

The frozen final-A architecture is unchanged: folded singleton density, fitted common RF coefficient, shared clock/timing state, and the family's learned two high-band shifts fixed in its baseline. The intervention adds the already qualified conditional-density / catalogue-propensity observation ports. No native C branch likelihood, new candidate, truth seed, offset uncertainty or free group calibration was introduced.

## Source, bounds and honest starting inventory

Source `00746eb76` adds `model_a_folded_propensity_release.py`; five owned tests and the preceding five CV tests pass, as does Ruff. The public synthetic test writes and validates all 25 outcomes through real folded objectives and JSON serialization, including strict rejection and no retry. The initial CV port also passed twenty tests.

All **nineteen accepted complete CV states** were retained, including their full physical vector, common-clock nuisance and own propensity tail. No nuisance was reset. Each model/case additionally received the same current-full common start; q started at zero only for those common controls. The five failed CV states were excluded rather than retried. The exact call inventory is:

| Case | Legacy | Conditional | Propensity | Total |
|---|---:|---:|---:|---:|
| 035 | 3 | 5 | 4 | 12 |
| 053 | 4 | 4 | 5 | 13 |

The realized starting inventories differ because CV eligibility differs. This is **not a matched-search-cost model causal comparison**. Randomized folds retain upstream full-training discovery/calibration/clock/geography leakage; full-data continuation is conditional development, not fold validation.

Exact transport qualification passed **44 objectives, zero fits**, in 29.326 seconds: nineteen independent original fixed-KKT replays plus 25 full-data seed scores. Full vectors/clock/q and fixed-shift families match their saved sources exactly, with **no initializer projection**. Original source banks **55/59** and disks **25/50 km** remain unchanged.

All **25 new free-position calls** retain 20 seconds / 600 iterations and strict full KKT ≤0.001. Eleven finite units with at most three calls ran on four single-thread workers, whole-unit bounds 180/195/200 seconds. Wave149 completed in **64.917 seconds**, all units exit 0. Twenty endpoints were strict accepted; five remain excluded. Maximum individual fit time was 12.097 seconds. The original SLSQP fitter and convergence rules were not changed.

Every outcome and **own-model training selector** sealed before configured-reference access: seal `6a1c95f720b833c97ebe5d22c849ebdf9f0588919c5b53b6ffd213e5abf4b4e9`. Post-seal evaluation took 10.003 seconds, eight objectives, zero fits. Each model selected its minimum-objective strict full-data endpoint; neither opposite-fold prediction nor position error selected a start.

## Selected outcomes

| Case / model | Strict fits | Selected source | Own full objective | Full KKT | Radius from own center km | Configured error km |
|---|---:|---|---:|---:|---:|---:|
| 035 legacy | 3/3 | common | 35642.819252 | 0.000143313 | 7.599 / 25 | **6.289664** |
| 035 conditional | 5/5 | fold0, own-low geography | 31998.112908 | 0.000140417 | 7.552 / 25 | 6.509421 |
| 035 propensity | 2/4 | fold1, current-full geography | 30174.189041 | 0.000097955 | 6.096 / 25 | **9.004813** |
| 053 legacy | 3/4 | common | 23498.663735 | 0.000314374 | 31.310 / 50 | **3.476405** |
| 053 conditional | 3/4 | fold0, current-full geography | 21049.182951 | 0.000316935 | 33.445 / 50 | 1.229751 |
| 053 propensity | 4/5 | fold1, current-full geography | 19370.784820 | 0.000389571 | 34.332 / 50 | **0.256462** |

Objectives belong to different likelihoods and are not directly ranked across model rows. The original legacy incumbents survive their common-start controls to numerical precision. All selected points are interior to their own local disks. A053's selected complete q fold state moves **3.293 km** after release; A035's moves 3.070 km.

Frequency effects are separate from position accuracy. The following are each model's per-band **raw joint-event NLL**, replayed at its selected endpoint; posterior assignments also change, so lower loss alone is not position evidence:

| Case / model | CH1–4 event NLL | CH5–8 event NLL |
|---|---:|---:|
| 035 legacy | 20664.912028 | 14603.986411 |
| 035 conditional | 20659.462020 | 14589.460225 |
| 035 propensity | 20108.815240 | 13420.162866 |
| 053 legacy | 15606.688314 | 7606.432784 |
| 053 conditional | 15491.117629 | 7568.849360 |
| 053 propensity | 14580.299593 | 6908.201068 |

A035 improves both bands' frequency likelihood while position worsens. A053 improves both here despite its preceding q CV conditional-NLL total being **worse by 377.047** at the fixed current-full geography. These are distinct selection/generalization/localization quantities.

The propensity budget remains Σq=1.6. Selected A035 has q range 0.00210–0.15585, six coefficient bounds active and propensity prior penalty 39.7465. A053 has range 0.00242–0.14520, four active bounds and penalty 35.4768. Separate timing/clock/propensity priors, conditional-CFO NLL, emission normalization, posterior masses and per-receiver results are in the numeric receipt. No coefficient bound was widened.

## Remaining optimization and scientific limits

There are feasible lower-objective **nonstationary** q outcomes: A035 common J=28882.674102, KKT=0.002364824; A053 common J=19314.770184, KKT=0.001045855. Both reported solver success, returning in 11.209/4.921 seconds; neither was a 20-second timeout. They remain excluded, with no retry or relaxed threshold. Another A035 q failure and the original-model failures are also retained. These facts preclude claiming globally optimized model comparisons. At the selected conditional endpoint embedded with zero q tail, neither case beats its selected q objective; that narrower nesting check does not remove the other optimization gaps.

The new experiment costs **49 real calls**: 24 CV plus 25 release, excluding inherited discovery/sequential/union/radius work. New exact-plan qualifications cost 24+44 objectives, endpoint audits 24+25, post-seal scoring 24+8; inherited 252-objective port qualification is separate. Six common controls and all accepted complete fold states were retained; no best-by-reference subset was used.

No independent half-band position fits were made. The next useful check is a prespecified same-selected-state conditional CH1–4 / CH5–8 view comparison, retaining full training-derived bank/frame/fixed shifts and explicitly labelling leakage; it would not become an independent half-only A pipeline. A035 also retains a genuine convergence gap before any claim that q worsens the best available localization. No additional fits are authorized by this report.

[Complete states, outcomes, exclusions and provenance](model_a_folded_propensity_release_results.json). Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-folded-propensity-release-035053-v1`.
