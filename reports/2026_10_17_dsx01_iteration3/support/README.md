# Displaced-support audit and complete-state portfolio pilot

The two-source portfolio does not repair the fitted-c support losses. Both S01 and S04 select the same endpoint as their fresh matched continuation; no fitted-c associations or challenge points change. This is a strict S01/S04 pilot, not an all-five or all-15-window aggregate. Nothing is promoted or deployed, and sealed iteration2 outputs remain unchanged.

## What displaced support

Exact original/fixed/expanded model replays reproduce all saved assignments, winning candidate IDs and residuals. The all-point populations remain 4,797 on S01 and 3,719 on S04. Three model evaluations per case are recorded, plus two source-loader replay evaluations. Window membership is used only for this retrospective diagnostic, never for proposal generation or selection.

| Fixed → expanded | Lost / new | Lost with best-signal/clutter ratio .8–1 | Lost below ratio .5 | Median former-candidate residual before / after Hz |
|---|---:|---:|---:|---:|
| S01 | 314 / 306 | 12 | 278 | 177.5 / 766.4 |
| S04 | 61 / 124 | 5 | 51 | 139.9 / 862.4 |

Every previous candidate is still present. None of the former candidates on these lost rows becomes completely invisible. This does not rule out smaller soft-visibility effects. Losses are mainly large residual changes, not a slight shift across the hard association threshold. In the conditional density, the row normalizer cancels from the ratio of any satellite posterior to clutter posterior: that ratio is satellite signal density divided by the clutter density. Adding competitors alone cannot turn a still-above-clutter original signal into an unassociated row; changed frequency predictions, q or visibility must reduce signal support.

Window001 falls from 79/86 to 45/86: 35 lost and one gained. Its lost-row median posterior ratio is approximately 2e-9, and the old candidate's new median absolute residual is 1,097 Hz. S01 candidate62052 loses 67/138 assignments as tau changes -1.94096 to -1.66442 seconds and q .0831 to .0489; the old candidate's lost-row median residual becomes 911 Hz. Candidate59845 loses 27/31 as tau changes -9.278 to -11.130 seconds, q .0201 to .00472, and median residual becomes 4,605 Hz. These are model associations, not verified emitter identities.

On S04, window011 falls 15/43 to 11/43 (five lost, one gained). Candidate68043 loses 11/14 as tau moves -3.958 to +2.801 seconds and its lost-row median residual rises from 56.8 to 24,464 Hz. Candidate48117 loses 9/10, with timing9.496→10.781 and median residual165→4,632 Hz. S04 uses its original Space-Track snapshot; this cannot be explained merely by the HF source used on S01/S05.

Four additional native predictions per case give a symmetric two-order decomposition of the orbital change, holding old timing/new geography and new timing/old geography in turn. No additional objective or localization fit is used for this split. Fixed-to-expanded geography moves only .895 km on S01 and .244 km on S04. On lost former-candidate rows, median absolute timing contributions are 670.4/804.7 Hz, compared with geography contributions81.6/34.5 Hz. Calibration-function changes separately have medians182.0/137.1 Hz. Timing dominates this saved-state decomposition, though it is not a causal claim about the optimizer trajectory or correct satellite identity.

Full candidate/RX-window residual, q, timing and threshold summaries are in `audit_S01.json`, `audit_S04.json`; predictor decompositions are in `orbit_split_S01.json`, `orbit_split_S04.json`. Candidate absence remains a separate limitation for hypotheses outside the selected bank; these diagnostics do not insert them by name.

## Generic unchanged-objective intervention

The five starts are complete expanded state, fixed-profile state transported to the SAME expanded bank, fixed geography/calibration/common-clock with expanded timing/q, the reciprocal cross, and deterministic prior-center geography with expanded complete nongeographic state. Every original candidate, physical likelihood, fixed contrast, q budget, prior and bound remains. The prior center is the model coordinate `[0,0]`, not station coordinates. The adapter validates exact common calibration designs and fixed baseline functions before mixing coordinates.

All five starts come from the same fitted-c source functions for both RF arms; c=0 changes only coefficient6 in those seeds. Each arm's own original expanded endpoint remains separately eligible. Both continuation and portfolio score that incumbent once inside the 1,000-call total, then allocate the other999 calls: one continuation or five fixed quotas200/200/200/200/199. Total wall allowance is120 seconds per unit. First seed scores are captured by a forwarding counter without extra objective evaluations. Selection uses total training J only, including feasible nonstationary research iterates; strict acceptance is separately audited.

Three component tests pass and Ruff passes. All eight inference outcomes are sealed in `seal_S01.json` and `seal_S04.json` before the evaluator accesses position or challenge metrics. Initial seed objectives, final objectives, calls and acceptance for every branch are retained in `fit_*.json`; selected complete endpoint vectors are retained. Nonselected endpoint summaries are preserved, but their final vectors are not retained by this prototype. The pilot uses4,585 actual objective evaluations, including eight raw-incumbent scores. Source preparation and postseal evaluation costs are separate.

| Source / arm | Continuation J / strict | Portfolio J / strict | Full associated continuation / portfolio | Challenge associated continuation / portfolio |
|---|---|---|---:|---:|
| S01 fitted-c | 57640.182386 / yes | 57640.182386 / yes | 2509 / 2509 | 58 / 58 |
| S04 fitted-c | 40075.117250 / yes | 40075.117250 / yes | 2866 / 2866 | 71 / 71 |
| S01 c=0 | 57742.813042 / no | 57742.813042 / no | 2520 / 2520 | 49 / 49 |
| S04 c=0 | 41577.813130 / yes | 41817.376338 / no | 2670 / 2608 | 70 / 71 |

S01 fitted-c selects the ordinary expanded continuation; S04 fitted-c retains its raw incumbent. Every nontrivial fitted-c cross/fixed/prior-center branch remains nonstationary at its quota and has worse J. Thus the negative result does not prove that global geometry/calibration search is complete. On c=0, S01 retains its nonstationary incumbent (KKT .0029598); S04 portfolio is worse than the deeper continuation by239.563 J and has KKT1768.69. Its extra one challenge assignment is not a reason to select that state. Five of the eight selected endpoints pass the .001 KKT gate.

The fitted-c geographic positions, association RMS and window001/011 support are unchanged from the expanded baseline. The postseal `evaluation.json` and `eval_*.npz` retain all-point new/lost/retained counts, intersection RMS, candidate identities, timing and position metrics. Position is evaluation-only. The RF arms have different frequency and position effects and are not ranked against each other by their raw training objectives. No remaining-three campaign or hybrid all-five result is inferred from this unsuccessful fitted-c pilot.
