# DS21-013 coverage-control fitted-c three-model results

The fixed dense-grid coverage control reduces the original severe DS21-013 CH1–8 misses from 266.839679 / 268.879362 / 267.759878 km for A/B/C to **1.509542 / 2.021218 / 1.846733 km**. None of the seven reported rows meets 0.5 km. This is a substantial single-case recovery within the new proposal domains, not successful target qualification or evidence of full-DS21 accuracy.

All **12 model outcomes and 54 call receipts** were sealed before the seven configured-reference rows were joined. **52 fits are stationary**; two nonstationary C fits remain saved and excluded from selection. The [receipt audit](COVERAGE_THREE_MODEL_013_AUDIT.json) validates source archives, parent and initialization authority, every unit/call/launch/termination binding, numerical receipt fields, the narrow A-high metadata scope and all seven training selections. It uses stored data and scalar arithmetic only, with no new fitting, physical predictions, objectives, KKT or reference-error calculations.

## Saved accuracy comparison

| Model | View | Original error, km | Control error, km | Selected control proposal | Fitted c, Hz/GHz | Calls / stationary | Selected boundary |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| A | Final CH1–8 | 266.839679 | 1.509542 | shape-high (4) | -730.616690 | 18 / 18 | No |
| B | CH1–8 | 268.879362 | 2.021218 | cold-0 (0) | -640.222634 | 6 / 6 | No |
| B | CH1–4 | 268.826502 | 2.895507 | shape-low (3) | -546.554594 | 6 / 6 | No |
| B | CH5–8 | 190.851447 | 7.808977 | cold-2 (2) | -638.836608 | 6 / 6 | No |
| C | CH1–8 | 267.759878 | 1.846733 | shape-low (3) | -593.944657 | 6 / 5 | No |
| C | CH1–4 | 271.452943 | 3.104978 | shape-all (5) | -581.901647 | 6 / 5 | No |
| C | CH5–8 | 198.398059 | 1.065469 | shape-all (5) | -628.632580 | 6 / 6 | No |

The [original DS21-013 baseline](THREE_MODEL_013_RESULTS.md) remains unchanged. Every control row improves its own saved baseline error. B combining improves over both its control halves; C combining improves over low and is worse than high. A reports six dependent low → locked-high → final-all paths and one final-all selection, so it supplies no independent half-band accuracy rows. Selections minimize stationary own training objective, with original start index as the tie-breaker. Reference accuracy does not choose a proposal or algorithm.

All selected boundary flags are false; their stored minimum physical slacks span 0.253133–3.969641. The sole boundary endpoint is stationary **C/low start 1, cold-1**, with stored minimum zero, and is not selected. The original boundary flag concerns satellite total timing and geographic constraints; it does not establish coefficient-bound or common-timing interiority. Stationarity and inactive reported boundaries establish neither global optimality nor correct position.

| Retained nonstationary call | Proposal | KKT | Elapsed, s | Solver success | Boundary |
| --- | --- | ---: | ---: | --- | --- |
| C/all start 2 | cold-2 | 1035.810791 | 20.040422 | No | No |
| C/low start 3 | shape-low | 0.003174326 | 5.750383 | Yes | No |

The fixed KKT threshold remains 0.001. The low-view solver-success flag does not override its failed stationarity certificate. The all-view attempt ran for 20.040 seconds without stationarity; the receipts do not independently establish its stop reason. Neither fit was retried, removed or accepted by changing tolerances. All six A paths completed all three stages; there are no skipped downstream calls or finalized process failures in this run.

## Training fit effects

| Model, CH1–8 | Control objective | Control likelihood NLL | Control frequency RMS, Hz | Objective change from original | NLL change from original | RMS change, Hz |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 32661.799257 | 32253.204720 | 97.835399 | -3266.489501 | -3147.148159 | -60.431483 |
| B | 33442.489690 | 32996.948239 | 95.558627 | -929.938801 | -683.373363 | -28.835507 |
| C | 30588.661088 | 30197.408853 | 95.951672 | -4715.455457 | -4603.691570 | -54.499726 |

