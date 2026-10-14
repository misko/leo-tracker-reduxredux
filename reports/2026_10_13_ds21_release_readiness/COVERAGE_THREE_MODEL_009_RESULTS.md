# DS21-009: fixed coverage policy, complete three-model comparison

The same coverage policy previously tested on DS21-013 improves DS21-009's Model B CH1–8 error from **5.327196 to 0.436419 km**, passing 0.5 km on this recording. Model C also improves, from **1.595252 to 1.152329 km**. Model A regresses from **0.658299 to 3.155489 km**. The result supports further transfer testing but does not justify declaring a generally successful release or choosing a different model for each recording using reference error.

All **54 prescribed calls completed; 53 met the unchanged stationarity criterion**. All 12 scientific outcomes and seven training-objective selections were sealed before the reference join. Every selected fit has a false physical-boundary flag. The single nonstationary C-all start remains in the receipts and was not retried.

| Model/view | Original error, km | Coverage error, km | Change, km | Coverage-selected proposal | Below 0.5 km |
| --- | ---: | ---: | ---: | --- | --- |
| A-all | 0.658299 | 3.155489 | +2.497190 | cold-1 | No |
| B-all | 5.327196 | 0.436419 | -4.890777 | shape-all | Yes |
| B-low | 0.790354 | 0.940492 | +0.150138 | shape-high | No |
| B-high | 0.772167 | 4.181058 | +3.408891 | cold-1 | No |
| C-all | 1.595252 | 1.152329 | -0.442923 | shape-high | No |
| C-low | 4.547625 | 1.297634 | -3.249991 | shape-all | No |
| C-high | 1.758365 | 1.578834 | -0.179531 | shape-all | No |

Negative changes improve accuracy. Under the new policy, **both B and C combined-band results beat their own two half-band results**. These half-band fits inherit shared discovery and initialization; they are not independently initialized band-only pipelines. A is the dependent low → high → final-all method and supplies only a final-all selection here.

## What changed and what remained matched

The [discovery transfer](DISCOVERY_COVERAGE_009_RESULTS.md) uses the previously fixed 50 / 25 / 12.5 km grid policy, the same 100-point budget and original full 983-satellite bank. It keeps the original two nearby selections and all three view minima, replacing the remote fallback. Its [five-stage downstream initialization](COVERAGE_PROPOSALS_009_RESULTS.md) produces six proposals and 18 exports over 33 candidates, versus 41 candidates in the original final-model chain.

Prepared observations, training/held partition, regional prior and training frames match the original byte-for-byte as serialized inputs. Candidate union, candidate indices and proposals differ. The downstream A/B/C numerical implementations, fitted-c treatment, likelihood scale, physical priors, six-start budgets and 25 km local disks are unchanged; disk centers follow the new proposals. Therefore this is an end-to-end coverage-policy transfer, not an isolated calibration or candidate-count experiment. The [original comparison](THREE_MODEL_009_RESULTS.md) remains intact.

The three required exact source transfers during seed initialization were already documented separately. They preserve feasible source functions after literal bounded-projection nonconvergence; they do not relax final location-fit convergence or physical constraints.

## Frequency fit and position accuracy are separate

All seven selected solutions have lower own-view objective and NLL than their respective original baselines. These are evaluations under different candidate unions and consequent priors, not a common-support likelihood improvement claim.

| Model/view | NLL change | Posterior RMS change, Hz | Coverage stationarity |
| --- | ---: | ---: | ---: |
| A-all | -676.618 | -7.267 | 9.333e-4 |
| B-all | -1188.122 | -7.886 | 5.789e-4 |
| B-low | -417.671 | -5.688 | 2.089e-4 |
| B-high | -266.766 | 20.205 | 7.821e-5 |
| C-all | -1063.545 | 2.279 | 5.720e-4 |
| C-low | -658.466 | -20.439 | 1.666e-4 |
| C-high | -141.462 | -4.799 | 1.722e-5 |

Model A's NLL improves by 676.618 while its position error worsens by 2.497190 km. B-high's NLL improves while both position error and posterior RMS worsen. C-all's position error improves while posterior RMS increases. Neither score nor residual RMS substitutes for the post-seal position comparison.

## Convergence, boundaries and verification

All 18 A stages, all 18 B starts, all six C-low starts and all six C-high starts are stationary. C-all has five stationary starts. Its unselected `cold-2` start reports solver success but stationarity **0.002907018536**, above the unchanged 0.001 criterion, and reaches a physical constraint. It took 15.867978 seconds and is explicitly nonstationary. Three endpoints across the entire run have a true boundary flag; none is selected. These flags cover the original physical constraints and do not establish that every coefficient is interior or that the position is accurate.

The [compact audit](COVERAGE_THREE_MODEL_009_AUDIT.json) verifies 415 live/archive source pairs, the unchanged 411-source original numerical subset, all 12 unit terminals, the 54-call inventory, all seven stationary training-selected winners and the evaluation's aggregate-terminal binding. It uses standard-library receipt/hash/selection arithmetic, with no additional fit or reference computation.

- Aggregate terminal SHA-256: `f870abf4dab4024724f7c1f2ad40dcfe046bede53bb785c2c638aa70a49a4351`.
- Post-seal evaluation SHA-256: `bdb275318f8e40da43d0b34f02bfd8dc9d52b468225f9af2e7d2285fb01a4bda`.
- Namespace: `reports/2026_10_13_ds21_release_readiness/local/coverage-models-v1/DS21-009`.

These errors use the configured reference, not independently surveyed ground truth. DS21-013's coverage comparison still has no row below 0.5 km; this DS21-009 transfer does not establish full-DS21 performance. Nine original development proposal sets are complete, with 25 still requiring initialization. Locked inference remains unopened. The next release decision must use one frozen algorithm across the development and locked sets, retaining failures and regressions.
