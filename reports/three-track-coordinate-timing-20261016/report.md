# Exact timing-basin search after cold inference

Recording: `fast8-auto-20261016-161535-99008d35-1-lower`.

The [automatic local-segment cold fits](../three-track-local-segments-20261016/report.md) reach strict stationarity but fail to recover the three trajectories. This component shows that those stationary endpoints also contain poor satellite-timing basins. A generic search over every retained satellite lowers the **unchanged** training objective substantially and restores some coherent held predictions. It still does not recover all three trajectories, and it does not establish geographic accuracy.

## Mechanism

Each fold starts from its accepted new cold checkpoint, including the same 86-candidate bank and learned high/low receiver contrast. No user-inspected track memberships or satellite labels are passed to the timing search. Candidates are visited in catalogue-number order. For each candidate, all other parameters remain fixed while its absolute orbit timing is searched from −20 to +20 seconds in 0.05-second increments. The current timing remains an eligible state, so the grid cannot force a worse step.

The search uses the existing normalized selected-CFO likelihood. Replacing a candidate changes both its Gaussian signal contribution and its soft-visibility detection odds, including the likelihood normalizer. The exact 3-second common and 2-second relative timing prior is recomputed in the original common/zero-sum gauge; changing one absolute timing changes that gauge consistently. Original ephemeris, common-timing and physical bounds remain in force. Receive-time clock calibration does not move with orbit timing.

A move must improve the full training objective by more than 0.01. Every accepted move is independently re-evaluated by the original full model, with a maximum permitted objective discrepancy of 1e−6 and no worsening beyond 1e−7. The complete sweep is bounded to 180 seconds, followed by a 60-second joint fitter and independent audit within 65 seconds. A partial sweep is not promoted to a completed method result. Final stationarity must remain at or below 0.001; that threshold is not relaxed.

Both fitted-c and c = 0 arms start from the same fitted-c cold donor, with c set to zero only in the latter. They share observations, candidates, receiver contrasts, priors, physical domain, grid, ordering and work budgets. This is a conditional RF-coefficient ablation, not a separate c = 0 cold discovery campaign.

## Executed results

All four sweeps complete all 86 candidates in 43–44 seconds. The batched single-candidate ephemeris predictions agree exactly with the public orbit port on the actual checked rows. Accepted coordinate moves reproduce the original objective within 5.83e−11.

| Fold | c arm | Timing moves | Objective before sweep | After sweep | After joint refit | Final stationarity |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Forward | fitted | 73 | 59,238.951 | 56,183.671 | 54,977.660 | 0.000335 |
| Forward | zero | 84 | 60,005.771 | 56,734.524 | 55,548.981 | 0.000183 |
| Reverse | fitted | 70 | 58,740.581 | 56,154.343 | 55,339.331 | 0.000134 |
| Reverse | zero | 84 | 59,901.721 | 56,707.191 | 55,749.469 | 0.000437 |

All four final endpoints pass the original numerical gate. Objective values should be compared within an RF arm: the initial zero arm is the same donor with its RF coefficient removed, before reoptimization of the remaining parameters.

For fitted c, the frequency likelihood NLL falls from 57,948 to 54,209 forward and from 57,533 to 54,711 reverse. Thus the score gain is not solely a reduction in timing-prior penalty. These remain training frequency-density scores, separate from held coherence and from geographic accuracy.

![Training objective decrease](01_training_objective.png)

For candidate 69333 in the reverse fitted-c run, the generic search moves timing from −16.547 to −4.850 seconds and decreases the full objective by about 168 at that coordinate. It also moves 69433 from −1.055 to −0.450 seconds. These moves emerge from all training observations, not the user-inspected target groups. This confirms a timing-basin problem at the old stationary endpoint. It does not independently establish the satellite identities or make those shifts physical timestamp corrections.

## Actual held classifier results

The classifier is frozen after training. Each trajectory's reporting label is selected from training posterior mass only and must have more training mass than clutter. A held point counts only when its maximum satellite posterior exceeds clutter and chooses that training-selected label. Unsupported groups remain in the denominator. These are coherence counts, not independently verified identity accuracy.

| Fold | c arm | Early CH2 | CH4 | Late CH2 |
| --- | --- | ---: | ---: | ---: |
| Forward | fitted | 0/14 | 27/36 | 0/13 |
| Forward | zero | 0/14 | 31/36 | 0/13 |
| Reverse | fitted | 3/15 | 1/37 | 0/14 |
| Reverse | zero | 1/15 | 0/37 | 0/14 |

The local-segment cold endpoints before the timing sweep had zero coherent held matches. Fitted c now gives 31/129; this remains worse than the original cold pipeline's 75/129 coherence count on the same folds. The original reverse CH4 label differs from the forward hypothesis, so neither number is independent physical identity truth. No best-result claim follows from a lower in-sample objective.

![Actual held coherence](02_held_coherence.png)

The forward fitted-c CH4 reporting label is **62052**, with 258 Hz held RMS; the reverse label is **69333**, with 1,128 Hz held RMS. Early CH2 remains about 1,232 Hz forward under label 66154, and 531 Hz reverse under label 69433. The late CH2 group remains unsupported in both folds. Thus the timing search repairs some assignments but leaves clock/geometry/association ambiguity and poor temporal transfer.

## What this establishes, and what remains

A strict stationary endpoint was not a good timing solution even for its own likelihood. Exact one-coordinate timing searches can escape those basins without adding a parameter or using target labels. Lower training objective alone does not solve the scientific recovery task. Final receiver-band contrast is still frozen from a pre-profile source donor while candidate assignments and timings change substantially. A next controlled mechanism is to refit that existing contrast jointly with timing, clocks and detectability, proving exact initial transport and retaining the held evaluation. This is a testable next step, not an established physical explanation or a reason to introduce arbitrary per-target shifts.

Five component tests check exact likelihood replacement, the visibility-normalizer effect even at zero posterior, common/relative prior gauge accounting, batched arithmetic and ephemeris/visibility agreement with public ports. Actual-data coordinate receipts include objective and orbital-oracle checks. `verify_result.py` independently reconstructs a saved endpoint and replays its strict audit and held classification without fitting. `run.py` requires the original observation export, local TLE archive and pinned deployed environment from the adjacent replay capsule. Sources, results, progress journals and verification receipts are pinned by `manifest.json`.

The full three-trajectory recovery goal remains incomplete. Nothing in this component deploys a model or changes production.