The JSON retains corresponding own-view diagnostics and deltas for all seven rows. All seven selected objectives, likelihood NLLs and frequency RMS values decrease relative to their original counterparts. These are within-model training-fit comparisons. Different association/calibration structures make raw scores unsuitable for ranking A against B or C, and frequency RMS is not a position confidence interval. Better in-sample fit alone would not establish better localization; the accuracy table separately records the saved errors.

## Controlled changes and limits

The [discovery control](DISCOVERY_COVERAGE_013_RESULTS.md) changes the hierarchy levels from 100/50/25/12.5 km to 50/25/12.5 km while preserving the 100-point budget and all-view priority. It is reference blind, retains the original 1,052-candidate regional bank and executes the original discovery math. Post-seal coverage evidence showed that the original six 25 km disks excluded the configured reference, whereas the control's three discovery points include it within their 25 km disks. That demonstrates recovered admissible local geography; it does not guarantee coverage everywhere or 0.5 km accuracy.

The [qualified five-stage initializer](COVERAGE_PROPOSALS_013_RESULTS.md) preserves the original shape → fresh bootstrap → hybrid → cold bootstrap → six-proposal operations. Its new training-selected geography and candidate unions produce 40 shared candidates, compared with 49 in the original model comparison. Thus final-model initialization, local candidate sets and centers differ together. This is a controlled downstream comparison of the new discovery policy through the unchanged initialization/model chain, not an isolated attribution of the final improvement to one numerical variable.

Original case inputs, training partition, prior and training frames are exactly equal across the two comparisons: 2,666 / 1,433 / 1,233 all/low/high windows, randomized whole 20-second blocks with seed 20261012, and the original 250 km regional prior. Every final fit retains fitted c, likelihood alpha 1, 20 seconds, 600 iterations and its proposal's original 25 km disk; A high locks the preceding low position. A paths use 90/105/110-second internal/TERM/KILL limits; B/C views use 165/175/180. There are no zero-c fits, numerical-source edits or optimizer retries. All 415 control live/archive source bindings pass, including the unchanged 411-source original numerical subset and native binary. The qualified A-high reader accepts only the frozen sequential core's literal descriptive override; all raw scientific fields remain preserved.

The initialization audit retains three distinct quantities: bootstrap all-view donor-target projection loss reaches 1569.914986 Hz RMS and 5356.305611 Hz maximum absolute residual; export closure to each seed's own physical source function is at most 7.275958e-12 Hz; C's native all-view projection RMS spans 57.558474–426.442881 Hz, with maximum absolute residual 4375.412875 Hz. They must not be substituted for one another. Of 24 required A-low/B model-input projections, 22 use the original strict solver and two B/all seeds use independently certified exact source transfer after the specific nonconvergence error. Their near-bound source clock coefficients remain recorded. Neither fallback nor projection loss is established as the cause of the retained C failures or residual position errors.

B/C half-view likelihoods use their designated observations but share discovery, geography and physical initialization. C additionally derives six receiver lifts once from all training and shares them across 18 seeds. They are not independent end-to-end half-band pipelines. Held observations were not used for these fits or selection. The configured reference entered only after the full scientific seal, for evaluation; it is not independently surveyed ground truth. This receipt audit reads those saved errors without recomputing them.

Aggregate terminal SHA-256: `ac51aa9b16ef26c9388ce81564bfe018c8ea9f49e7f45b89f61e47ed6a04574d`. Evaluation SHA-256: `8f938b22f0cc0fc3b71e19cb1a670c6df893665ce029a3346b82b1c8d483a176`.

The historical five-case table and original 009/011/013 comparisons remain frozen. This additional DS21-013 namespace does not add a development case: nine original complete initialization sets and 25 remaining initializations remain the census. Locked evaluation is unopened. The result supports further bounded transfer of the fixed coverage policy, not a cross-case success claim, promotion by per-case reference or completion of the full-DS21 0.5 km target.
